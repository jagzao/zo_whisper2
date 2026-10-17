#!/usr/bin/env python3
"""Video Compressor & Mover.

Compresses videos with high efficiency (H.265) and moves them to their
destination folder. Source deletion is delegated to
`transcript_pipeline.media.optimize`, which validates and publishes the
optimized output and records provenance before removing the exact source.
"""

import json
import subprocess
import sys
from pathlib import Path

from transcript_pipeline.config import DATA_ROOT
from transcript_pipeline.media.optimize import (
    FAILED,
    OPTIMIZED_SOURCE_REMOVED,
    ProvenanceStore,
    encode_h265,
    optimize_media,
)
from transcript_pipeline.media.utils import run_ffprobe

_COMPRESSION_TIMEOUT_SECONDS = 2 * 60 * 60


def get_video_info(video_path):
    """Gets video information using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', str(video_path)
    ]

    try:
        result = run_ffprobe(cmd)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"[ERROR] Could not get video info: {e}")
        return None


def compress_video_high_efficiency(input_path, output_path):
    """Compresses video with H.265 using a configurable CRF (24-26 recommended).

    Thin compatibility wrapper: encoding only. Validation, publication and
    source cleanup are the caller's responsibility via `optimize_media`.
    """
    print(f"[INFO] Analyzing: {input_path.name}")

    info = get_video_info(input_path)
    if not info:
        return False

    video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not video_stream:
        print("[ERROR] No video stream found")
        return False

    from transcript_pipeline.settings import SETTINGS

    crf = max(24, min(26, SETTINGS.video_compress_crf))
    print(f"[INFO] Compressing with H.265 + CRF {crf} + preset slow...")

    if encode_h265(Path(input_path), Path(output_path), crf=crf):
        if Path(output_path).exists():
            final_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            current_size_mb = int(info['format']['size']) / (1024 * 1024)
            reduction = ((current_size_mb - final_size_mb) / current_size_mb * 100) if current_size_mb > 0 else 0
            print(f"[OK] Compressed: {current_size_mb:.1f}MB → {final_size_mb:.1f}MB ({reduction:.1f}% reduction)")
            return True
    print("[ERROR] FFmpeg compression failed")
    return False


def get_target_folder(filename, base_path):
    """Determines the destination folder based on the filename prefix"""
    filename_lower = filename.lower()

    # Prefix-to-folder map (same convention as pipeline/master.py)
    target_map = {
        "zo_": base_path / "Videos" / "py_zo",
        "jm_": base_path / "Videos" / "py_jm",
    }

    for prefix, target in target_map.items():
        if filename_lower.startswith(prefix):
            return target

    if "interview" in filename_lower or "entrevista" in filename_lower:
        return base_path / "Videos" / "zo_Entrevista"

    return base_path / "Videos" / "general"


def process_video_compress_folder(base_path: Path = DATA_ROOT) -> int:
    """Processes the Video_compress folder: validates, publishes, cleans up."""
    compress_folder = base_path / "Video_compress"

    print("=" * 60)
    print("VIDEO COMPRESSION - H.265 (CRF 24-26)")
    print("=" * 60)
    print()

    if not compress_folder.exists():
        print("[INFO] Video_compress folder doesn't exist, creating it...")
        compress_folder.mkdir(exist_ok=True)
        print(f"[OK] Folder created: {compress_folder}")
        return 0

    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    video_files = [f for f in compress_folder.iterdir()
                   if f.is_file() and f.suffix.lower() in video_extensions]

    if not video_files:
        print("[INFO] No videos pending compression in Video_compress/")
        return 0

    print(f"[INFO] Found {len(video_files)} video(s) to compress")
    print()

    provenance = ProvenanceStore(base_path / "compression_provenance.json")
    processed_count = 0

    for video_file in video_files:
        print(f"\n[PROCESSING] {video_file.name}")
        print("-" * 50)

        target_folder = get_target_folder(video_file.name, base_path)
        target_folder.mkdir(parents=True, exist_ok=True)

        result = optimize_media(
            video_file,
            target_folder,
            base_path=base_path,
            provenance=provenance,
        )

        if result.cleanup_state == OPTIMIZED_SOURCE_REMOVED:
            print(f"[OK] Moved to: {result.output}")
            print(f"     size: {result.source_size} -> {result.output_size} bytes "
                  f"(saved {result.bytes_saved})")
            print("     cleanup: OPTIMIZED_SOURCE_REMOVED")
            processed_count += 1
        elif result.succeeded:
            print(f"[WARN] Optimized output retained at {result.output}; source kept ({result.cleanup_state})")
            print(f"     reason: {result.reason}")
            processed_count += 1
        else:
            print(f"[ERROR] Could not compress {video_file.name}: {result.reason}")
            print(f"     cleanup: {FAILED} (source retained at {video_file})")

    print()
    print("=" * 60)
    print(f"[SUMMARY] Videos processed: {processed_count}/{len(video_files)}")
    print("=" * 60)

    return processed_count


def main() -> None:
    if sys.platform == "win32":
        import codecs
        # sys.stdout/stderr are typed as TextIO, which typeshed doesn't
        # declare .detach() on — it's real on the TextIOWrapper Python
        # actually hands you here, just not part of the abstract interface.
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())  # type: ignore[attr-defined]
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())  # type: ignore[attr-defined]

    try:
        count = process_video_compress_folder()
        sys.exit(0 if count >= 0 else 1)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Process cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
