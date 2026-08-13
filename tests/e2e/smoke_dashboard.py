"""Dashboard smoke test using Playwright.

Verifies functionality and captures screenshots of each key section.
Generates a JSON report with passed/failed checks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

DASHBOARD_URL = "http://127.0.0.1:5000"
TIMEOUT_MS = 30000
SCREENSHOTS: list[str] = []
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def screenshot(page, name: str) -> str:
    path = f"dashboard_{name}.png"
    page.screenshot(path=path, full_page=False)
    SCREENSHOTS.append(path)
    print(f"Screenshot: {path}")
    return path


def fetch_files() -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/files", timeout=10)
    r.raise_for_status()
    return r.json().get("files", [])


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return 1

    files = fetch_files()
    target = next(
        (f for f in files if f.get("transcription") and f["transcription"].get("id")),
        None,
    )
    if not target:
        print("No files with a transcription available to test the modal")
        return 1

    print(f"Test file: {target['name']}")
    all_ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
        page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)

        # Home
        screenshot(page, "home")
        rows = page.locator("#filesList table tbody tr").count()
        all_ok &= check("files_table", rows > 0 and rows <= 5, f"{rows} rows (page 1)")
        all_ok &= check("dropzone_visible", page.locator("#dropzone").is_visible())
        all_ok &= check("folders_visible", page.locator("#folders .folder").count() == 4)
        all_ok &= check(
            "pagination_visible",
            page.locator("#filesPaginationTop button").count() > 0
            or page.locator("#filesPagination button").count() > 0,
        )

        # Filter by the test file's own project (avoids hardcoding a project name)
        project_name = target.get("project")
        if project_name:
            page.locator("#projectFilter").select_option(project_name)
            page.wait_for_timeout(400)
            filtered_rows = page.locator("#filesList table tbody tr").count()
            all_ok &= check("project_filter", filtered_rows > 0 and filtered_rows <= 5, f"{filtered_rows} rows")

        # Sort by name desc
        page.locator('th[data-sort="name"]').click()
        page.wait_for_timeout(300)
        page.locator('th[data-sort="name"]').click()
        page.wait_for_timeout(300)
        icon_text = page.locator('th[data-sort="name"] .sort-icon').text_content() or ""
        is_desc = icon_text not in ("", "?", "?")
        detail = "desc icon" if is_desc else f"icon={icon_text.encode('ascii','replace').decode()}"
        all_ok &= check("sort_name_desc", is_desc, detail)

        # Clear filters
        page.locator("#projectFilter").select_option("")
        page.wait_for_timeout(400)
        rows_after = page.locator("#filesList table tbody tr").count()
        all_ok &= check("clear_filter", rows_after > 0, f"{rows_after} rows")

        # Header buttons
        for label in ("Projects", "Logs", "Help"):
            all_ok &= check(
                f"header_{label}", page.locator(f'button[aria-label="{label}"]').count() == 1
            )

        # Preview modal
        row = page.locator(f"#filesList table tbody tr:has-text('{target['name']}')")
        ver_button = row.locator("button[aria-label='View']")
        edit_button = row.locator("button[aria-label='Edit']")
        all_ok &= check("view_btn_enabled", ver_button.is_enabled())
        all_ok &= check("edit_btn_enabled", edit_button.is_enabled())

        ver_button.click()
        page.wait_for_selector("#previewModal:not(.hidden)", timeout=TIMEOUT_MS)
        page.wait_for_timeout(1000)
        all_ok &= check("player_present", page.locator("#editorMedia").count() > 0)
        tx_text = page.locator("#transcriptList").inner_text(timeout=5000)
        all_ok &= check(
            "transcription_loaded", len(tx_text) > 100, f"{len(tx_text)} chars"
        )
        screenshot(page, "preview")

        # Search + highlight (use a real word from the transcription)
        tx_text = page.locator("#transcriptList").inner_text(timeout=5000)
        search_word = next((w for w in tx_text.split() if len(w) >= 5 and w.isalpha()), "the")
        page.locator("#txSearch").fill(search_word)
        page.wait_for_timeout(600)
        marks = page.locator("#transcriptList .segment mark").count()
        count_text = page.locator("#searchCount").text_content() or ""
        all_ok &= check(
            "search_highlight", marks > 0, f"'{search_word}' -> {marks} marks, {count_text}"
        )
        screenshot(page, "editor")

        # Frames tab
        page.locator("#tabFrames").click()
        page.wait_for_timeout(1500)
        screenshot(page, "frames")
        all_ok &= check(
            "frames_tab_visible",
            page.locator("#framesGrid .frame-card").count() > 0
            or page.locator("#framesGrid").inner_text(timeout=2000) != "",
        )

        page.locator("#previewModal .close-x").click()
        page.wait_for_selector("#previewModal.hidden", state="hidden", timeout=TIMEOUT_MS)

        # Edit modal
        edit_button.click()
        page.wait_for_selector("#editModal:not(.hidden)", timeout=TIMEOUT_MS)
        page.wait_for_timeout(500)
        textarea = page.locator("#editTxText")
        tx_value = textarea.input_value()
        all_ok &= check(
            "edit_loaded", len(tx_value.strip()) > 10, f"{len(tx_value)} chars"
        )
        screenshot(page, "edit")
        page.locator("#editModal .close-x").click()
        page.wait_for_selector("#editModal.hidden", state="hidden", timeout=TIMEOUT_MS)

        # Header modals
        for label, modal, item_selector in (
            ("Projects", "#projectsModal", ".project-item"),
            ("Logs", "#logsModal", ""),
            ("Help", "#helpModal", ""),
        ):
            page.locator(f'button[aria-label="{label}"]').click()
            page.wait_for_selector(f"{modal}:not(.hidden)", timeout=TIMEOUT_MS)
            if item_selector:
                count = page.locator(f"{modal} {item_selector}").count()
                all_ok &= check(f"{label.lower()}_modal_items", count > 0, f"{count} items")
            screenshot(page, label.lower())
            page.locator(f"{modal} .close-x").click()
            page.wait_for_selector(f"{modal}.hidden", state="hidden", timeout=TIMEOUT_MS)

        browser.close()

    # Report
    Path("dashboard_report.json").write_text(
        json.dumps({"checks": REPORT, "screenshots": SCREENSHOTS}, indent=2),
        encoding="utf-8",
    )
    print("\nReport saved: dashboard_report.json")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
