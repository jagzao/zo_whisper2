"""W6 browser crop-selection smoke test using Playwright + fake media devices.

Opens the dashboard, opens the Live Capture modal, draws a normalized crop
region over the camera preview, verifies it round-trips into the created
session manifest, and verifies clear/reset. No real camera or media â€” Chromium
is launched with deterministic fake devices and granted camera permission.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
TIMEOUT_MS = 30000
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def _sessions() -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/capture/sessions", timeout=10)
    r.raise_for_status()
    return r.json().get("sessions", [])


def _close_safely(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def _snapshot_crop(page):
    return page.evaluate("() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return s ? s.crop : undefined; }")


def _drag_crop(page):
    box = page.locator("#cropOverlay").bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0, "crop overlay has no size"
    start = (box["x"] + box["width"] * 0.25, box["y"] + box["height"] * 0.25)
    end = (box["x"] + box["width"] * 0.75, box["y"] + box["height"] * 0.75)
    page.mouse.move(start[0], start[1])
    page.mouse.down()
    page.mouse.move(end[0], end[1], steps=6)
    page.mouse.up()


def _valid_region(crop) -> bool:
    if not isinstance(crop, dict):
        return False
    for key in ("x", "y", "width", "height"):
        if not isinstance(crop.get(key), (int, float)):
            return False
    x, y, w, h = crop["x"], crop["y"], crop["width"], crop["height"]
    return (
        0.0 <= x <= 1.0
        and 0.0 <= y <= 1.0
        and 0.0 < w <= 1.0
        and 0.0 < h <= 1.0
        and x + w <= 1.0001
        and y + h <= 1.0001
    )


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return 1

    sessions_before = {s["sessionId"] for s in _sessions()}
    all_ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            permissions=["camera"],
        )
        page = context.new_page()

        browser_errors: list[str] = []
        page.on("console", lambda msg: browser_errors.append(f"console: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: browser_errors.append(f"pageerror: {exc}"))

        try:
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
            page.locator('button[aria-label="Capture"]').click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording' && document.getElementById('capturePreview').videoWidth > 0",
                timeout=TIMEOUT_MS,
            )

            # 1. Draw a crop region over the preview overlay.
            _drag_crop(page)
            crop = _snapshot_crop(page)
            all_ok &= check("crop_region_selected", _valid_region(crop), json.dumps(crop))

            # 2. Clear/reset removes the region.
            page.locator("#cropClearBtn").click()
            page.wait_for_function("() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return !!(s && s.crop === null); }", timeout=TIMEOUT_MS)
            all_ok &= check("crop_cleared", _snapshot_crop(page) is None, json.dumps(_snapshot_crop(page)))

            # 3. Re-select and start capture so the crop persists with the session.
            _drag_crop(page)
            crop = _snapshot_crop(page)
            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )

            sessions_after = _sessions()
            new_sessions = [s for s in sessions_after if s["sessionId"] not in sessions_before]
            all_ok &= check("crop_session_created", len(new_sessions) == 1, f"{len(new_sessions)} new sessions")
            if new_sessions:
                persisted = new_sessions[0].get("crop")
                all_ok &= check("crop_persisted_roundtrip", persisted == crop, f"snapshot={crop} persisted={persisted}")
        finally:
            all_ok &= check("crop_no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000])
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_crop_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
