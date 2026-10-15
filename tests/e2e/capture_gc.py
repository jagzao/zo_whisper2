from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
checks: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{checks[-1]['status']}] {name}: {detail}")


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            section = page.locator("details").filter(has_text="Media cleanup suggestions")
            section.locator("summary").click()
            check("gc_no_automatic_delete_notice", "No media is deleted automatically." in section.inner_text())
            review = section.get_by_role("button", name="Review stale processed captures")
            check("gc_review_control_visible", review.is_visible())
            review.click()
            state = section.locator("#captureGcCandidates")
            state.wait_for()
            page.wait_for_function("document.getElementById('captureGcCandidates').textContent.length > 0")
            check("gc_suggestions_surface_in_ui", "Could not load" not in state.inner_text(), state.inner_text())
            check("gc_suggestions_have_no_automatic_delete_action", section.get_by_role("button", name="Delete").count() == 0)
            check("gc_no_browser_errors", not errors, "; ".join(errors))
        finally:
            page.close()
            context.close()
            browser.close()
    Path("capture_gc_report.json").write_text(json.dumps({"checks": checks}, indent=2), encoding="utf-8")
    return 0 if all(row["status"] == "PASS" for row in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
