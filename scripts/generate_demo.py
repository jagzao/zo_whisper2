"""Generates the LinkedIn demo MP4 for the community launch (Task E).

Drives the REAL dashboard UI with Playwright through a synthetic journey
(Option B: docs/assets/generate_mock_data.py mock data — never real client
data), capturing one full-page screenshot per step, then assembles them with
FFmpeg into docs/marketing/zo-whisper-studio-linkedin-demo.mp4.

The journey is real UI + real pipeline steps: home, RUN Full (the pipeline
skips the already-processed mock files, so it completes fast), the tutorial
file's transcript with timestamp + frame, its keyframes, the DOCS tab's
evidence source badges, the generated MANUAL.md steps, and the AI package.

Marketing overlays are burned in with FFmpeg drawtext on the intro, evidence,
and final frames.

Run:
    python scripts/generate_demo.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "marketing" / "zo-whisper-studio-linkedin-demo.mp4"
DASHBOARD_URL = "http://127.0.0.1:5000"
PYTHON = sys.executable
TIMEOUT_MS = 30000
WIDTH, HEIGHT = 1920, 1080
FONT = "C\\:/Windows/Fonts/arial.ttf"

# (screenshot name, seconds shown, drawtext overlay or None)
# Durations sum to ~38s (within the 35-50s target).
STEPS: list[tuple[str, float, str | None]] = [
    ("01_home_intro.png", 5.0, "A screen recording contains more knowledge than its transcript."),
    ("02_home.png", 4.0, None),
    ("03_run_full.png", 3.0, None),
    ("04_pipeline_progress.png", 3.0, None),
    ("05_transcript.png", 4.0, None),
    ("06_frames.png", 3.0, None),
    ("07_evidence.png", 4.0, "Speech + screen evidence \u2192 grounded documentation"),
    ("08_docs_manual.png", 4.0, None),
    ("09_ai_package.png", 3.0, None),
    ("10_final.png", 5.0, "Zo Whisper Studio\nLocal-first. Grounded. AI-ready."),
]

# A name substring only the mock-data generator's synthetic files match, so
# the home/file-list frames show no real client rows.
SYNTHETIC_FILTER = "northwind"


def _server_cmd() -> list[str]:
    return [PYTHON, str(ROOT / "dashboard.py")]


def _wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(DASHBOARD_URL, timeout=1.0) as _:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _drain_output(stream, sink: list[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
    except (ValueError, OSError):
        pass


def _ensure_mock_data() -> None:
    subprocess.run(
        [PYTHON, str(ROOT / "docs" / "assets" / "generate_mock_data.py")],
        cwd=str(ROOT), check=True, capture_output=True, text=True, timeout=300,
    )


def _find_tutorial_file(page) -> dict:
    files = page.evaluate("() => window._allFiles")
    for f in files:
        if (f.get("documentation") or {}).get("has_manual"):
            return f
    raise RuntimeError("no file with generated documentation found")


def _open_workspace(page, file_info: dict, tab: str) -> None:
    tx = file_info.get("transcription") or {}
    page.evaluate(
        "([mid, tid]) => preview(encodeURIComponent(mid), tid ? encodeURIComponent(tid) : '', false)",
        [file_info["media_id"], tx.get("id", "")],
    )
    page.wait_for_selector("#previewModal:not(.hidden)", timeout=TIMEOUT_MS)
    page.wait_for_timeout(800)
    page.locator(f"#tab{tab}").click()
    page.wait_for_timeout(1200)


def _capture(page, name: str, out_dir: Path) -> Path:
    path = out_dir / name
    page.screenshot(path=str(path), full_page=False)
    return path


def _drawtext(text: str, *, y: str, fontsize: int = 44) -> str:
    """Builds a single drawtext filter for `text` (may contain \n for a
    second line) centered horizontally at vertical position `y`."""
    lines = text.split("\n")
    filters = []
    for i, line in enumerate(lines):
        escaped = line.replace(":", "\\:").replace("'", "\\'").replace("\\", "\\\\")
        line_y = f"{y}+{i * (fontsize + 14)}" if i else y
        filters.append(
            f"drawtext=fontfile='{FONT}':text='{escaped}':fontcolor=white:"
            f"fontsize={fontsize}:box=1:boxcolor=black@0.55:boxborderw=18:"
            f"x=(w-text_w)/2:y={line_y}"
        )
    return ",".join(filters)


def _assemble(frames: list[tuple[Path, float, str | None]], out_path: Path) -> None:
    """Concatenates the per-step screenshots into the final H.264 MP4,
    scaling each to 1920x1080 and burning in the per-step drawtext overlay."""
    inputs: list[str] = []
    for path, dur, _ in frames:
        inputs += ["-loop", "1", "-t", str(dur), "-i", str(path)]

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for i, (_, _, overlay) in enumerate(frames):
        chain = (
            f"[{i}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
        if overlay:
            chain += "," + _drawtext(overlay, y="h-160")
        chain += f"[v{i}]"
        filter_parts.append(chain)
        concat_inputs.append(f"[v{i}]")

    filter_parts.append(
        "".join(concat_inputs) + f"concat=n={len(frames)}:v=1:a=0[outv]"
    )

    cmd = (
        ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filter_parts),
         "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", "30", "-movflags", "+faststart", str(out_path)]
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-3000:]}")


def main() -> int:
    _ensure_mock_data()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")

    server = subprocess.Popen(
        _server_cmd(), cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    server_output: list[str] = []
    threading.Thread(target=_drain_output, args=(server.stdout, server_output), daemon=True).start()

    tmp = Path(tempfile.mkdtemp(prefix="zo_demo_"))
    try:
        if not _wait_for_server():
            print("[FAIL] dashboard did not start", file=sys.stderr)
            return 1

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.on("dialog", lambda d: d.accept())
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
            page.wait_for_timeout(1500)

            # Home (filtered to synthetic) — intro + home frames.
            page.locator("#fileFilter").fill(SYNTHETIC_FILTER)
            page.wait_for_timeout(800)
            _capture(page, "01_home_intro.png", tmp)
            _capture(page, "02_home.png", tmp)

            # RUN Full — real pipeline run; the already-processed mock files
            # are skipped so it completes fast. Capture the stepper right
            # after clicking (running state) and again after it finishes.
            page.locator("#btnRunFull").click()
            page.wait_for_timeout(400)
            _capture(page, "03_run_full.png", tmp)
            page.wait_for_timeout(2500)
            _capture(page, "04_pipeline_progress.png", tmp)

            # Tutorial workspace: transcript (timestamp + frame), frames,
            # then DOCS evidence / manual / AI package.
            tutorial = _find_tutorial_file(page)
            _open_workspace(page, tutorial, "Transcript")
            page.locator("#transcriptList .segment").first.click()
            page.wait_for_timeout(1200)
            _capture(page, "05_transcript.png", tmp)

            page.locator("#tabFrames").click()
            page.wait_for_timeout(1500)
            _capture(page, "06_frames.png", tmp)

            page.locator("#tabDocs").click()
            page.wait_for_timeout(1500)
            page.wait_for_selector("#docsContent .doc-step", timeout=TIMEOUT_MS)
            page.wait_for_timeout(800)
            _capture(page, "07_evidence.png", tmp)
            _capture(page, "08_docs_manual.png", tmp)

            # AI package summary is at the top of docsContent — scroll back up.
            page.evaluate("() => document.getElementById('docsContent').scrollTop = 0")
            page.wait_for_timeout(600)
            _capture(page, "09_ai_package.png", tmp)

            # Final frame: back to the clean home view.
            page.locator("#previewModal .close-x").click()
            page.wait_for_selector("#previewModal.hidden", state="hidden", timeout=TIMEOUT_MS)
            page.wait_for_timeout(500)
            _capture(page, "10_final.png", tmp)

            browser.close()

        frames = [(tmp / name, dur, overlay) for name, dur, overlay in STEPS]
        for path, _, _ in frames:
            if not path.exists():
                raise RuntimeError(f"missing screenshot: {path}")
        _assemble(frames, OUT_PATH)
        print(f"[OK] demo video: {OUT_PATH}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())