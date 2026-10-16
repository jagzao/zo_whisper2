"""W6 browser scenario: short ACKed fragments become server processing chunks.

Launches Chromium with deterministic fake media devices (no real camera or
microphone) and proves the frozen W6 contract end-to-end on the real server:

1. The capture shell is driven with an accelerated fragment cadence (1s) and an
   accelerated processing-chunk duration (4s) via the deterministic test hook
   `window.__captureSetProcessingChunkSeconds`, so the test needs no long wait.
2. While capture keeps running, the server aggregates short ACKed fragments into
   a playable processing chunk once the recorded timeline crosses the configured
   duration - the browser never holds a 15-minute Blob.
3. Stopping the session issues the new `/drain` stop endpoint (never the legacy
   per-fragment chunk finalize) and force-finalizes the partial tail.
4. After stop the server exposes a durable fragment->chunk map whose mapped
   fragments cover every ACKed fragment, and every finalized chunk has real
   media bytes.

This script only inspects the durable, server-observable surface; the FFmpeg
playability proof lives in tests/test_live_capture_assembly.py and the boundary
unit tests in tests/test_live_capture_processing_chunks.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
TIMEOUT_MS = 60000
PROCESSING_CHUNK_SECONDS = 4
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def _close_safely(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def _processing_chunks(session_id: str) -> list[dict]:
    r = requests.get(
        f"{DASHBOARD_URL}/api/capture/sessions/{session_id}/processing-chunks", timeout=10
    )
    r.raise_for_status()
    return r.json().get("processingChunks", [])


def _server_session(session_id: str) -> dict:
    r = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{session_id}", timeout=10)
    r.raise_for_status()
    return r.json()["session"]


def _wait_for(predicate, timeout_s: float, interval_s: float = 0.3):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval_s)
    return None


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return 1

    all_ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            permissions=["camera"],
        )
        page = context.new_page()

        browser_errors: list[str] = []
        page.on("console", lambda msg: browser_errors.append(f"console: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: browser_errors.append(f"pageerror: {exc}"))

        drain_posts: list[str] = []
        legacy_chunk_posts: list[str] = []
        fragment_posts: list[str] = []

        def _observe_request(req) -> None:
            if req.method != "POST":
                return
            if "/drain" in req.url:
                drain_posts.append(req.url)
            if "/fragments" in req.url:
                fragment_posts.append(req.url)
            if "/chunks/" in req.url:
                legacy_chunk_posts.append(req.url)

        page.on("request", _observe_request)

        try:
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)

            # Accelerated fragment cadence (1s) + accelerated processing chunk
            # duration (4s) through the deterministic test hook.
            page.locator("#captureChunkDuration").fill("1")
            resolved = page.evaluate(
                "() => window.__captureSetProcessingChunkSeconds(%d)" % PROCESSING_CHUNK_SECONDS
            )
            all_ok &= check(
                "processing_chunk_seconds_hook",
                resolved == PROCESSING_CHUNK_SECONDS,
                f"resolved={resolved}",
            )

            page.wait_for_function("document.querySelectorAll('#captureProject option').length > 1")
            page.locator("#captureProject").select_option(index=1)
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
            )
            snap = page.evaluate("() => window.__captureSnapshot()")
            session_id = snap.get("sessionId")
            all_ok &= check("capture_session_started", bool(session_id), str(session_id))

            server = _server_session(session_id)
            all_ok &= check(
                "session_uses_accelerated_chunk_duration",
                server.get("chunkDurationSec") == PROCESSING_CHUNK_SECONDS,
                str(server.get("chunkDurationSec")),
            )

            # While still recording, wait until the server has finalized a
            # processing chunk from short fragments.
            auto = _wait_for(
                lambda: next((c for c in _processing_chunks(session_id) if c["state"] == "FINALIZED"), None),
                timeout_s=30,
            )
            live_state = page.evaluate("() => window.__captureSnapshot().state")
            all_ok &= check(
                "chunk_finalized_while_recording",
                auto is not None and live_state == "recording",
                f"auto={auto} state={live_state}",
            )
            if auto is not None:
                all_ok &= check(
                    "auto_chunk_index_zero_has_fragments",
                    auto["chunkIndex"] == 0 and len(auto["fragmentIds"]) >= 1,
                    json.dumps({k: auto.get(k) for k in ("chunkIndex", "fragmentIds", "durationMs")}),
                )

            # Record a little past the boundary so a partial tail exists, then
            # stop.
            page.wait_for_function(
                "() => window.__captureSnapshot().recordedOffsetMs >= %d"
                % ((PROCESSING_CHUNK_SECONDS + 2) * 1000),
                timeout=TIMEOUT_MS,
            )
            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )
            all_ok &= check("capture_saved_state", page.locator("#captureState").inner_text() == "Saved")

            # Stop must use the drain endpoint, never the legacy chunk finalize.
            all_ok &= check("stop_calls_drain_endpoint", len(drain_posts) >= 1, f"drain={drain_posts[:2]}")
            all_ok &= check(
                "no_legacy_chunk_finalize_from_browser",
                not legacy_chunk_posts,
                str(legacy_chunk_posts[:3]),
            )

            # Durable map: every chunk finalized, and the mapped fragments cover
            # every ACKed fragment exactly once.
            chunks = _processing_chunks(session_id)
            all_ok &= check("processing_chunks_nonempty", len(chunks) >= 1, json.dumps(chunks))
            all_ok &= check(
                "all_processing_chunks_finalized",
                all(c["state"] == "FINALIZED" for c in chunks),
                json.dumps([c["state"] for c in chunks]),
            )
            all_ok &= check(
                "processing_indices_ordered_unique",
                [c["chunkIndex"] for c in chunks] == list(range(len(chunks))),
                str([c["chunkIndex"] for c in chunks]),
            )
            mapped = [fid for c in chunks for fid in c["fragmentIds"]]
            all_ok &= check(
                "no_fragment_double_mapped",
                len(mapped) == len(set(mapped)),
                f"mapped={mapped}",
            )
            final_snap = page.evaluate("() => window.__captureSnapshot()")
            acked = list(final_snap.get("ackedFragmentIds") or [])
            all_ok &= check(
                "acked_fragments_all_mapped",
                acked and set(acked).issubset(set(mapped)),
                f"acked={acked} mapped={mapped}",
            )

            final_session = _server_session(session_id)
            finalized_chunks = [c for c in final_session.get("chunks", []) if c["state"] == "FINALIZED"]
            all_ok &= check(
                "finalized_session_matches_map",
                final_session.get("status") == "FINALIZED"
                and len(finalized_chunks) == len(chunks),
                f"status={final_session.get('status')} chunks={len(finalized_chunks)} map={len(chunks)}",
            )
            all_ok &= check(
                "finalized_chunks_have_media",
                bool(finalized_chunks)
                and all((c.get("mediaSizeBytes") or 0) > 0 for c in finalized_chunks),
                json.dumps([{k: c.get(k) for k in ("index", "state", "mediaSizeBytes")} for c in finalized_chunks]),
            )
            all_ok &= check(
                "fragments_use_distinct_endpoint",
                len(fragment_posts) >= 2,
                f"fragments={len(fragment_posts)}",
            )
        finally:
            all_ok &= check("capture_no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000])
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_processing_chunks_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
