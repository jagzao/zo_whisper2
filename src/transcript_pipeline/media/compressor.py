#!/usr/bin/env python3
"""
Video Compressor & Mover - Compresses videos with high efficiency (H.265)
and moves them to their destination folder.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from transcript_pipeline.config import PROJECT_ROOT
from transcript_pipeline.settings import SETTINGS

_COMPRESSION_TIMEOUT_SECONDS = 2 * 60 * 60  # 2h — generous, catches a hung ffmpeg, not slow encoding


def get_video_info(video_path):
    """Gets video information using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', str(video_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"[ERROR] Could not get video info: {e}")
        return None


def compress_video_high_efficiency(input_path, output_path):
    """Compresses video with H.265 using a configurable CRF (24-26 recommended)."""
    print(f"[INFO] Analyzing: {input_path.name}")

    info = get_video_info(input_path)
    if not info:
        return False

    duration = float(info['format']['duration'])
    current_size_mb = int(info['format']['size']) / (1024 * 1024)

    video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not video_stream:
        print("[ERROR] No video stream found")
        return False

    width = int(video_stream.get('width', 0))
    height = int(video_stream.get('height', 0))
    fps_str = video_stream.get('r_frame_rate', '30/1')
    try:
        if '/' in fps_str:
            num, _, den = fps_str.partition('/')
            fps = float(num) / float(den) if float(den) else 30.0
        else:
            fps = float(fps_str)
    except Exception:
        fps = 30.0

    print(f"[INFO] Duration: {duration:.1f}s | Current size: {current_size_mb:.1f}MB")
    print(f"[INFO] Resolution: {width}x{height} | FPS: {fps:.1f}")

    # H.265 offers a better quality/size ratio than H.264.
    # Recommended CRF range: 24 to 26.
    crf = max(24, min(26, SETTINGS.video_compress_crf))

    cmd = [
        'ffmpeg', '-i', str(input_path),
        '-c:v', 'libx265',            # H.265/HEVC codec
        '-preset', 'slow',            # Compression/time tradeoff for HEVC
        '-crf', str(crf),             # Recommended range: 24-26
        '-tag:v', 'hvc1',             # Better player compatibility
        '-c:a', 'copy',               # Copy audio without re-encoding
        '-movflags', '+faststart',   # Streaming optimization
        '-pix_fmt', 'yuv420p',      # Compatible pixel format
        '-y', str(output_path)       # Overwrite if it exists
    ]

    print(f"[INFO] Compressing with H.265 + CRF {crf} + preset slow...")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        try:
            # H.265 encoding is genuinely slow for large/long videos — this
            # bounds a truly hung ffmpeg process, not normal compression time.
            stdout, stderr = process.communicate(timeout=_COMPRESSION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            print(f"[ERROR] FFmpeg compression timed out after {_COMPRESSION_TIMEOUT_SECONDS}s")
            return False

        if process.returncode != 0:
            print(f"[ERROR] FFmpeg failed: {stderr}")
            return False

        if output_path.exists():
            final_size_mb = output_path.stat().st_size / (1024 * 1024)
            reduction = ((current_size_mb - final_size_mb) / current_size_mb * 100) if current_size_mb > 0 else 0
            print(f"[OK] Compressed: {current_size_mb:.1f}MB → {final_size_mb:.1f}MB ({reduction:.1f}% reduction)")
            return True
        else:
            print("[ERROR] Output file was not generated")
            return False

    except Exception as e:
        print(f"[ERROR] Exception during compression: {e}")
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


def process_video_compress_folder(base_path: Path = PROJECT_ROOT) -> int:
    """Processes the Video_compress folder: compresses and moves files"""
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

    processed_count = 0

    for video_file in video_files:
        print(f"\n[PROCESSING] {video_file.name}")
        print("-" * 50)

        target_folder = get_target_folder(video_file.name, base_path)
        target_folder.mkdir(parents=True, exist_ok=True)

        temp_compressed = compress_folder / f"temp_{video_file.name}"

        try:
            if compress_video_high_efficiency(video_file, temp_compressed):
                final_path = target_folder / video_file.name

                if final_path.exists():
                    timestamp = datetime.now().strftime("%H%M%S")
                    stem = video_file.stem
                    suffix = video_file.suffix
                    final_path = target_folder / f"{stem}_{timestamp}{suffix}"

                shutil.move(str(temp_compressed), str(final_path))
                video_file.unlink()

                print(f"[OK] Moved to: {final_path}")
                processed_count += 1
            else:
                if temp_compressed.exists():
                    temp_compressed.unlink()
                print(f"[ERROR] Could not compress {video_file.name}")

        except Exception as e:
            print(f"[ERROR] Processing {video_file.name}: {e}")
            if temp_compressed.exists():
                temp_compressed.unlink()

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
