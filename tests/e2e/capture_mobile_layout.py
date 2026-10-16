from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
REPORT: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    REPORT.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")
    return passed


def main() -> int:
    all_ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        )
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            ignore_https_errors=True,
            permissions=["camera"],
        )
        page = context.new_page()
        browser_errors: list[str] = []
        page.on("console", lambda msg: browser_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#filesList", timeout=30000)
            page.locator("#newRecordingBtn").click()
            modal = page.locator("#captureModal .capture-modal")
            modal.wait_for(state="visible")

            initial = page.evaluate("""() => {
                const modal = document.querySelector('#captureModal .capture-modal');
                const preview = document.querySelector('#capturePreview').getBoundingClientRect();
                const actions = document.querySelector('#captureActions');
                return {
                    viewportWidth: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    modalWidth: modal.clientWidth,
                    modalScrollWidth: modal.scrollWidth,
                    preview: {top: preview.top, bottom: preview.bottom, width: preview.width, height: preview.height},
                    actionsDirection: getComputedStyle(actions).flexDirection,
                    startVisible: document.querySelector('#captureStartBtn').getBoundingClientRect().height > 0,
                };
            }""")
            all_ok &= check(
                "mobile_layout_fits_viewport",
                initial["documentWidth"] <= initial["viewportWidth"] + 1
                and initial["modalWidth"] <= initial["viewportWidth"]
                and initial["modalScrollWidth"] <= initial["modalWidth"] + 1,
                json.dumps(initial),
            )
            all_ok &= check(
                "camera_preview_visible_near_top",
                initial["preview"]["height"] >= 160
                and initial["preview"]["top"] >= 0
                and initial["preview"]["bottom"] <= 0.75 * 844,
                json.dumps(initial["preview"]),
            )
            all_ok &= check(
                "capture_actions_stacked_and_visible",
                initial["actionsDirection"] == "column" and initial["startVisible"],
                f"direction={initial['actionsDirection']} visible={initial['startVisible']}",
            )

            page.evaluate("""() => renderLogicalVideos({logicalVideos: [
                {id:'mobile-1', title:'AMS KAP Compliance Session 1', confidence:0.98, status:'CONFIRMED'},
                {id:'mobile-2', title:'AMS KAP Compliance Session 2', confidence:0.97, status:'CONFIRMED'}
            ], reviewCandidates: [
                {id:'mobile-review', title:'Unknown / Needs review', confidence:0.61, status:'NEEDS_TITLE_REVIEW'}
            ]})""")
            playlist = page.evaluate("""() => {
                const list = document.querySelector('#captureLogicalVideos');
                const rows = [...list.querySelectorAll('.capture-logical-row')];
                return {
                    listWidth: list.clientWidth,
                    listScrollWidth: list.scrollWidth,
                    rowCount: rows.length,
                    rows: rows.map(row => ({
                        width: row.clientWidth,
                        scrollWidth: row.scrollWidth,
                        textWidth: row.querySelector('span').clientWidth,
                        textScrollWidth: row.querySelector('span').scrollWidth,
                        buttonHeight: row.querySelector('button').getBoundingClientRect().height,
                        buttons: row.querySelectorAll('button').length,
                    })),
                };
            }""")
            all_ok &= check(
                "playlist_results_readable_without_overflow",
                playlist["rowCount"] == 3
                and playlist["listScrollWidth"] <= playlist["listWidth"] + 1
                and all(row["scrollWidth"] <= row["width"] + 1 for row in playlist["rows"])
                and all(row["buttonHeight"] >= 44 for row in playlist["rows"]),
                json.dumps(playlist),
            )

            modal.evaluate("el => { el.scrollTop = Math.min(120, el.scrollHeight - el.clientHeight); }")
            start = page.locator("#captureStartBtn")
            start_box = start.bounding_box()
            start_scroll = modal.evaluate("el => el.scrollTop")
            all_ok &= check(
                "sticky_start_action_accessible",
                start.is_visible()
                and start_scroll > 0
                and start_box is not None
                and start_box["y"] + start_box["height"] <= 844,
                json.dumps({"box": start_box, "scrollTop": start_scroll}),
            )
            page.wait_for_function("document.querySelectorAll('#captureProject option').length > 1")
            page.locator("#captureProject").select_option(index=1)
            start.click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Recording'", timeout=30000)
            stop = page.locator("#captureStopBtn")
            modal.evaluate("el => { el.scrollTop = Math.min(120, el.scrollHeight - el.clientHeight); }")
            stop_box = stop.bounding_box()
            sticky_state = modal.evaluate("el => ({scrollTop: el.scrollTop, maxScroll: el.scrollHeight - el.clientHeight})")
            all_ok &= check(
                "sticky_stop_action_accessible",
                stop.is_visible()
                and sticky_state["scrollTop"] > 0
                and stop_box is not None
                and stop_box["y"] + stop_box["height"] <= 844,
                json.dumps({"box": stop_box, **sticky_state}),
            )
            stop.click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Saved'", timeout=30000)
            all_ok &= check("mobile_recording_stops", True)
            all_ok &= check("no_mobile_browser_errors", not browser_errors, "; ".join(browser_errors))
        finally:
            context.close()
            browser.close()

    Path("capture_mobile_layout_report.json").write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
