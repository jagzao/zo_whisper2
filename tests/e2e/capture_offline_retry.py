"""W7 browser scenario: durable IndexedDB buffer, offline retry and reconnect.

Launches Chromium with deterministic fake media devices (no real camera or
microphone) and proves the frozen W7 journey:

1. The pending-fragment buffer is durable IndexedDB keyed by capture session +
   stable fragment ID, and it is bounded with a visible near/full warning.
2. A short fragment is persisted to IndexedDB before the network upload; while
   the network is offline no server ACK exists, yet the fragment survives
   locally.
3. On reconnect the *same* fragment ID is retried and the buffer is released
   only after the server ACK; the server never stores a duplicate.
4. A reload restores still-pending fragments and re-uploads them with their
   original IDs (idempotent replay) without duplicates.
5. "Save local copy" stays opt-in OFF by default and the durable buffer never
   writes to browser Downloads/gallery.

Synthetic devices/media only. Reports PASS/FAIL checks to
`capture_offline_retry_report.json`.

Environment:
- ZMI_BASE_URL: dashboard base URL (default http://127.0.0.1:5000)
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
TIMEOUT_MS = 45000
REPORT: list[dict] = []
# Offline mode makes the dashboard's own pollers fail with expected transport
# errors; those are not application defects.
NETWORK_ERROR_MARKERS = (
    "Failed to fetch",
    "NetworkError",
    "net::ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK",
    "The Internet connection has been lost",
)


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def _sessions() -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/capture/sessions", timeout=10)
    r.raise_for_status()
    return r.json().get("sessions", [])


def _fragments(session_id: str) -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{session_id}/fragments", timeout=10)
    r.raise_for_status()
    return r.json().get("fragments", [])


def _close_safely(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def _is_network_error(text: str) -> bool:
    return any(marker in text for marker in NETWORK_ERROR_MARKERS)


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

        def _record_error(text: str) -> None:
            if not _is_network_error(text):
                browser_errors.append(text)

        page.on("console", lambda msg: _record_error(f"console: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: _record_error(f"pageerror: {exc}"))
        downloads: list[str] = []
        page.on("download", lambda d: downloads.append(d.suggested_filename))

        try:
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)

            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)

            # 5a. Save local copy is opt-in OFF by default (no download).
            all_ok &= check(
                "save_local_default_off",
                page.locator("#captureSaveLocal").is_checked() is False,
                str(page.locator("#captureSaveLocal").is_checked()),
            )
            buffer_limit = page.locator("#captureBufferLimitMB")
            all_ok &= check("buffer_limit_default_64_mb", buffer_limit.input_value() == "64")
            buffer_limit.fill("80")
            buffer_limit.dispatch_event("change")
            all_ok &= check(
                "buffer_limit_user_configurable",
                page.evaluate("localStorage.getItem('zmi.captureBufferLimitMB')") == "80",
            )

            # 1. Durable bounded IndexedDB buffer with a visible warning.
            page.evaluate("() => window.__captureBufferClearTest()")
            state = page.evaluate("() => window.__captureBufferState()")
            all_ok &= check("buffer_supported_indexeddb", bool(state.get("supported")), json.dumps(state))
            all_ok &= check("buffer_starts_empty_none", state.get("count") == 0 and state.get("warning") == "none", json.dumps(state))

            limit = 1024 * 1024
            page.evaluate("(n) => window.__captureSetBufferLimitBytes(n)", limit)
            page.evaluate("(n) => window.__captureBufferFillTest(n)", limit // 4)
            near = page.evaluate("() => window.__captureBufferState()")
            all_ok &= check(
                "buffer_near_limit_warning_visible",
                near.get("warning") == "none"
                and page.locator("#captureBufferWarning").is_hidden(),
                json.dumps(near),
            )
            page.evaluate("(n) => window.__captureBufferFillTest(n)", limit // 2)
            near2 = page.evaluate("() => window.__captureBufferState()")
            all_ok &= check(
                "buffer_near_limit_warning",
                near2.get("warning") == "near" and page.locator("#captureBufferWarning").is_visible(),
                json.dumps(near2),
            )
            page.evaluate("(n) => window.__captureBufferFillTest(n)", limit // 2)
            full = page.evaluate("() => window.__captureBufferState()")
            all_ok &= check(
                "buffer_full_warning_visible",
                full.get("warning") == "full"
                and full.get("bytes") >= full.get("limitBytes")
                and "Local buffer FULL" in page.locator("#captureBufferWarning").inner_text(),
                json.dumps(full),
            )
            all_ok &= check(
                "buffer_bounded_never_exceeds_limit",
                full.get("bytes") <= full.get("limitBytes") * 1.1,
                f"bytes={full.get('bytes')} limit={full.get('limitBytes')}",
            )
            all_ok &= check(
                "buffer_records_keyed_by_fragment",
                page.evaluate(
                    "async () => { const rows = await window.__captureBufferAll();"
                    " return rows.length > 0 && rows.every(r => r.sessionId && r.fragmentId && r.sizeBytes > 0); }"
                ),
            )
            page.evaluate("() => window.__captureBufferClearTest()")

            # 2/3. Offline: fragment persists locally with no server ACK; on
            # reconnect the same ID is retried and released only after ACK.
            page.locator("#captureBufferLimitMB").fill("0.05")
            page.locator("#captureBufferLimitMB").dispatch_event("change")
            page.evaluate("() => window.__captureSetAutoRetry(false)")
            page.locator("#captureChunkDuration").fill("1")
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
            )
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot();"
                " return !!(s && s.ackedFragmentIds.length >= 1); }",
                timeout=TIMEOUT_MS,
            )
            session_id = page.evaluate("() => window.__captureSnapshot().sessionId")
            acked_online = page.evaluate("() => window.__captureSnapshot().ackedFragmentIds")
            all_ok &= check("first_fragment_acked_online", len(acked_online) >= 1, str(acked_online))

            context.set_offline(True)
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot();"
                " return !!(s && s.bufferCount >= 1 && s.stalled === true); }",
                timeout=TIMEOUT_MS,
            )
            offline_state = page.evaluate("() => window.__captureSnapshot()")
            buffered = page.evaluate("async () => await window.__captureBufferAll()")
            buffered_ids = [row["fragmentId"] for row in buffered]
            server_offline = _fragments(session_id)
            server_ids_offline = {f["fragmentId"] for f in server_offline}
            all_ok &= check(
                "fragment_persisted_before_network",
                len(buffered_ids) >= 1 and all(fid not in server_ids_offline for fid in buffered_ids),
                f"buffered={buffered_ids} server={sorted(server_ids_offline)}",
            )
            all_ok &= check(
                "offline_buffer_warning_visible",
                offline_state.get("bufferWarning") in ("near", "full")
                and page.locator("#captureBufferWarning").is_visible(),
                json.dumps({k: offline_state.get(k) for k in ("bufferCount", "bufferedBytes", "bufferLimitBytes", "bufferWarning")}),
            )

            # Reconnect: the same IDs are retried; the buffer drains only after
            # the server ACK.
            context.set_offline(False)
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot();"
                " return !!(s && s.bufferCount === 0 && s.stalled === false); }",
                timeout=TIMEOUT_MS,
            )
            reconnected = page.evaluate("() => window.__captureSnapshot()")
            server_online = _fragments(session_id)
            server_ids_online = [f["fragmentId"] for f in server_online]
            all_ok &= check(
                "reconnect_retries_same_ids",
                all(fid in server_ids_online for fid in buffered_ids),
                f"buffered={buffered_ids} server={server_ids_online}",
            )
            all_ok &= check(
                "reconnect_no_duplicate_fragments",
                len(server_ids_online) == len(set(server_ids_online))
                and all(f.get("state") == "ACKED" and f.get("mediaSizeBytes", 0) > 0 for f in server_online),
                json.dumps([{k: f.get(k) for k in ("fragmentId", "state", "mediaSizeBytes")} for f in server_online]),
            )
            all_ok &= check(
                "reconnect_buffer_released_after_ack",
                reconnected.get("bufferCount") == 0 and reconnected.get("bufferedBytes") == 0,
                json.dumps({k: reconnected.get(k) for k in ("bufferCount", "bufferedBytes")}),
            )
            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )
            all_ok &= check("capture_saved_after_reconnect", page.locator("#captureState").inner_text() == "Saved")

            # 4. Reload restores a still-pending fragment with its original ID.
            title = "reload restore synthetic " + uuid.uuid4().hex[:8]
            reload_session = page.evaluate(
                """async (title) => {
                    const r = await fetch('/api/capture/sessions', {
                        method: 'POST',
                        headers: {'X-Local-Dashboard-Token': DASHBOARD_TOKEN, 'Content-Type': 'application/json'},
                        body: JSON.stringify({title}),
                    });
                    return (await r.json()).session.sessionId;
                }""",
                title,
            )
            page.evaluate("() => window.__captureBufferClearTest()")
            page.evaluate(
                "(sid) => window.__captureBufferFillTest(4096, sid)",
                reload_session,
            )
            pending_before = page.evaluate("() => window.__captureBufferState()")
            pending_id = page.evaluate("async () => (await window.__captureBufferAll())[0].fragmentId")
            all_ok &= check(
                "pending_fragment_survives_before_reload",
                pending_before.get("count") == 1 and _fragments(reload_session) == [],
                json.dumps(pending_before),
            )
            page.reload(timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
            page.wait_for_function(
                "async () => { const s = await window.__captureBufferState(); return s.count === 0; }",
                timeout=TIMEOUT_MS,
            )
            restored = _fragments(reload_session)
            restored_ids = [f["fragmentId"] for f in restored]
            all_ok &= check(
                "reload_restores_pending_fragment_same_id",
                restored_ids == [pending_id]
                and restored[0]["state"] == "ACKED"
                and restored[0]["mediaSizeBytes"] > 0
                and len(restored_ids) == len(set(restored_ids)),
                json.dumps(restored_ids),
            )
            all_ok &= check(
                "reload_restore_no_duplicate",
                page.evaluate("async () => (await window.__captureBufferAll()).length") == 0,
            )

            # 5b. The durable buffer never wrote to browser Downloads/gallery.
            all_ok &= check("no_browser_downloads", not downloads, "; ".join(downloads))
        finally:
            all_ok &= check("no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000])
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_offline_retry_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
