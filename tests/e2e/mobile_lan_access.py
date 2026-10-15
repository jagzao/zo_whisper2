"""W25 browser scenario: phone-style mobile/LAN access over HTTPS.

Drives the real dashboard through a Chromium context that reaches it over
HTTPS (the LAN transport) with deterministic fake camera devices, and proves
the frozen W25 journey:

1. The page is served over HTTPS and loads the dashboard.
2. The header/capture health badges report backend ONLINE via the same-origin
   `/api/health` endpoint (no loopback URL is hardcoded in the page).
3. `/api/network` is reachable same-origin; when LAN mode is on it advertises
   HTTPS LAN URLs and a certificate fingerprint, with no loopback URLs.
4. The camera capture journey works over HTTPS: preview, Start, durably ACKed
   synthetic fragments on the distinct fragment endpoint, Stop, Saved.
5. A phone-sized viewport keeps the capture controls usable.

Synthetic devices/media only. Reports PASS/FAIL checks to
`mobile_lan_access_report.json`.

Environment:
- ZMI_BASE_URL: dashboard base URL (default https://127.0.0.1:5001)
- ZMI_EXPECT_LAN: "1" to require /api/network to report LAN mode enabled.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "https://127.0.0.1:5001").rstrip("/")
EXPECT_LAN = os.environ.get("ZMI_EXPECT_LAN", "") == "1"
TIMEOUT_MS = 30000
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


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

    all_ok = True
    api_requests: list[str] = []
    offsite_requests: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
            ],
        )
        # Local HTTPS uses the lan_access certificate; the phone trusts it via
        # the CA bundle (docs/ops/MOBILE_LAN_ACCESS.md). The headless e2e
        # context accepts the local certificate to exercise the HTTPS app path.
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            permissions=["camera"],
            ignore_https_errors=True,
        )
        page = context.new_page()

        browser_errors: list[str] = []
        page.on("console", lambda msg: browser_errors.append(f"console: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: browser_errors.append(f"pageerror: {exc}"))

        def _observe_request(req) -> None:
            if "/api/" not in req.url:
                return
            api_requests.append(req.url)
            if req.url.startswith(("http://127.0.0.1", "http://localhost", "https://localhost")):
                offsite_requests.append(req.url)

        page.on("request", _observe_request)

        try:
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)

            # 1. Served over HTTPS.
            all_ok &= check("dashboard_served_over_https", page.url.startswith("https://"), page.url)

            # 2. Backend health badge reports ONLINE via same-origin /api/health.
            page.wait_for_function(
                "document.getElementById('serverHealth').textContent === 'ONLINE'", timeout=TIMEOUT_MS
            )
            all_ok &= check(
                "header_health_online",
                page.locator("#serverHealth").inner_text().strip() == "ONLINE",
                page.locator("#serverHealth").inner_text(),
            )
            origin = page.evaluate("() => window.location.origin")
            all_ok &= check("origin_matches_base", DASHBOARD_URL.startswith(origin), f"origin={origin} base={DASHBOARD_URL}")
            health = page.evaluate(
                "async () => { const r = await fetch('/api/health'); return r.ok ? await r.json() : {status: null}; }"
            )
            all_ok &= check("same_origin_health_online", health.get("status") == "ONLINE", json.dumps(health))

            # 3. /api/network same-origin; LAN URLs never loopback.
            network = page.evaluate("async () => { const r = await fetch('/api/network'); return r.ok ? await r.json() : {}; }")
            all_ok &= check("network_reports_https", network.get("https") is True, json.dumps(network.get("https")))
            urls = network.get("urls") or []
            all_ok &= check(
                "network_urls_not_loopback",
                all("localhost" not in u and "127.0.0.1" not in u for u in urls),
                str(urls),
            )
            if EXPECT_LAN:
                all_ok &= check("lan_mode_enabled", network.get("lan_access") is True, json.dumps(network.get("lan_access")))
                all_ok &= check("lan_urls_advertised", len(urls) >= 1 and all(u.startswith("https://") for u in urls), str(urls))
                all_ok &= check(
                    "certificate_fingerprint_present",
                    bool(network.get("cert_fingerprint_sha256")),
                    str(network.get("cert_fingerprint_sha256")),
                )

            all_ok &= check("no_offsite_api_requests", not offsite_requests, "; ".join(offsite_requests[:3]))

            # 4. Camera capture journey over HTTPS with synthetic fragments.
            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)
            all_ok &= check("capture_preview_visible", page.locator("#capturePreview").is_visible())
            page.locator("#captureChunkDuration").fill("1")
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
            )
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot();"
                " return !!(s && s.ackedFragmentIds.length >= 1); }",
                timeout=TIMEOUT_MS,
            )
            acked = page.evaluate("() => window.__captureSnapshot()")
            all_ok &= check(
                "fragment_acked_over_https",
                len(acked.get("ackedFragmentIds") or []) >= 1,
                str(acked.get("ackedFragmentIds")),
            )
            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )
            all_ok &= check("capture_saved", page.locator("#captureState").inner_text() == "Saved")

            session_id = acked.get("sessionId")
            if session_id:
                server_fragments = requests.get(
                    f"{DASHBOARD_URL}/api/capture/sessions/{session_id}/fragments",
                    verify=False,
                    timeout=10,
                ).json().get("fragments", [])
                all_ok &= check(
                    "fragments_durable_on_server",
                    len(server_fragments) >= 1
                    and all(f.get("state") == "ACKED" and f.get("mediaSizeBytes", 0) > 0 for f in server_fragments),
                    json.dumps([{k: f.get(k) for k in ("fragmentId", "state", "mediaSizeBytes")} for f in server_fragments]),
                )

            # 5. Phone-sized viewport keeps the capture controls usable.
            all_ok &= check(
                "mobile_viewport_capture_controls",
                page.locator("#capturePreview").is_visible()
                and (page.locator("#captureStartBtn").is_visible() or page.locator("#captureStopBtn").is_visible()),
            )
        finally:
            all_ok &= check("no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000])
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("mobile_lan_access_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
