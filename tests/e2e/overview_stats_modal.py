"""Synthetic Overview Stats Modal journey: toolbar icon, open, metrics, close paths, mobile."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
REPORT: list[dict] = []

EXPECTED_LABELS = ["Files processed", "Media processed", "Success rate", "Avg. processing time"]


def check(name: str, condition: bool, detail: str = "") -> bool:
    REPORT.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")
    return condition


def modal_is_open(page) -> bool:
    return page.evaluate("() => !document.getElementById('overviewModal').classList.contains('hidden')")


def modal_cards(page) -> list[dict]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#overviewModalMetrics .metric')).map(m => ({"
        " value: m.querySelector('.value') ? m.querySelector('.value').textContent.trim() : '',"
        " label: m.querySelector('.label') ? m.querySelector('.label').textContent.trim() : '' }))"
    )


def main_cards(page) -> list[dict]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#metrics .metric')).map(m => ({"
        " value: m.querySelector('.value') ? m.querySelector('.value').textContent.trim() : '',"
        " label: m.querySelector('.label') ? m.querySelector('.label').textContent.trim() : '' }))"
    )


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 1
    all_ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_function("() => document.querySelectorAll('#metrics .metric').length === 4")
            icon = page.locator('header button[aria-label="Overview"]')
            all_ok &= check("toolbar_icon_visible", icon.is_visible(), "header Overview icon button rendered")
            icon.click()
            page.wait_for_function("() => !document.getElementById('overviewModal').classList.contains('hidden')")
            all_ok &= check("click_opens_modal", modal_is_open(page), "modal overlay visible after icon click")
            all_ok &= check("modal_title", page.locator("#overviewModalTitle").inner_text().strip() == "Overview", "modal heading text")
            cards = modal_cards(page)
            main = main_cards(page)
            all_ok &= check("modal_four_metric_labels", [c["label"] for c in cards] == EXPECTED_LABELS, str([c["label"] for c in cards]))
            all_ok &= check("modal_metric_values_nonempty", len(cards) == 4 and all(c["value"] for c in cards), str([c["value"] for c in cards]))
            all_ok &= check("modal_reuses_overview_values", cards == main, "modal cards match the dashboard Overview cards")
            page.locator("#overviewModal .close-x").click()
            page.wait_for_function("() => document.getElementById('overviewModal').classList.contains('hidden')")
            all_ok &= check("close_x_hides_modal", not modal_is_open(page), "close X dismissed modal")
            icon.click()
            page.wait_for_function("() => !document.getElementById('overviewModal').classList.contains('hidden')")
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.getElementById('overviewModal').classList.contains('hidden')")
            all_ok &= check("escape_hides_modal", not modal_is_open(page), "Escape dismissed modal")
            icon.click()
            page.wait_for_function("() => !document.getElementById('overviewModal').classList.contains('hidden')")
            page.mouse.click(8, 8)
            page.wait_for_function("() => document.getElementById('overviewModal').classList.contains('hidden')")
            all_ok &= check("backdrop_hides_modal", not modal_is_open(page), "backdrop click dismissed modal")
            all_ok &= check(
                "main_overview_still_visible",
                page.locator("#metrics").is_visible()
                and page.locator("#metrics .metric").count() == 4,
                "main Overview section keeps 4 cards",
            )
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            try:
                mobile.goto(DASHBOARD_URL, wait_until="domcontentloaded")
                mobile.wait_for_function("() => document.querySelectorAll('#metrics .metric').length === 4")
                mobile.locator('header button[aria-label="Overview"]').click()
                mobile.wait_for_function("() => !document.getElementById('overviewModal').classList.contains('hidden')")
                box = mobile.locator("#overviewModal .modal").bounding_box()
                fits = box is not None and box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 844
                all_ok &= check("mobile_modal_fits_viewport", fits, str(box))
                mobile.locator("#overviewModal .close-x").click()
                mobile.wait_for_function("() => document.getElementById('overviewModal').classList.contains('hidden')")
                all_ok &= check("mobile_close_x_hides_modal", not modal_is_open(mobile), "mobile close X dismissed modal")
            finally:
                mobile.close()
        finally:
            browser.close()
    Path("overview_stats_modal_report.json").write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
