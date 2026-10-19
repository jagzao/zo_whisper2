"""Playwright workflow for temporal black trimming and separate border cropping.

Run only against scripts/e2e.py's isolated synthetic data root.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("ZMI_TEST_DATA_ROOT", "")).resolve()
SAFE_ROOT = (ROOT / "artifacts" / "gates" / "e2e-host-data").resolve()
BASE_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")


def _generate_black_clip(path: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=3",
            "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=4",
            "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10:d=3",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        capture_output=True, text=True, timeout=90, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])


def _generate_borders(path: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i",
            "color=c=black:s=160x120:r=10:d=4", "-vf",
            "drawbox=x=0:y=20:w=160:h=80:color=blue:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        capture_output=True, text=True, timeout=90, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])


def _run_button(page, name: str, button_name: str, copy_name: str) -> str:
    page.fill("#fileFilter", name)
    row = page.locator("#filesList tr").filter(has_text=name).first
    row.wait_for()
    messages = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.accept()))
    row.get_by_role("button", name=button_name).click(timeout=30_000)
    page.get_by_text(copy_name, exact=True).wait_for(timeout=120_000)
    return messages[0] if messages else ""


def _click_and_dismiss(page, name: str, button_name: str) -> str:
    page.fill("#fileFilter", name)
    row = page.locator("#filesList tr").filter(has_text=name).first
    row.wait_for()
    messages = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.dismiss()))
    row.get_by_role("button", name=button_name).click(timeout=30_000)
    page.wait_for_timeout(100)
    return messages[0] if messages else ""


def main() -> int:
    if DATA_ROOT != SAFE_ROOT or not (DATA_ROOT / "Videos").is_dir():
        raise RuntimeError("Refusing to write fixtures outside the isolated Host E2E data root")
    videos = DATA_ROOT / "Videos" / "general"
    videos.mkdir(parents=True, exist_ok=True)
    source = videos / "black_video_ui.mp4"
    border_source = videos / "black_borders_ui.mp4"
    outputs = [videos / "black_video_ui_trimmed.mp4", videos / "black_borders_ui_cropped.mp4"]
    try:
        _generate_black_clip(source)
        _generate_borders(border_source)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                permissions=["camera", "microphone"],
            )
            page = context.new_page()
            page.goto(BASE_URL, wait_until="commit", timeout=30_000)
            page.locator("#filesList").wait_for(timeout=60_000)
            page.locator("summary", has_text="Black video tools").click()
            page.locator("#autoRemoveBlack").check()
            page.locator("#blackDarknessThreshold").select_option("0.12")
            review = _click_and_dismiss(page, "black_video_ui.mp4", "Remove black sections")
            if "NEEDS_REVIEW" not in review:
                raise AssertionError("Low-confidence auto trim did not show NEEDS_REVIEW")
            if outputs[0].exists():
                raise AssertionError("Low-confidence auto trim produced a copy")
            page.locator("#autoRemoveBlack").uncheck()
            page.locator("#blackDarknessThreshold").select_option("0.05")

            canceled_preview = _click_and_dismiss(page, "black_video_ui.mp4", "Remove black sections")
            if "removed:" not in canceled_preview or not re.search(r"\d{2}:\d{2}:\d{2}–\d{2}:\d{2}:\d{2}", canceled_preview):
                raise AssertionError("Temporal preview did not show detected ranges and total removal")
            if outputs[0].exists():
                raise AssertionError("Cancel trim created a copy")
            accepted_preview = _run_button(page, "black_video_ui.mp4", "Remove black sections", "black_video_ui_trimmed.mp4")
            if "removed:" not in accepted_preview:
                raise AssertionError("Trim confirmation omitted the removed duration")

            crop_preview = _run_button(page, "black_borders_ui.mp4", "Crop black borders", "black_borders_ui_cropped.mp4")
            if "Create a separately cropped copy" not in crop_preview:
                raise AssertionError("Border crop confirmation was not shown")

            page.set_viewport_size({"width": 390, "height": 844})
            page.fill("#fileFilter", "black_video_ui.mp4")
            row = page.locator("#filesList tr").filter(has_text="black_video_ui.mp4").first
            mobile = page.evaluate("""() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth,
                cutVisible: [...document.querySelectorAll('#filesList button')].some(button => button.getAttribute('aria-label') === 'Remove black sections')})""")
            if mobile["documentWidth"] > mobile["width"] + 1 or not mobile["cutVisible"] or not row.is_visible():
                raise AssertionError(f"Black video controls fail mobile layout: {mobile}")

            page.locator("#newRecordingBtn").click()
            page.locator("#captureModal:not(.hidden)").wait_for()
            if page.locator("#captureAutoStopBlack").input_value() != "off":
                raise AssertionError("Black preview auto-stop must default Off")
            page.locator("#captureAutoStopBlack").select_option("30")
            page.evaluate("""async () => {
                const canvas = document.createElement('canvas');
                canvas.width = 160; canvas.height = 90;
                const ctx = canvas.getContext('2d');
                window.__setBlackPreview = color => {
                    ctx.fillStyle = color;
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                };
                window.__setBlackPreview('black');
                const stream = canvas.captureStream(10);
                const preview = document.querySelector('#capturePreview');
                preview.muted = true;
                preview.srcObject = stream;
                await preview.play();
                await new Promise(resolve => {
                    if (preview.readyState >= 2) return resolve();
                    preview.addEventListener('loadeddata', resolve, {once: true});
                });
                capture.state = 'recording';
                capture.captureKind = 'video';
                window.__blackTestStream = stream;
                window.__fakeNow = Date.now();
                Date.now = () => window.__fakeNow;
                const nativeClearInterval = window.clearInterval.bind(window);
                window.setInterval = callback => {
                    window.__blackMonitorTick = callback;
                    return 99173;
                };
                window.clearInterval = id => { if (id !== 99173) nativeClearInterval(id); };
                window.stopCapture = () => { window.__blackAutoStopCalled = true; };
                startBlackScreenMonitor();
            }""")
            tick = "window.__blackMonitorTick()"
            page.evaluate(tick)
            page.evaluate("window.__fakeNow += 30000")
            page.evaluate(tick)
            warning = page.locator("#captureBlackWarning")
            if "stop in 10 s" not in warning.inner_text():
                raise AssertionError("Black preview auto-stop did not show its 10 second warning")
            page.evaluate("window.__fakeNow += 5000")
            page.evaluate(tick)
            if "stop in 5 s" not in warning.inner_text():
                raise AssertionError("Black preview countdown did not update")
            page.evaluate("window.__setBlackPreview('white')")
            page.wait_for_timeout(300)
            page.evaluate(tick)
            if not warning.evaluate("el => el.classList.contains('hidden')"):
                raise AssertionError("Visible content did not cancel the black preview countdown")
            page.evaluate("window.__setBlackPreview('black')")
            page.wait_for_timeout(300)
            page.evaluate(tick)
            page.evaluate("window.__fakeNow += 30000")
            page.evaluate(tick)
            page.evaluate("window.__fakeNow += 10000")
            page.evaluate(tick)
            if not page.evaluate("window.__blackAutoStopCalled === true"):
                raise AssertionError("Black preview auto-stop did not stop after the warning countdown")
            page.evaluate("""() => {
                clearInterval(99173);
                window.__blackTestStream.getTracks().forEach(track => track.stop());
                document.querySelector('#capturePreview').srcObject = null;
                capture.state = 'idle';
            }""")

            mobile_capture = page.evaluate("""() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth,
                modalWidth: document.querySelector('#captureModal .capture-modal').clientWidth,
                warningWidth: document.querySelector('#captureBlackWarning').getBoundingClientRect().width,
                selectorVisible: document.querySelector('#captureAutoStopBlack').getBoundingClientRect().width > 0})""")
            if mobile_capture["documentWidth"] > mobile_capture["width"] + 1 or not mobile_capture["selectorVisible"]:
                raise AssertionError(f"Black stop controls fail mobile layout: {mobile_capture}")
            page.screenshot(path=str(DATA_ROOT / "black-video-tools.png"), full_page=True)
            context.close()
            browser.close()
        assert all(path.is_file() and path.stat().st_size > 0 for path in outputs)
        print(json.dumps({"status": "PASS", "checks": ["temporal preview", "trim cancel/confirm", "low-confidence review", "border crop", "auto-stop warning/cancel", "mobile layout", "originals retained"]}))
        return 0
    finally:
        for path in [*outputs, source, border_source]:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
