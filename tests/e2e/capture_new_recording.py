"""W3/W4 browser scenario: `Videos -> New Recording` capture shell.

Launches Chromium with deterministic fake media devices (no real camera or
microphone), grants camera permission, and proves the frozen W3/W4 journey:

1. The user reaches the capture shell from `Videos -> New Recording` (not only
   the header Capture icon).
2. The recording view exposes camera preview, Normal Recording / Continuous
   Playlist modes, crop control, Save local copy (default unchecked), Start/
   Stop Recording, a visible timer, upload/processing status, and the
   detected-title/logical-video shell with its empty state.
3. W4 fragment cadence/config and stable fragment IDs are deterministic
   (checked through pure state hooks — no 15s wait).
4. Starting capture with the fake device shows a live, incrementing timer.
5. Stopping succeeds, keeps the final short fragment, and reaches the saved
   state; the synthetic mobile viewport keeps the controls usable.

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

            # 3b. W4 fragment cadence/config — deterministic, no 15s wait.
            cfg = page.evaluate("() => window.__captureFragmentConfig()")
            all_ok &= check(
                "fragment_target_default",
                cfg.get("targetMs") == 15000 and cfg.get("resolvedMs") == 15000,
                json.dumps(cfg),
            )
            all_ok &= check(
                "fragment_configurable_range_10_30s",
                cfg.get("minMs") == 10000 and cfg.get("maxMs") == 30000,
                f"min={cfg.get('minMs')} max={cfg.get('maxMs')}",
            )
            all_ok &= check(
                "fragment_queue_bounded_4",
                cfg.get("maxPendingFragments") == 4,
                str(cfg.get("maxPendingFragments")),
            )
            page.locator("#captureChunkDuration").fill("10")
            resolved_10 = page.evaluate("() => window.__captureFragmentConfig().resolvedMs")
            page.locator("#captureChunkDuration").fill("30")
            resolved_30 = page.evaluate("() => window.__captureFragmentConfig().resolvedMs")
            page.locator("#captureChunkDuration").fill("15")
            all_ok &= check(
                "fragment_cadence_configurable",
                resolved_10 == 10000 and resolved_30 == 30000,
                f"10s={resolved_10} 30s={resolved_30}",
            )

            # 3c. W4 stable, monotonically increasing fragment IDs.
            seq_a = page.evaluate("() => window.__captureTestFragmentSequence(3)")
            seq_b = page.evaluate("() => window.__captureTestFragmentSequence(3)")
            all_ok &= check(
                "fragment_ids_stable_monotonic",
                bool(seq_a.get("monotonic")) and bool(seq_b.get("monotonic"))
                and seq_a.get("ids") == [1, 2, 3] and seq_b.get("ids") == [4, 5, 6],
                f"a={seq_a} b={seq_b}",
            )

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

            # The final short fragment is kept and only marked finalized after
            # a real server response (never a fabricated ACK).
            snap = page.evaluate("() => window.__captureSnapshot()")
            all_ok &= check(
                "final_fragment_kept_on_stop",
                snap.get("fragmentIds") == [1] and snap.get("fragmentSeq") == 1,
                json.dumps({k: snap.get(k) for k in ("fragmentIds", "fragmentSeq")}),
            )
            all_ok &= check(
                "fragment_finalized_only_from_server",
                snap.get("finalizedIndexes") == [0] and snap.get("stalled") is False,
                f"finalized={snap.get('finalizedIndexes')} stalled={snap.get('stalled')}",
            )

            sessions_after = _sessions()
            new_sessions = [s for s in sessions_after if s["sessionId"] not in sessions_before]
            all_ok &= check("capture_session_created", len(new_sessions) == 1, f"{len(new_sessions)} new sessions")
            if new_sessions:
                all_ok &= check("capture_session_finalized", new_sessions[0]["status"] == "FINALIZED", new_sessions[0]["status"])

            # Synthetic mobile viewport keeps the capture controls usable.
            page.set_viewport_size({"width": 390, "height": 844})
            mobile_ok = page.locator("#capturePreview").is_visible() and (
                page.locator("#captureStartBtn").is_visible() or page.locator("#captureStopBtn").is_visible()
            )
            all_ok &= check("mobile_viewport_capture_controls", mobile_ok)
            page.set_viewport_size({"width": 1280, "height": 900})
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
