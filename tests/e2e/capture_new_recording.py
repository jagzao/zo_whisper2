"""W3 browser scenario: `Videos -> New Recording` capture shell.

Launches Chromium with deterministic fake media devices (no real camera or
microphone), grants camera permission, and proves the frozen W3 journey:

1. The user reaches the capture shell from `Videos -> New Recording` (not only
   the header Capture icon).
2. The recording view exposes camera preview, Normal Recording / Continuous
   Playlist modes, crop control, Save local copy (default unchecked), Start/
   Stop Recording, a visible timer, upload/processing status, and the
   detected-title/logical-video shell with its empty state.
3. Starting capture with the fake device shows a live, incrementing timer.
4. Stopping succeeds and reaches the saved state.

Synthetic devices/media only. Reports PASS/FAIL checks to JSON like the other
capture e2e scripts.
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

            # 1. Videos -> New Recording entry.
            all_ok &= check(
                "videos_section_present",
                page.locator("#videosSection h2").inner_text().strip().lower() == "videos",
                page.locator("#videosSection h2").inner_text(),
            )
            all_ok &= check(
                "new_recording_button_visible",
                page.locator("#newRecordingBtn").is_visible()
                and page.locator("#newRecordingBtn").inner_text().strip() == "New Recording",
            )
            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)
            all_ok &= check("new_recording_opens_capture", page.locator("#captureModal:not(.hidden)").count() == 1)

            # 2. Required controls exist in the capture shell.
            all_ok &= check("preview_visible", page.locator("#capturePreview").is_visible())
            all_ok &= check(
                "normal_mode_visible",
                page.locator("#captureModeNormal").is_visible()
                and "Normal Recording" in page.locator("label[for='captureModeNormal']").inner_text(),
            )
            all_ok &= check(
                "playlist_mode_visible",
                page.locator("#captureModePlaylist").is_visible()
                and "Continuous Playlist" in page.locator("label[for='captureModePlaylist']").inner_text(),
            )
            all_ok &= check("crop_control_visible", page.locator("#cropOverlay").is_visible() and page.locator("#cropClearBtn").is_visible())
            all_ok &= check("save_local_present_unchecked", page.locator("#captureSaveLocal").is_checked() is False)
            all_ok &= check("start_button_visible", page.locator("#captureStartBtn").is_visible())
            all_ok &= check("stop_button_hidden_initially", page.locator("#captureStopBtn").is_hidden())
            all_ok &= check(
                "timer_visible_initial",
                page.locator("#captureTimer").is_visible() and page.locator("#captureTimer").inner_text() == "00:00:00",
                page.locator("#captureTimer").inner_text(),
            )
            all_ok &= check("upload_status_visible", page.locator("#captureUploadStatus").is_visible())
            all_ok &= check(
                "logical_videos_shell_empty",
                page.locator("#captureLogicalVideos").is_visible()
                and "No detected titles yet" in page.locator("#captureLogicalVideos").inner_text(),
            )

            # 3. Mode choice is wired (playlist <-> normal).
            page.locator("#captureModePlaylist").check()
            all_ok &= check("playlist_mode_selectable", page.evaluate("() => window.__captureSnapshot().mode") == "playlist")
            page.locator("#captureModeNormal").check()
            all_ok &= check("normal_mode_selectable", page.evaluate("() => window.__captureSnapshot().mode") == "normal")

            # 4. Start fake-device capture with a visible, incrementing timer.
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
            )
            all_ok &= check("recording_state", page.locator("#captureState").inner_text() == "Recording")
            all_ok &= check("stop_button_visible_while_recording", page.locator("#captureStopBtn").is_visible())
            all_ok &= check(
                "preview_has_stream",
                page.evaluate("() => document.getElementById('capturePreview').srcObject !== null"),
            )
            page.wait_for_function(
                "() => { const v = document.getElementById('capturePreview'); return v.readyState >= 2 && v.videoWidth > 0; }",
                timeout=TIMEOUT_MS,
            )
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return !!(s && s.timerSeconds >= 2); }",
                timeout=TIMEOUT_MS,
            )
            timer_text = page.locator("#captureTimer").inner_text()
            all_ok &= check(
                "timer_advances_while_recording",
                timer_text != "00:00:00" and page.evaluate("() => window.__captureSnapshot().timerSeconds") >= 2,
                timer_text,
            )

            # 5. Stop succeeds and reaches the saved state.
            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )
            all_ok &= check("capture_saved_state", page.locator("#captureState").inner_text() == "Saved")

            sessions_after = _sessions()
            new_sessions = [s for s in sessions_after if s["sessionId"] not in sessions_before]
            all_ok &= check("capture_session_created", len(new_sessions) == 1, f"{len(new_sessions)} new sessions")
            if new_sessions:
                all_ok &= check("capture_session_finalized", new_sessions[0]["status"] == "FINALIZED", new_sessions[0]["status"])
        finally:
            all_ok &= check("capture_no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000])
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_new_recording_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
