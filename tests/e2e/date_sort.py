"""Synthetic Date-column check for backend sorting and UI pagination/filtering."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    REPORT.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")
    return condition


def main() -> int:
    data_root = Path(os.environ.get("ZMI_DATA_ROOT", "artifacts/gates/date-sort"))
    videos = data_root / "Videos"
    videos.mkdir(parents=True, exist_ok=True)
    prefix = "date_fixture_" + uuid.uuid4().hex[:8]
    expected = []
    base_epoch = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    for index in range(7):
        path = videos / f"{prefix}_{index}.mp4"
        path.write_bytes(b"synthetic media fixture")
        stamp = base_epoch + index * 86400
        os.utime(path, (stamp, stamp))
        expected.append(path.name)

    api_desc = requests.get(f"{DASHBOARD_URL}/api/files?sort_by=date&order=desc", timeout=20).json()["files"]
    api_rows = [row for row in api_desc if row["name"].startswith(prefix)]
    all_ok = check("api_date_newest_first", [r["name"] for r in api_rows] == list(reversed(expected)))
    api_asc = requests.get(f"{DASHBOARD_URL}/api/files?sort_by=date&order=asc", timeout=20).json()["files"]
    all_ok &= check("api_date_ascending", [r["name"] for r in api_asc if r["name"].startswith(prefix)] == expected)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 1
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        requests_seen = []
        page.on("request", lambda req: requests_seen.append(req.url) if "/api/files?sort_by=date&order=" in req.url else None)
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_function("() => window._allFiles && window._allFiles.length > 0")
            page.locator("#fileFilter").fill(prefix)
            names = page.evaluate("() => window._filteredFiles.map(f => f.name)")
            all_ok &= check("default_newest_order", names == list(reversed(expected)), str(names))
            page.locator('th[data-sort="date"]').click()
            page.wait_for_function("window._fileSort && window._fileSort.dir === 'asc'")
            page.wait_for_function("() => window._filteredFiles[0].name.endsWith('_0.mp4')")
            page.wait_for_function("() => document.querySelectorAll('#filesList tbody tr').length === 5")
            all_ok &= check("date_click_queries_backend", any("order=asc" in url for url in requests_seen))
            first_page = page.evaluate("() => Array.from(document.querySelectorAll('#filesList tbody tr')).map(r => r.cells[0].textContent)")
            all_ok &= check("ascending_first_page", first_page == expected[:5], str(first_page))
            page.locator("#filesPaginationTop button").filter(has_text="2").click()
            second_page = page.evaluate("() => Array.from(document.querySelectorAll('#filesList tbody tr')).map(r => r.cells[0].textContent)")
            all_ok &= check("ascending_second_page", second_page == expected[5:], str(second_page))
            page.locator("th[data-sort='date']").click()
            page.wait_for_function("window._fileSort.dir === 'desc'")
            page.wait_for_function("() => window._filteredFiles[0].name.endsWith('_6.mp4')")
            all_ok &= check("descending_after_filter_and_page", page.evaluate("window._fileSort.dir") == "desc")
        finally:
            browser.close()
    Path("date_sort_report.json").write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
