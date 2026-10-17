"""Mobile regeneration + crop visibility e2e (AC-06/AC-07).

Runs against a live dashboard in a narrow mobile viewport. Uses route mocks for
the documentation endpoints so it proves UI visibility/behavior, not backend
work. Validates the rendered documentation result and version picker against
known text, and proves the capture modal's Clear crop control is a real, visible
control adjacent to the crop overlay (not a tautological presence check).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
REPORT = Path("documentation_mobile_regeneration_report.json")
MOBILE = {"width": 390, "height": 844}
LATEST_MANUAL = "Synthetic latest V2 documentation"
PREVIOUS_MANUAL = "Synthetic previous V2 documentation"


def _ready(page, expression: str) -> None:
    page.wait_for_function(expression, timeout=15000)


def _preview_equals(text: str) -> str:
    """JS predicate that tolerates the preview being briefly absent on re-render."""
    return (
        "() => { const el = document.getElementById('docVersionPreview');"
        f" return !!el && el.textContent.trim() === {json.dumps(text)}; }}"
    )


def main() -> int:
    checks: list[tuple[str, bool]] = []
    versions = [
        {"documentation_version": 2, "pipeline_version": "documentation-v2", "generated_at": "latest", "status": "COMPLETED"},
        {"documentation_version": 1, "pipeline_version": "documentation-v2", "generated_at": "previous", "status": "COMPLETED"},
    ]
    latest_expr = _preview_equals(LATEST_MANUAL)
    previous_expr = _preview_equals(PREVIOUS_MANUAL)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport=MOBILE, has_touch=True, is_mobile=True)
        page = context.new_page()
        page.route("**/api/transcription?**", lambda r: r.fulfill(json={"ok": True, "segments": [], "insights": {}}))
        page.route("**/api/documentation?id=**", lambda r: r.fulfill(json={"ok": True, "steps": [], "manifest": {"procedures": [], "schema_version": "2"}, "ai_package_files": {}}))
        page.route("**/api/documentation/v2/regenerate?**", lambda r: r.fulfill(json={"ok": True, "pipeline": "documentation-v2"}))
        page.route("**/api/video/reprocess?**", lambda r: r.fulfill(status=202, json={"ok": True, "state": "PROCESSING_MEDIA"}))
        page.route("**/api/documentation/versions?**", lambda r: r.fulfill(json={"ok": True, "versions": versions}))
        page.route("**/api/documentation/versions?*version=1", lambda r: r.fulfill(json={"ok": True, "version": versions[1], "manual": PREVIOUS_MANUAL}))
        page.route("**/api/documentation/versions?*version=2", lambda r: r.fulfill(json={"ok": True, "version": versions[0], "manual": LATEST_MANUAL}))
        page.route("**/api/projects", lambda r: r.fulfill(json={"ok": True, "projects": [{"name": "demo", "default": True}]}))
        page.route("**/api/capture/sessions**", lambda r: r.fulfill(json={"ok": True, "sessions": []}))
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.evaluate("window._allFiles = [{media_id:'Videos:synthetic.mp4', user_state:'COMPLETED', timings:{stages:{}, total_seconds:0}}]")
        page.evaluate("preview(encodeURIComponent('Videos:synthetic.mp4'), encodeURIComponent('Transcriptions:synthetic.txt'), true)")

        regenerate = page.get_by_role("button", name="Regenerate Documentation")
        regenerate.wait_for(state="visible", timeout=15000)
        checks.append(("regenerate_visible_mobile", regenerate.is_visible()))
        reprocess = page.get_by_role("button", name="Reprocess Video")
        checks.append(("reprocess_visible_mobile", reprocess.is_visible()))

        preview = page.locator("#docVersionPreview")
        preview.wait_for(state="visible", timeout=15000)
        checks.append(("rendered_latest_result_mobile", preview.inner_text().strip() == LATEST_MANUAL))

        version_select = page.locator("#docVersionSelect")
        version_select.wait_for(state="visible", timeout=15000)
        checks.append(("version_picker_options_mobile", version_select.locator("option").count() == 2))
        version_select.select_option("1")
        _ready(page, previous_expr)
        checks.append(("rendered_previous_result_mobile", preview.inner_text().strip() == PREVIOUS_MANUAL))

        regenerate.click()
        _ready(page, latest_expr)
        checks.append(("regeneration_result_rendered_mobile", preview.inner_text().strip() == LATEST_MANUAL))

        # Capture modal: Clear crop is a real, visible control adjacent to (below)
        # the crop overlay inside the capture modal.
        page.evaluate("openCaptureModal()")
        page.wait_for_selector("#captureModal:not(.hidden)", timeout=15000)
        clear_btn = page.locator("#captureModal #captureCropControls #cropClearBtn")
        clear_btn.wait_for(state="visible", timeout=15000)
        overlay_box = page.locator("#captureModal #cropOverlay").bounding_box()
        clear_box = clear_btn.bounding_box()
        adjacent = bool(overlay_box and clear_box) and clear_box["y"] >= overlay_box["y"] + overlay_box["height"] - 2
        checks.append(("capture_clear_crop_visible_and_adjacent", clear_btn.is_visible() and adjacent))
        page.evaluate("closeCaptureModal()")
        page.wait_for_function(
            "() => document.getElementById('captureModal').classList.contains('hidden')",
            timeout=15000,
        )

        overflow = page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1")
        checks.append(("no_horizontal_overflow", overflow))

        browser.close()

    report = {"checks": [{"name": name, "status": "PASS" if passed else "FAIL"} for name, passed in checks]}
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for check in report["checks"]:
        print(f"[{check['status']}] {check['name']}")
    return 0 if all(passed for _, passed in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
