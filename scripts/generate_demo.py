"""Generates the LinkedIn demo MP4 for the community launch.

Drives the REAL dashboard UI with Playwright through a live journey — uploads
the synthetic demo video, runs the real pipeline to completion (faster-whisper
transcription + keyframes + documentation incl. MANUAL.pdf), then walks the
transcript, frame/timestamp evidence, OCR evidence, DOCS tab, MANUAL.pdf
download, and the AI package. The whole session is recorded with
page.screencast() (falling back to per-phase screenshots), then edited with
FFmpeg: per-phase trim + setpts speedup (dead pipeline time compressed),
concat, and drawtext marketing overlays.

All data is synthetic (scripts/generate_demo_video.py) — never real client
data, never personal paths, never secrets.

Output: docs/marketing/zo-media-intelligence-linkedin-demo.mp4

Run:
    python scripts/generate_demo.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "marketing" / "zo-media-intelligence-linkedin-demo.mp4"
DEMO_VIDEO = ROOT / "demo" / "en_demo_zo_media_intelligence_tutorial.mp4"


def _find_free_port() -> int:
    """Binds an ephemeral port so the demo never collides with a dashboard
    already running on the default 5000 — a stale dashboard there would make
    RUN Full appear disabled (its _run_state["running"]=True) and stall the
    journey for the full pipeline timeout."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _find_free_port()
DASHBOARD_URL = f"http://127.0.0.1:{PORT}"
PYTHON = sys.executable
TIMEOUT_MS = 30000
WIDTH, HEIGHT = 1920, 1080
FONT = "C\\:/Windows/Fonts/arial.ttf"
PIPELINE_TIMEOUT_S = 10 * 60

# The real workspace is moved aside for the run so RUN Full only ever sees
# the synthetic demo video — never the 50 real client files (which would
# blow the pipeline timeout and leak client data into the demo).
WORKSPACE_DIRS = ["Videos", "audio", "Video_compress", "CarpetaTranscripciones"]
WORKSPACE_FILES = ["processed_files.json"]

# (phase name, target final duration in seconds) — the journey marks each
# phase boundary in wall time; the edit compresses each phase to its target.
PHASES: list[tuple[str, float]] = [
    ("intro", 4.0),
    ("upload", 4.0),
    ("run", 3.0),
    ("wait", 12.0),
    ("transcript", 5.0),
    ("frames", 4.0),
    ("docs", 5.0),
    ("pdf", 5.0),
    ("ai", 4.0),
    ("final", 4.0),
]

OVERLAYS: dict[str, str] = {
    "intro": "A screen recording contains more knowledge than its transcript.",
    "docs": "Speech + screen evidence \u2192 grounded documentation",
    "final": "Zo Media Intelligence\nLocal-first. Grounded. AI-ready.",
}


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


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}:\n{result.stderr[-1000:]}")
    return float(json.loads(result.stdout)["format"]["duration"])


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


def _upload_demo_video(page) -> None:
    """Uploads the synthetic demo MP4 via the dashboard's file input, retrying
    the known local ffprobe-validation flake (exit 3221225794) up to 3 times."""
    for attempt in range(3):
        page.locator("#fileInput").evaluate("el => { el.value = ''; }")
        page.set_input_files("#fileInput", str(DEMO_VIDEO))
        try:
            page.wait_for_function(
                "document.getElementById('uploadQueue').innerText.includes('OK') || "
                "document.getElementById('uploadQueue').innerText.includes('Error')",
                timeout=20000,
            )
        except Exception:
            continue
        queue_text = page.locator("#uploadQueue").inner_text(timeout=5000)
        if "OK" in queue_text:
            return
        print(f"[RETRY] upload attempt {attempt + 1} failed: {queue_text[:120]}")
        page.wait_for_timeout(1500)
    raise RuntimeError("upload failed after 3 attempts")


def _wait_for_pipeline(page, tmp: Path, shots: list[tuple[Path, float]]) -> None:
    """Polls /api/status until the real pipeline run finishes, capturing a
    screenshot per poll so the fallback edit still shows progress."""
    deadline = time.time() + PIPELINE_TIMEOUT_S
    while time.time() < deadline:
        try:
            status = requests.get(f"{DASHBOARD_URL}/api/status", timeout=10).json()
        except Exception:
            status = {"running": True}
        if not status.get("running"):
            if status.get("error"):
                raise RuntimeError(f"pipeline failed: {status['error']}")
            return
        shot = tmp / f"shot_{len(shots):03d}.png"
        try:
            page.screenshot(path=str(shot))
            shots.append((shot, time.time()))
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError(f"pipeline did not finish within {PIPELINE_TIMEOUT_S // 60} minutes")


def _find_demo_file(page) -> dict:
    files = page.evaluate("() => window._allFiles")
    target = next((f for f in files if f.get("name") == DEMO_VIDEO.name), None)
    if target is None:
        target = next((f for f in files if (f.get("documentation") or {}).get("has_manual")), None)
    if target is None:
        raise RuntimeError(f"processed demo file {DEMO_VIDEO.name} not found in dashboard")
    return target


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


def _journey(page, tmp: Path) -> tuple[list[tuple[str, float]], list[tuple[Path, float]]]:
    """Runs the live journey, returning (phase boundaries, fallback screenshots)."""
    phases: list[tuple[str, float]] = []
    shots: list[tuple[Path, float]] = []

    def _mark(name: str) -> None:
        phases.append((name, time.time()))
        shot = tmp / f"shot_{len(shots):03d}.png"
        try:
            page.screenshot(path=str(shot))
            shots.append((shot, time.time()))
        except Exception:
            pass

    # 1. Home — the dashboard's file browser.
    page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
    page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
    page.wait_for_timeout(1500)
    _mark("intro")
    page.wait_for_timeout(3000)

    # 2. Upload the synthetic demo video.
    _upload_demo_video(page)
    _mark("upload")
    page.wait_for_timeout(3000)

    # 3. RUN Full — the real pipeline (compress → transcribe → keyframes → docs).
    page.locator("#btnRunFull").click()
    _mark("run")
    page.wait_for_timeout(3000)

    # 4. Poll the real pipeline to completion.
    _wait_for_pipeline(page, tmp, shots)
    _mark("wait")
    page.wait_for_timeout(1500)

    # 5. Transcript — timestamped segments; click one to seek + show its frame.
    demo_file = _find_demo_file(page)
    _open_workspace(page, demo_file, "Transcript")
    page.locator("#transcriptList .segment").first.click()
    page.wait_for_timeout(1500)
    _mark("transcript")
    page.wait_for_timeout(3000)

    # 6. Frame/timestamp evidence.
    page.locator("#tabFrames").click()
    page.wait_for_timeout(1500)
    _mark("frames")
    page.wait_for_timeout(3000)

    # 7. DOCS tab — manual steps with evidence-source badges (transcript /
    #    transcript_ocr / ocr). Scroll an OCR-grounded step into view.
    page.locator("#tabDocs").click()
    page.wait_for_timeout(1500)
    page.wait_for_selector("#docsContent .doc-step", timeout=TIMEOUT_MS)
    page.wait_for_timeout(800)
    page.evaluate(
        """() => {
            const steps = document.querySelectorAll('#docsContent .doc-step');
            for (const s of steps) {
                const badge = s.querySelector('.doc-step-header .status');
                if (badge && /ocr/.test(badge.textContent)) { s.scrollIntoView({block:'center'}); break; }
            }
        }"""
    )
    page.wait_for_timeout(800)
    _mark("docs")
    page.wait_for_timeout(3000)

    # 8. MANUAL.pdf — click the link, catch the download, verify it is a real
    #    non-empty PDF, and confirm the URL serves application/pdf.
    pdf_link = page.locator(".manual-pdf-link")
    if pdf_link.count() == 0:
        raise RuntimeError("MANUAL.pdf link not found in DOCS tab")
    pdf_href = pdf_link.first.get_attribute("href")
    with page.expect_download(timeout=20000) as dl_info:
        pdf_link.first.click()
    dl = dl_info.value
    pdf_download = tmp / "MANUAL.pdf"
    dl.save_as(str(pdf_download))
    if pdf_download.stat().st_size == 0 or pdf_download.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError("downloaded MANUAL.pdf is empty or not a PDF")
    pdf_resp = requests.get(DASHBOARD_URL + pdf_href, timeout=15)
    if pdf_resp.status_code != 200 or pdf_resp.headers.get("Content-Type") != "application/pdf":
        raise RuntimeError("MANUAL.pdf URL did not serve application/pdf")
    _mark("pdf")
    page.wait_for_timeout(3000)

    # 9. AI package summary (top of docsContent).
    page.evaluate("() => document.getElementById('docsContent').scrollTop = 0")
    page.wait_for_timeout(800)
    _mark("ai")
    page.wait_for_timeout(3000)

    # 10. Back to the clean home view.
    page.locator("#previewModal .close-x").click()
    page.wait_for_selector("#previewModal.hidden", state="hidden", timeout=TIMEOUT_MS)
    page.wait_for_timeout(800)
    _mark("final")
    page.wait_for_timeout(3000)

    return phases, shots


def _edit_screencast(webm: Path, t0: float, phases: list[tuple[str, float]], out_path: Path) -> None:
    """Trims the screencast into per-phase segments, speeds each to its target
    duration, concats, and burns in the marketing overlays."""
    webm_dur = _probe_duration(webm)
    marks = [t0] + [t for _, t in phases]
    segments: list[tuple[float, float, float, str | None]] = []
    for i, (name, target_dur) in enumerate(PHASES):
        start = max(0.0, marks[i] - t0 - 0.3)
        end = min(webm_dur, marks[i + 1] - t0 + 0.3)
        real = max(0.1, end - start)
        segments.append((start, end, real / target_dur, OVERLAYS.get(name)))

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for i, (start, end, speed, overlay) in enumerate(segments):
        chain = (
            f"[0:v]trim=start={start:.3f}:end={end:.3f},"
            f"setpts=(PTS-STARTPTS)/{speed:.4f},fps=30,"
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
        if overlay:
            chain += "," + _drawtext(overlay, y="h-160")
        chain += f"[v{i}]"
        filter_parts.append(chain)
        concat_inputs.append(f"[v{i}]")

    filter_parts.append("".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=0[outv]")
    cmd = (
        ["ffmpeg", "-y", "-i", str(webm), "-filter_complex", ";".join(filter_parts),
         "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", "30", "-movflags", "+faststart", str(out_path)]
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg edit failed:\n{result.stderr[-3000:]}")


def _edit_screenshots(shots: list[tuple[Path, float]], phases: list[tuple[str, float]], out_path: Path) -> None:
    """Fallback edit: assembles the per-phase screenshots into the final MP4."""
    marks = [phases[0][1]] + [t for _, t in phases]
    frames: list[tuple[Path, float, str | None]] = []
    for i, (name, target_dur) in enumerate(PHASES):
        start_w, end_w = marks[i], marks[i + 1]
        phase_shots = [p for p, t in shots if start_w <= t < end_w]
        if not phase_shots:
            boundary = next((p for p, t in shots if abs(t - start_w) < 2.0), None)
            if boundary:
                phase_shots = [boundary]
        if not phase_shots:
            continue
        per = target_dur / len(phase_shots)
        overlay = OVERLAYS.get(name)
        for j, (path, _) in enumerate(phase_shots):
            frames.append((path, per, overlay if j == 0 else None))

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

    filter_parts.append("".join(concat_inputs) + f"concat=n={len(frames)}:v=1:a=0[outv]")
    cmd = (
        ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filter_parts),
         "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", "30", "-movflags", "+faststart", str(out_path)]
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg fallback edit failed:\n{result.stderr[-3000:]}")


def _isolate_workspace(backup: Path) -> None:
    """Moves the real workspace into `backup` and leaves empty dirs plus the
    demo video, so the pipeline run is isolated to synthetic data only."""
    for name in WORKSPACE_DIRS + WORKSPACE_FILES:
        src = ROOT / name
        if src.exists():
            shutil.move(str(src), str(backup / name))
    for name in WORKSPACE_DIRS:
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEMO_VIDEO, ROOT / "Video_compress" / DEMO_VIDEO.name)


def _restore_workspace(backup: Path) -> None:
    """Restores the real workspace. `_isolate_workspace` moved the real dirs
    into `backup` and left empty dirs; the pipeline then wrote demo outputs
    into those empty dirs (including subfolders like Videos/general/). So we
    unconditionally remove the current workspace dirs (they are demo-only by
    construction — the real data is in `backup`) and move the backup back.
    A name with no backup entry simply didn't exist before; its empty dir is
    removed too."""
    for name in WORKSPACE_DIRS:
        shutil.rmtree(ROOT / name, ignore_errors=True)
    for entry in backup.iterdir():
        shutil.move(str(entry), str(ROOT / entry.name))


def main() -> int:
    if not DEMO_VIDEO.exists():
        print(f"[FAIL] demo video missing: {DEMO_VIDEO}", file=sys.stderr)
        print("       run: python scripts/generate_demo_video.py", file=sys.stderr)
        return 1
    if shutil.which("ffmpeg") is None:
        print("[FAIL] ffmpeg not found on PATH", file=sys.stderr)
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="zo_demo_"))
    backup = tmp / "workspace_backup"
    backup.mkdir(parents=True, exist_ok=True)

    server: subprocess.Popen | None = None
    server_output: list[str] = []
    try:
        _isolate_workspace(backup)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["DASHBOARD_PORT"] = str(PORT)

        server = subprocess.Popen(
            _server_cmd(), cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=_drain_output, args=(server.stdout, server_output), daemon=True).start()

        if not _wait_for_server():
            print("[FAIL] dashboard did not start", file=sys.stderr)
            print("       server output:", file=sys.stderr)
            print("".join(server_output[-40:]), file=sys.stderr)
            return 1

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.on("dialog", lambda d: d.accept())

            webm = tmp / "journey.webm"
            t0 = time.time()
            page.screencast.start(path=str(webm))
            try:
                phases, shots = _journey(page, tmp)
            finally:
                page.screencast.stop()
            browser.close()

        if webm.exists() and webm.stat().st_size > 0:
            _edit_screencast(webm, t0, phases, OUT_PATH)
        else:
            print("[WARN] screencast empty — assembling from screenshots", file=sys.stderr)
            _edit_screenshots(shots, phases, OUT_PATH)
        print(f"[OK] demo video: {OUT_PATH}")
        return 0
    except Exception:
        print("[FAIL] demo generation failed — dashboard output:", file=sys.stderr)
        print("".join(server_output[-60:]), file=sys.stderr)
        raise
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except Exception:
                server.kill()
        _restore_workspace(backup)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())