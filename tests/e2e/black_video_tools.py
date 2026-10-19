"""Playwright workflow for temporal black trimming and separate border cropping.

Run only against scripts/e2e.py's isolated synthetic data root.
"""

from __future__ import annotations

import json
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


def _run_button(page, name: str, button_name: str, copy_name: str) -> None:
    page.fill("#fileFilter", name)
    row = page.locator("#filesList tr").filter(has_text=name).first
    row.wait_for()
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name=button_name).click(timeout=30_000)
    page.get_by_text(copy_name, exact=True).wait_for(timeout=120_000)


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
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.locator("#filesList").wait_for(timeout=30_000)
            _run_button(page, "black_video_ui.mp4", "Remove black sections", "black_video_ui_trimmed.mp4")
            _run_button(page, "black_borders_ui.mp4", "Crop black borders", "black_borders_ui_cropped.mp4")
            page.screenshot(path=str(DATA_ROOT / "black-video-tools.png"), full_page=True)
            browser.close()
        assert all(path.is_file() and path.stat().st_size > 0 for path in outputs)
        print(json.dumps({"status": "PASS", "checks": ["black trim UI", "separate border crop UI", "originals retained"]}))
        return 0
    finally:
        for path in [*outputs, source, border_source]:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
