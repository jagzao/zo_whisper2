"""W5 browser chunk flow using Playwright + fake media devices.

Two accelerated scenarios (no real camera/media):

1. Rotation/order/overlap — a 2s chunk duration drives the MediaRecorder to
   finalize multiple chunks in order while the next chunk keeps recording.
2. Stalled/retry — a synthetic failed chunk-0 upload is observed as a
   retryable stalled state, then an explicit retry recovers and finalizes.

Reports PASS/FAIL checks to JSON like the dashboard smoke test.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
TIMEOUT_MS = 30000
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def _sessions() -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/capture/sessions", timeout=10)
    r.raise_for_status()
    return r.json().get("sessions", [])


def _close_safely(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def _snapshot(page) -> dict:
    return page.evaluate("() => window.__captureSnapshot && window.__captureSnapshot()")


def _open_and_start(page, all_ok) -> bool:
    page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
    all_ok &= check("chunk_capture_button", page.locator('button[aria-label="Capture"]').count() == 1)
    page.locator('button[aria-label="Capture"]').click()
    page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)
    page.locator("#captureChunkDuration").fill("2")
    page.locator("#captureStartBtn").click()
    page.wait_for_function(
        "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
    )
    return all_ok


def rotation_flow(page, all_ok) -> bool:
    all_ok = _open_and_start(page, all_ok)
    page.wait_for_function(
        "() => {"
        " const s = window.__captureSnapshot && window.__captureSnapshot();"
        " if (!s || s.finalizedIndexes.length < 3) return false;"
        " return s.recordingIndex !== null && s.recordingIndex > Math.max.apply(null, s.finalizedIndexes);"
        "}",
        timeout=TIMEOUT_MS,
    )
    snap = _snapshot(page)
    all_ok &= check(
        "chunk_rotation_ordered",
        snap["finalizedIndexes"][:3] == [0, 1, 2],
        json.dumps(snap["finalizedIndexes"]),
    )
    all_ok &= check(
        "chunk_overlap_next_recording",
        snap["recordingIndex"] > snap["finalizedIndexes"][-1],
        f"recording={snap['recordingIndex']} finalized={snap['finalizedIndexes']}",
    )

    page.locator("#captureStopBtn").click()
    page.wait_for_function(
        "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
    )
    all_ok &= check("chunk_saved_state", page.locator("#captureState").inner_text() == "Saved")

    sessions = _sessions()
    active = [s for s in sessions if s.get("status") == "FINALIZED" and s.get("chunks")]
    newest = active[0] if active else None
    all_ok &= check("chunk_session_finalized", newest is not None)
    if newest:
        finalized = [c for c in newest["chunks"] if c.get("state") == "FINALIZED"]
        indexes = [c["index"] for c in finalized]
        all_ok &= check("chunk_server_order", len(finalized) >= 3 and indexes == list(range(len(finalized))), str(indexes))
    return all_ok


def stalled_flow(page, all_ok) -> bool:
    all_ok = _open_and_start(page, all_ok)

    failed = {"once": False}

    def fail_once(route) -> None:
        if not failed["once"]:
            failed["once"] = True
            route.fulfill(status=500, content_type="application/json", body='{"ok": false, "error": "injected"}')
        else:
            route.continue_()

    page.route("**/chunks/0/finalize", fail_once)

    page.wait_for_function(
        "() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return !!(s && s.stalled); }",
        timeout=TIMEOUT_MS,
    )
    all_ok &= check("chunk_stalled_state", page.locator("#captureRetryBtn").is_visible())

    page.unroute("**/chunks/0/finalize", fail_once)
    page.locator("#captureRetryBtn").click()
    page.wait_for_function(
        "() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return !!(s && !s.stalled); }",
        timeout=TIMEOUT_MS,
    )
    page.wait_for_function(
        "() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return !!(s && s.finalizedIndexes.indexOf(0) !== -1); }",
        timeout=TIMEOUT_MS,
    )
    all_ok &= check("chunk_retry_recovered", _snapshot(page)["finalizedIndexes"].count(0) == 1)

    page.locator("#captureStopBtn").click()
    page.wait_for_function(
        "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
    )
    return all_ok


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

        try:
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            all_ok &= rotation_flow(page, all_ok)

            # The rotation flow must be free of browser errors; the stalled
            # flow intentionally injects a 500, so it is checked separately.
            all_ok &= check(
                "chunk_no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000]
            )
            browser_errors.clear()

            # Close and reopen for a clean second scenario.
            page.locator("#captureModal .close-x").click()
            page.wait_for_function(
                "document.getElementById('captureModal').classList.contains('hidden')", timeout=TIMEOUT_MS
            )
            all_ok &= stalled_flow(page, all_ok)
        finally:
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_chunking_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
