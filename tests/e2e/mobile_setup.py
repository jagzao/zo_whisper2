"""Browser check for the first-run phone setup and desktop QR card."""
from __future__ import annotations

import dataclasses
import json
import os
import socket
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "artifacts" / "gates" / "mobile-setup-playwright-data"
REPORT = ROOT / "artifacts" / "gates" / "mobile-setup-playwright.json"
os.environ["ZMI_DATA_ROOT"] = str(DATA)
sys.path.insert(0, str(ROOT / "src"))

from transcript_pipeline import lan_access  # noqa: E402
from transcript_pipeline.dashboard import app as dashboard  # noqa: E402
from transcript_pipeline.settings import SETTINGS  # noqa: E402


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    lan_access.provision_lan_certificate(DATA / "lan-access", ["127.0.0.1"])
    dashboard.SETTINGS = dataclasses.replace(SETTINGS, lan_access=True, lan_hosts=("127.0.0.1",))
    dashboard._LAN_HOST_ALLOWLIST.update({"127.0.0.1"})
    lan_access.local_ipv4_addresses = lambda: ["127.0.0.1"]
    lan_access.advertised_lan_ipv4_addresses = lambda configured=(): ["127.0.0.1"]
    is_private_ipv4 = lan_access.is_private_ipv4
    lan_access.is_private_ipv4 = lambda value: value == "127.0.0.1" or is_private_ipv4(value)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = make_server("127.0.0.1", port, dashboard.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1360, "height": 900}, accept_downloads=True)
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            base = f"http://127.0.0.1:{port}"
            page.goto(base, wait_until="domcontentloaded")
            card = page.locator("#mobileSetupCard")
            card.wait_for(state="visible")
            if "http://127.0.0.1:5000/setup" not in card.inner_text():
                raise AssertionError("Desktop QR card shows the wrong bootstrap URL")
            if not page.locator("#mobileSetupCard img").evaluate("img => img.complete && img.naturalWidth > 0"):
                raise AssertionError("Desktop QR image did not render")
            checks.append("desktop QR points to /setup")
            page.get_by_role("button", name="Dismiss").click()
            page.reload(wait_until="domcontentloaded")
            if page.locator("#mobileSetupCard").count():
                raise AssertionError("Dismissed onboarding returned in this browser")
            checks.append("desktop dismissal persists")

            page.goto(f"{base}/setup", wait_until="domcontentloaded")
            if f"https://127.0.0.1:5001/" not in page.locator("a.secure").get_attribute("href"):
                raise AssertionError("Secure link has the wrong HTTPS port")
            if "Settings" not in page.locator("main").inner_text():
                raise AssertionError("Android installation steps are missing")
            page.set_viewport_size({"width": 390, "height": 844})
            if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                raise AssertionError("Mobile setup page overflows horizontally")
            if not page.get_by_role("link", name="Open Whisper securely").is_visible():
                raise AssertionError("Secure link is not visible on mobile")
            checks.append("mobile setup layout and secure CTA")
            with page.expect_download() as download_info:
                page.get_by_role("link", name="Install Whisper certificate").click()
            download = download_info.value
            if download.suggested_filename != "Whisper-LAN-Local-CA.cer":
                raise AssertionError("Wrong certificate download filename")
            downloaded = Path(download.path()).read_bytes()
            from cryptography import x509

            x509.load_der_x509_certificate(downloaded)
            if b"PRIVATE KEY" in downloaded:
                raise AssertionError("Certificate download contained private-key text")
            checks.append("public CA download and Android instructions")
            if errors:
                raise AssertionError(f"Browser errors: {errors}")
            page.screenshot(path=str(ROOT / "artifacts" / "gates" / "mobile-setup-playwright.png"), full_page=True)
            browser.close()
        report = {"status": "PASS", "checks": checks}
    except Exception as exc:  # noqa: BLE001
        report = {"status": "FAIL", "checks": checks, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
