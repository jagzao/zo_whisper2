from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
URLS = [
    os.environ.get("ZMI_DESKTOP_URL", "http://127.0.0.1:5000").rstrip("/"),
    os.environ.get("ZMI_MOBILE_URL", "https://127.0.0.1:5001").rstrip("/"),
]
results: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
    print(f"[{results[-1]['status']}] {name}: {detail}")


def main() -> int:
    expected = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for url in URLS:
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            calls: list[dict] = []

            def route_run(route):
                request = route.request
                calls.append({"url": request.url, "token": request.headers.get("x-local-dashboard-token", "")})
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "mode": "full"}))

            page.route("**/api/run/full", route_run)
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            revision = response.headers.get("x-whisper-build", "") if response else ""
            check(f"{url}_current_build", revision == expected, f"served={revision} git={expected}")
            page.wait_for_function("document.querySelector('#workerStatus').textContent.includes('Worker: RUNNING')")
            worker_text = page.locator("#workerStatus").text_content() or ""
            worker_title = page.locator("#workerStatus").get_attribute("title") or ""
            check(f"{url}_worker_observable", all(token in worker_text for token in ("Pending:", "Active:", "Limit:")) and "Next scan:" in worker_title and "Last scan:" in worker_title, worker_text)
            page.get_by_role("button", name="RUN Full").click()
            page.wait_for_function("document.querySelector('#toast').textContent.includes('Pipeline started')")
            check(f"{url}_real_run_full_button", len(calls) == 1 and bool(calls[0]["token"]), str(calls))

            page.unroute("**/api/run/full")
            denied = page.evaluate("async () => { const r = await fetch('/api/run/full', {method:'POST', headers:{'X-Local-Dashboard-Token':'invalid'}}); return {status:r.status, body:await r.json()}; }")
            check(f"{url}_unauthorized_mutation_rejected", denied["status"] == 403 and "error" in denied["body"], str(denied))
            page.route("**/api/run/full", lambda route: route.fulfill(status=403, content_type="application/json", body=json.dumps({"ok": False, "error": "Dashboard authorization expired. Reload Whisper and try again."})))
            page.get_by_role("button", name="RUN Full").click()
            page.wait_for_function("document.querySelector('#toast').textContent.includes('Reload Whisper')")
            check(f"{url}_useful_run_error", "Reload Whisper" in (page.locator("#toast").text_content() or ""))
            context.close()
        browser.close()

    report = ROOT / "artifacts" / "gates" / "run-full"
    report.mkdir(parents=True, exist_ok=True)
    (report / "run_full_button_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if all(item["status"] == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
