"""Verify the visible Capture UI and revision on desktop and HTTPS LAN serves."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


EXPECTED = os.environ.get("WHISPER_EXPECTED_REVISION", "").strip()
TARGETS = {
    "desktop": os.environ.get("ZMI_DESKTOP_URL", "http://localhost:5000"),
    "lan": os.environ.get("ZMI_LAN_URL", "https://192.168.50.67:5001"),
}


def main() -> int:
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for name, url in TARGETS.items():
            page = browser.new_page(viewport={"width": 390, "height": 844}, ignore_https_errors=True)
            response = requests.get(url, timeout=20, verify=False)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#buildVersion", timeout=15000)
            revision = page.locator('meta[name="whisper-build"]').get_attribute("content")
            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)")
            modes = {
                "camera": page.locator("#captureInputCamera").inner_text(),
                "audio": page.locator("#captureInputAudio").inner_text(),
                "camera_visible": page.locator("#captureInputCamera").is_visible(),
                "audio_visible": page.locator("#captureInputAudio").is_visible(),
                "rear_default": page.locator("#captureCameraFacing").input_value() == "environment",
                "get_user_media": page.evaluate("() => !!navigator.mediaDevices?.getUserMedia"),
                "offline": page.locator("#captureOfflineBadge").is_visible() if page.locator("#captureOfflineBadge").count() else False,
                "document_width": page.evaluate("() => document.documentElement.scrollWidth"),
                "viewport_width": page.evaluate("() => innerWidth"),
                "service_workers": page.evaluate("async () => (await navigator.serviceWorker.getRegistrations()).length"),
            }
            results[name] = {
                "http_status": response.status_code,
                "header_revision": response.headers.get("X-Whisper-Build"),
                "html_revision": revision,
                "expected_revision": EXPECTED,
                "modes": modes,
                "pass": response.status_code == 200
                and (not EXPECTED or revision == EXPECTED)
                and response.headers.get("X-Whisper-Build") == revision
                and modes["camera_visible"] and modes["audio_visible"]
                and "Camera" in modes["camera"] and "Audio" in modes["audio"]
                and modes["rear_default"] and modes["get_user_media"]
                and modes["document_width"] <= modes["viewport_width"] + 1
                and modes["service_workers"] == 0,
            }
            page.locator("#captureModal .close-x").click()
            page.close()
        browser.close()

    target = Path("artifacts/gates/live-capture-finalization")
    target.mkdir(parents=True, exist_ok=True)
    (target / "served_ui_revision.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0 if all(value["pass"] for value in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
