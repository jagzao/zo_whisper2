from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
REPORT: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    REPORT.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")
    return ok


SOURCE_SCRIPT = r"""
(() => {
  const canvas = document.createElement('canvas');
  canvas.width = 1280; canvas.height = 720;
  const ctx = canvas.getContext('2d');
  function title(value) {
    ctx.fillStyle = 'white'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'black'; ctx.font = '64px Arial';
    value.split('\n').forEach((line, index) => ctx.fillText(line, 80, 120 + index * 120));
  }
  title('AMS KAP\nCompliance\nSession 1\n2026-08-05 12:29 UTC');
  const stream = canvas.captureStream(5);
  window.__setPlaylistSource = title;
  Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {configurable:true, value:async () => stream});
})();
"""


def main() -> int:
    all_ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, permissions=["camera"])
        page = context.new_page()
        page.add_init_script(SOURCE_SCRIPT)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_selector("#filesList")
            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)")
            page.locator("#captureModePlaylist").check()
            page.locator("#captureStartBtn").click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Recording'")
            session_id = page.evaluate("window.__captureSnapshot().sessionId")
            all_ok &= check("playlist_capture_started_once", bool(session_id))
            page.wait_for_function(
                "Array.from(document.querySelectorAll('#captureLogicalVideos .capture-logical-row')).some(row => row.innerText.includes('Session 1'))",
                timeout=90000,
            )
            session_one = page.locator("#captureLogicalVideos .capture-logical-row").filter(has_text="Session 1")
            all_ok &= check("session1_automatically_detected_and_confirmed", session_one.count() == 1)

            page.evaluate("window.__setPlaylistSource('AMS KAP\\nCompliance\\nSession 2\\n2026-08-05 12:44 UTC')")
            page.wait_for_function(
                "Array.from(document.querySelectorAll('#captureLogicalVideos .capture-logical-row')).some(row => row.innerText.includes('Session 2'))",
                timeout=90000,
            )
            session_two = page.locator("#captureLogicalVideos .capture-logical-row").filter(has_text="Session 2").first
            all_ok &= check("session2_automatically_detected", session_two.count() >= 1)
            logical = page.evaluate("async id => (await (await fetch(`/api/capture/sessions/${id}/logical-videos`)).json()).logicalVideos", session_id)
            all_ok &= check(
                "stable_boundary_within_same_processing_chunk",
                len(logical) >= 2
                and logical[0]["endOffsetMs"] == logical[1]["startOffsetMs"]
                and logical[0]["processingChunkIds"] == logical[1]["processingChunkIds"],
                json.dumps(logical[:2]),
            )
            still = page.evaluate("window.__captureSnapshot()")
            all_ok &= check("same_camera_session_kept_recording", still.get("sessionId") == session_id and still.get("state") == "recording")

            page.evaluate("window.__setPlaylistSource('Unclear slide words')")
            page.wait_for_function(
                "Array.from(document.querySelectorAll('#captureLogicalVideos .capture-logical-row')).some(row => row.innerText.includes('NEEDS_TITLE_REVIEW'))",
                timeout=90000,
            )
            all_ok &= check("low_confidence_title_marked_for_review", True)

            session_two = page.locator("#captureLogicalVideos .capture-logical-row").filter(has_text="Session 2").first
            session_two.locator(".playlist-title-edit").fill("Corrected Session 2")
            session_two.get_by_role("button", name="Rename").click()
            page.get_by_text("Corrected Session 2").wait_for()
            session_two = page.locator("#captureLogicalVideos .capture-logical-row").filter(has_text="Corrected Session 2").first
            session_two.locator(".playlist-date-edit").fill("2026-08-06 12:44 UTC")
            session_two.get_by_role("button", name="Set date").click()
            all_ok &= check("rename_and_recorded_date_review", True)
            session_two.get_by_role("button", name="Split here").click()
            page.wait_for_function(
                "(id) => fetch(`/api/capture/sessions/${id}/logical-videos`).then(r=>r.json()).then(d=>d.logicalVideos.length >= 3)",
                arg=session_id,
            )
            session_two = page.locator("#captureLogicalVideos .capture-logical-row").filter(has_text="Corrected Session 2").first
            session_two.get_by_role("button", name="Merge next").click()
            page.wait_for_function(
                "(id) => fetch(`/api/capture/sessions/${id}/logical-videos`).then(r=>r.json()).then(d=>d.logicalVideos.length === 2)",
                arg=session_id,
            )
            all_ok &= check("split_and_merge_review", True)

            review_row = page.locator("#captureLogicalVideos .capture-logical-row").filter(has_text="NEEDS_TITLE_REVIEW").first
            review_row.get_by_role("button", name="Confirm title").click()
            page.wait_for_function(
                "!Array.from(document.querySelectorAll('#captureLogicalVideos .capture-logical-row')).some(row => row.innerText.includes('Confirm title'))",
            )
            all_ok &= check("confirm_low_confidence_review", True)
            page.locator("#captureStopBtn").click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Saved'")
            all_ok &= check("playlist_stop_works", True)
            all_ok &= check("no_browser_errors", not errors, "; ".join(errors))
        finally:
            page.close()
            context.close()
            browser.close()
    Path("capture_playlist_report.json").write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
