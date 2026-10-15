"""W4 browser camera capture smoke test using Playwright + fake media devices.

Launches Chromium with deterministic fake media-stream devices (no real camera
or microphone), grants camera permission, and exercises the full capture
lifecycle: open modal -> start (getUserMedia + MediaRecorder) -> visible
recording state -> stop/finalize -> visible saved state -> server-side session
with finalized media. Reports PASS/FAIL checks to JSON like the dashboard
smoke test.
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


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return 1

    sessions_before = {s["sessionId"] for s in _sessions()}
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
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)

            # Capture button opens the modal.
            all_ok &= check("capture_button_visible", page.locator('button[aria-label="Capture"]').count() == 1)
            page.locator('button[aria-label="Capture"]').click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)
            all_ok &= check("capture_modal_opens", page.locator("#captureModal:not(.hidden)").count() == 1)

            # Start -> requesting -> recording.
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
            )
            all_ok &= check(
                "capture_recording_state",
                page.locator("#captureState").inner_text() == "Recording",
                page.locator("#captureState").inner_text(),
            )
            all_ok &= check("capture_stop_btn_visible", page.locator("#captureStopBtn").is_visible())
            all_ok &= check("capture_start_btn_hidden", page.locator("#captureStartBtn").is_hidden())
            all_ok &= check(
                "capture_preview_has_stream",
                page.evaluate("() => document.getElementById('capturePreview').srcObject !== null"),
            )

            page.wait_for_function(
                "() => { const v = document.getElementById('capturePreview'); return v.readyState >= 2 && v.videoWidth > 0; }",
                timeout=TIMEOUT_MS,
            )

            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )
            all_ok &= check(
                "capture_saved_state",
                page.locator("#captureState").inner_text() == "Saved",
                page.locator("#captureState").inner_text(),
            )

            # Server-side: a new FINALIZED session with finalized media exists.
            sessions_after = _sessions()
            new_sessions = [s for s in sessions_after if s["sessionId"] not in sessions_before]
            all_ok &= check("capture_session_created", len(new_sessions) == 1, f"{len(new_sessions)} new sessions")
            if new_sessions:
                session = new_sessions[0]
                all_ok &= check("capture_session_finalized", session["status"] == "FINALIZED", session["status"])
                chunks = session.get("chunks", [])
                finalized = [c for c in chunks if c.get("state") == "FINALIZED" and c.get("mediaSizeBytes", 0) > 0]
                all_ok &= check("capture_media_persisted", len(finalized) == 1, f"{chunks}")
                all_ok &= check(
                    "capture_recorded_at_persisted", bool(session.get("recordedAt")), str(session.get("recordedAt"))
                )
        finally:
            all_ok &= check(
                "capture_no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000]
            )
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
