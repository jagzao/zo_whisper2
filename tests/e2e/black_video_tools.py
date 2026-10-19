"""Playwright workflow for temporal black trimming and separate border cropping.

Run only against scripts/e2e.py's isolated synthetic data root.
"""

from __future__ import annotations

import json
import hashlib
import os
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


def main() -> int:
    if DATA_ROOT != SAFE_ROOT or not (DATA_ROOT / "Videos").is_dir():
        raise RuntimeError("Refusing to write fixtures outside the isolated Host E2E data root")
    videos = DATA_ROOT / "Videos" / "general"
    videos.mkdir(parents=True, exist_ok=True)
    source = videos / "black_video_ui.mp4"
    border_source = videos / "black_borders_ui.mp4"
    outputs = [videos / "black_video_ui_edited.mp4", videos / "black_borders_ui_edited.mp4"]
    sidecars = [output.with_suffix(".provenance.json") for output in outputs]
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
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(BASE_URL, wait_until="commit", timeout=30_000)
            page.locator("#filesList").wait_for(timeout=60_000)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            page.fill("#fileFilter", source.name)
            row = page.locator("#filesList tr").filter(has_text=source.name).first
            row.get_by_role("button", name="Edit video").click()
            modal = page.locator("#videoTrimModal:not(.hidden)")
            modal.wait_for()
            page.wait_for_function("document.querySelector('#videoTrimPlayer').readyState >= 1")
            page.wait_for_function("document.querySelectorAll('#videoTrimCuts .video-trim-cut').length > 0")
            if page.locator("#videoTrimPlayer").evaluate("video => video.duration") < 9:
                raise AssertionError("Editor preview did not load the source video")
            page.locator("#videoTrimSeek").fill("1.2")
            page.wait_for_function("Math.abs(document.querySelector('#videoTrimPlayer').currentTime - 1.2) < 0.2")
            page.locator("#videoTrimPlayButton").click()
            page.wait_for_function("document.querySelector('#videoTrimPlayer').currentTime > 1.25")
            page.locator("#videoTrimPlayButton").click()
            detected = page.locator("#videoTrimCuts .video-trim-cut").first
            detected.get_by_role("checkbox").check()
            original_removed = page.locator("#videoTrimRemoved").inner_text()
            detected.locator("input[type=number]").nth(1).fill("6.5")
            detected.locator("input[type=number]").nth(1).press("Tab")
            if page.locator("#videoTrimRemoved").inner_text() == original_removed:
                raise AssertionError("Changing a cut range did not update the edit summary")
            detected.get_by_role("checkbox").uncheck()
            page.locator("#videoTrimManualStart").fill("0.5")
            page.locator("#videoTrimManualEnd").fill("1.5")
            page.get_by_role("button", name="Add cut").click()
            if page.locator("#videoTrimCuts .video-trim-cut").count() != 2:
                raise AssertionError("Manual cut range was not added")
            page.locator("#videoTrimStart").fill("0.25")
            page.screenshot(path=str(DATA_ROOT / "video-trim-editor.png"), full_page=True)
            page.get_by_role("button", name="Preview", exact=True).click()
            page.wait_for_timeout(250)
            page.get_by_role("button", name="Reset", exact=True).click()
            if page.locator("#videoTrimStart").input_value() != "0" or page.locator("#videoTrimCuts .video-trim-cut").count() != 1:
                raise AssertionError("Reset did not restore the detected edit state")
            if outputs[0].exists():
                raise AssertionError("Opening or previewing the editor created media")
            page.set_viewport_size({"width": 390, "height": 844})
            mobile = page.evaluate("""() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth,
                modalWidth: document.querySelector('#videoTrimModal .modal').getBoundingClientRect().width})""")
            if mobile["documentWidth"] > mobile["width"] + 1:
                raise AssertionError(f"Video editor overflows mobile layout: {mobile}")
            page.get_by_role("button", name="Cancel", exact=True).click()
            if outputs[0].exists() or hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
                raise AssertionError("Cancel changed source media or created an output")

            page.set_viewport_size({"width": 1280, "height": 900})
            page.fill("#fileFilter", source.name)
            page.locator("#filesList tr").filter(has_text=source.name).first.get_by_role("button", name="Edit video").click()
            page.locator("#videoTrimModal:not(.hidden)").wait_for()
            page.wait_for_function("document.querySelectorAll('#videoTrimCuts .video-trim-cut').length > 0")
            page.wait_for_function("!document.querySelector('#videoTrimStatus').textContent.startsWith('Scanning')")
            page.get_by_role("button", name="Apply changes").click()
            page.fill("#fileFilter", "")
            try:
                page.get_by_text(outputs[0].name, exact=True).wait_for(timeout=45_000)
            except Exception as exc:
                raise AssertionError(
                    f"Trim output missing; modal={modal.is_visible()}, "
                    f"status={page.locator('#videoTrimStatus').inner_text()!r}, "
                    f"toast={page.locator('#toast').inner_text()!r}, page_errors={page_errors}"
                ) from exc
            if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash or not sidecars[0].is_file():
                raise AssertionError("Apply failed source preservation or edit provenance")

            border_hash = hashlib.sha256(border_source.read_bytes()).hexdigest()
            page.fill("#fileFilter", border_source.name)
            page.locator("#filesList tr").filter(has_text=border_source.name).first.get_by_role("button", name="Edit video").click()
            page.locator("#videoTrimModal:not(.hidden)").wait_for()
            page.get_by_role("tab", name="FRAME").click()
            page.get_by_role("button", name="Auto detect black borders").click()
            page.wait_for_function("document.querySelector('#videoTrimStatus').textContent.startsWith('Border suggestion')")
            page.wait_for_function("document.querySelector('#videoCropWidth').value !== ''")
            crop_width = int(page.locator("#videoCropWidth").input_value())
            crop_height = int(page.locator("#videoCropHeight").input_value())
            page.locator("#videoCropX").fill("2")
            page.get_by_role("button", name="Preview crop").click()
            if page.locator("#videoCropBox").is_visible():
                raise AssertionError("Crop preview did not switch to the cropped frame")
            page.get_by_role("button", name="Reset crop").click()
            if page.locator("#videoCropWidth").input_value() != "160":
                raise AssertionError("Reset crop did not restore the full frame")
            page.get_by_role("button", name="Auto detect black borders").click()
            page.wait_for_function("document.querySelector('#videoTrimStatus').textContent.startsWith('Border suggestion')")
            page.get_by_role("button", name="Apply changes").click()
            page.fill("#fileFilter", "")
            page.get_by_text(outputs[1].name, exact=True).wait_for(timeout=120_000)
            if hashlib.sha256(border_source.read_bytes()).hexdigest() != border_hash or not sidecars[1].is_file():
                raise AssertionError("Crop apply changed the original or omitted provenance")
            if crop_width >= 160 and crop_height >= 90:
                raise AssertionError("Synthetic border fixture did not produce a crop")

            page.locator("#newRecordingBtn").click()
            page.locator("#captureModal:not(.hidden)").wait_for()
            if page.locator("#captureAutoStopBlack").input_value() != "off":
                raise AssertionError("Black preview auto-stop must default Off")
            page.locator("#captureAutoStopBlack").select_option("30")
            page.evaluate("""async () => {
                const preview = document.querySelector('#capturePreview');
                Object.defineProperties(preview, {
                    readyState: {configurable: true, value: 2},
                    videoWidth: {configurable: true, value: 160},
                    videoHeight: {configurable: true, value: 90},
                });
                const originalGetContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, options) {
                    const context = originalGetContext.call(this, type, options);
                    if (this.width === 32 && this.height === 18 && context) {
                        context.drawImage = () => {};
                        context.getImageData = () => {
                            const data = new Uint8ClampedArray(32 * 18 * 4);
                            for (let i = 0; i < data.length; i += 4) {
                                const value = window.__blackFrameDark ? 0 : 255;
                                data[i] = data[i + 1] = data[i + 2] = value;
                                data[i + 3] = 255;
                            }
                            return {data};
                        };
                    }
                    return context;
                };
                window.__blackFrameDark = true;
                capture.state = 'recording';
                capture.captureKind = 'video';
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
            page.evaluate("window.__blackFrameDark = false")
            page.evaluate(tick)
            if not warning.evaluate("el => el.classList.contains('hidden')"):
                raise AssertionError("Visible content did not cancel the black preview countdown")
            page.evaluate("window.__blackFrameDark = true")
            page.evaluate(tick)
            page.evaluate("window.__fakeNow += 30000")
            page.evaluate(tick)
            page.evaluate("window.__fakeNow += 10000")
            page.evaluate(tick)
            if not page.evaluate("window.__blackAutoStopCalled === true"):
                raise AssertionError("Black preview auto-stop did not stop after the warning countdown")
            page.evaluate("""() => {
                clearInterval(99173);
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
        print(json.dumps({"status": "PASS", "checks": ["video player and seek", "detected and manual cuts", "deselect and edit range", "manual trim", "result preview", "reset and cancel", "combined border crop preview", "validated apply and provenance", "auto-stop warning/cancel", "mobile layout", "originals retained"], "screenshot": "video-trim-editor.png"}))
        return 0
    finally:
        for path in [*outputs, *sidecars, source, border_source]:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
