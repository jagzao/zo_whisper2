"""Generates a short, fully synthetic tutorial video for manual acceptance
testing (US-001 final acceptance) — local TTS narration (Windows SAPI) +
ffmpeg drawtext screen changes, no external LLM, no real client data.

Five ~6s segments, each a distinct on-screen color + caption, most with a
narration line that partially overlaps the on-screen text (so the pipeline
produces a mix of "transcript", "transcript_ocr", and one pure "ocr"
segment) — see transcript_pipeline.documentation.engine's evidence layering.

Output filename starts with "en_" (forces English transcription) and
contains "tutorial" (routes to the "Tutorials" project and activates
keyframe extraction) per the naming conventions in CLAUDE.md.

Run:
    python scripts/generate_demo_video.py [--force] [--out PATH]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "demo" / "en_demo_zo_media_intelligence_tutorial.mp4"
SEGMENT_SECONDS = 6
SIZE = "960x540"
FONT = "C\\:/Windows/Fonts/arial.ttf"
VOICE = "Microsoft David Desktop"

# (lavfi source, on-screen caption, narration or None)
# Textured/patterned lavfi sources, not flat colors — a flat-color frame is
# a degenerate case for ffmpeg's scene-change score (only the small text
# region differs, background is ~identical), so smart_scene keyframe
# detection never fires between segments. Same reasoning already used by
# tests/integration/conftest.py's make_synthetic_cuts_video fixture.
# Narration is short relative to SEGMENT_SECONDS so each segment ends with
# a few seconds of real silence — enough of a gap for Whisper/VAD to emit
# one transcript segment per narration line instead of merging all speech
# into a single run-on segment.
# Segments 2 and 3 captions add information the narration doesn't say
# (a concrete label / a config value) -> combined "transcript_ocr" evidence.
# Segment 5 has no narration at all -> pure "ocr" evidence.
SEGMENTS = [
    ("testsrc", "ZO MEDIA INTELLIGENCE", "Welcome to Zo Media Intelligence."),
    ("smptebars", "STEP 1: RUN FULL", "Click Run Full to start."),
    ("rgbtestsrc", "PIPELINE: COMPRESS - TRANSCRIBE - KEYFRAMES", "The pipeline transcribes and extracts keyframes."),
    ("pal75bars", "DOCS TAB: MANUAL.MD", "Open the docs tab to review the manual."),
    ("yuvtestsrc", "CONFIG: ALLOW_EXTERNAL_LLM=FALSE", None),
]


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr}")


def _synthesize_narration(text: str, wav_path: Path) -> None:
    ps_script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{VOICE}'); "
        f"$s.SetOutputToWaveFile('{wav_path}'); "
        f"$s.Speak('{text.replace(chr(39), '')}'); "
        "$s.Dispose()"
    )
    _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script])


def _make_segment(index: int, source: str, caption: str, narration: str | None, tmp: Path) -> Path:
    video_only = tmp / f"seg{index}_video.mp4"
    escaped_caption = caption.replace(":", "\\:")
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"{source}=size={SIZE}:rate=10:duration={SEGMENT_SECONDS}",
        "-vf", (
            f"drawtext=fontfile='{FONT}':text='{escaped_caption}':fontcolor=white:"
            "fontsize=30:box=1:boxcolor=black@0.7:boxborderw=14:"
            "x=(w-text_w)/2:y=(h-text_h)/2"
        ),
        "-pix_fmt", "yuv420p", str(video_only),
    ])

    # SAPI (System.Speech) always renders at 22050 Hz — the silent placeholder
    # must match, or the concat demuxer's stream-copy mixes sample rates
    # across segments and corrupts the container's reported/actual duration.
    wav_path = tmp / f"seg{index}.wav"
    if narration:
        _synthesize_narration(narration, wav_path)
    else:
        _run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
            "-t", "1", str(wav_path),
        ])

    padded_wav = tmp / f"seg{index}_padded.wav"
    _run([
        "ffmpeg", "-y", "-i", str(wav_path),
        "-af", "apad", "-ar", "22050", "-t", str(SEGMENT_SECONDS), str(padded_wav),
    ])

    muxed = tmp / f"seg{index}_av.mp4"
    _run([
        "ffmpeg", "-y", "-i", str(video_only), "-i", str(padded_wav),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(muxed),
    ])
    return muxed


def generate(out_path: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="zo_demo_") as tmp_str:
        tmp = Path(tmp_str)
        segment_files = [
            _make_segment(i, bg, caption, narration, tmp)
            for i, (bg, caption, narration) in enumerate(SEGMENTS, start=1)
        ]

        concat_list = tmp / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{f.as_posix()}'" for f in segment_files), encoding="utf-8"
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", str(out_path),
        ])
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true", help="regenerate even if the file already exists")
    args = parser.parse_args()

    if args.out.exists() and not args.force:
        print(f"[OK] demo video already exists: {args.out}")
        return 0

    if shutil.which("ffmpeg") is None:
        print("[FAIL] ffmpeg not found on PATH", file=sys.stderr)
        return 1

    generate(args.out)
    print(f"[OK] demo video generated: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
