from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
REPORT = Path("documentation_detail_actions_report.json")


def main() -> int:
    checks = []
    versions = [
        {"documentation_version": 2, "pipeline_version": "documentation-v2", "generated_at": "latest", "status": "COMPLETED"},
        {"documentation_version": 1, "pipeline_version": "documentation-v2", "generated_at": "previous", "status": "COMPLETED"},
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/transcription?**", lambda route: route.fulfill(json={"ok": True, "segments": [], "insights": {}}))
        page.route("**/api/documentation?id=**", lambda route: route.fulfill(json={"ok": True, "steps": [], "manifest": {"procedures": [], "schema_version": "2"}, "ai_package_files": {}}))
        page.route("**/api/documentation/v2/regenerate?**", lambda route: route.fulfill(json={"ok": True, "pipeline": "documentation-v2"}))
        page.route("**/api/video/reprocess?**", lambda route: route.fulfill(status=202, json={"ok": True, "state": "PROCESSING_MEDIA"}))
        page.route("**/api/documentation/versions?**", lambda route: route.fulfill(json={"ok": True, "versions": versions}))
        page.route("**/api/documentation/versions?*version=1", lambda route: route.fulfill(json={"ok": True, "version": versions[1], "manual": "Synthetic previous V2 documentation"}))
        page.route("**/api/documentation/versions?*version=2", lambda route: route.fulfill(json={"ok": True, "version": versions[0], "manual": "Synthetic latest V2 documentation"}))
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.evaluate("window._allFiles = [{media_id:'Videos:synthetic.mp4', user_state:'COMPLETED', timings:{stages:{upload:{duration_seconds:1.2}}, total_seconds:1.2}}]")
        page.evaluate("preview(encodeURIComponent('Videos:synthetic.mp4'), encodeURIComponent('Transcriptions:synthetic.txt'), true)")
        page.locator(".editor-main > p.muted").wait_for()
        state_metrics = page.locator(".editor-main > p.muted").inner_text()
        checks.append(("user_state_and_timings_visible", "COMPLETED" in state_metrics and "upload 1.2s" in state_metrics))
        page.get_by_role("button", name="Regenerate Documentation").wait_for()
        checks.append(("separate_actions_visible", page.get_by_role("button", name="Reprocess Video").is_visible()))
        page.get_by_role("button", name="Regenerate Documentation").click()
        page.get_by_text("Synthetic latest V2 documentation").wait_for()
        checks.append(("v2_result_visible", True))
        page.locator("#docVersionSelect").wait_for(state="visible")
        checks.append(("version_select_visible", page.locator("#docVersionSelect option").count() == 2))
        page.locator("#docVersionSelect").select_option("1")
        page.get_by_text("Synthetic previous V2 documentation").wait_for()
        checks.append(("previous_version_viewable", True))
        page.get_by_role("button", name="Reprocess Video").click()
        page.get_by_text("Video media processing started").wait_for()
        checks.append(("reprocess_distinct_action", True))
        browser.close()
    report = {"checks": [{"name": name, "status": "PASS" if passed else "FAIL"} for name, passed in checks]}
    REPORT.write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
    for check in report["checks"]:
        print(f"[{check['status']}] {check['name']}")
    return 0 if all(passed for _, passed in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
