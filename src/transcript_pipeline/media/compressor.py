#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Compressor & Mover - Comprime videos con alta eficiencia (H.265)
y los mueve a su carpeta destino.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from transcript_pipeline.config import PROJECT_ROOT


def get_video_info(video_path):
    """Obtiene información del video usando ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', str(video_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"[ERROR] No se pudo obtener info del video: {e}")
        return None


def compress_video_high_efficiency(input_path, output_path):
    """Comprime video con H.265 usando CRF configurable (24-26 recomendado)."""
    print(f"[INFO] Analizando: {input_path.name}")

    info = get_video_info(input_path)
    if not info:
        return False

    duration = float(info['format']['duration'])
    current_size_mb = int(info['format']['size']) / (1024 * 1024)

    video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not video_stream:
        print("[ERROR] No se encontró stream de video")
        return False

    width = int(video_stream.get('width', 0))
    height = int(video_stream.get('height', 0))
    fps_str = video_stream.get('r_frame_rate', '30/1')
    try:
        fps = eval(fps_str) if '/' in fps_str else float(fps_str)
    except Exception:
        fps = 30.0

    print(f"[INFO] Duración: {duration:.1f}s | Tamaño actual: {current_size_mb:.1f}MB")
    print(f"[INFO] Resolución: {width}x{height} | FPS: {fps:.1f}")

    # H.265 ofrece mejor ratio calidad/tamano que H.264.
    # Recomendado por usuario: CRF entre 24 y 26.
    try:
        crf = int(os.getenv("VIDEO_COMPRESS_CRF", "25"))
    except ValueError:
        crf = 25

    crf = max(24, min(26, crf))

    cmd = [
        'ffmpeg', '-i', str(input_path),
        '-c:v', 'libx265',            # Codec H.265/HEVC
        '-preset', 'slow',            # Equilibrio compresion/tiempo en HEVC
        '-crf', str(crf),             # Rango recomendado: 24-26
        '-tag:v', 'hvc1',             # Mejor compatibilidad en reproductores
        '-c:a', 'copy',               # Copiar audio sin recodificar
        '-movflags', '+faststart',   # Optimización para streaming
        '-pix_fmt', 'yuv420p',      # Formato compatible
        '-y', str(output_path)       # Sobrescribir si existe
    ]

    print(f"[INFO] Comprimiendo con H.265 + CRF {crf} + preset slow...")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"[ERROR] FFmpeg falló: {stderr}")
            return False

        if output_path.exists():
            final_size_mb = output_path.stat().st_size / (1024 * 1024)
            reduction = ((current_size_mb - final_size_mb) / current_size_mb * 100) if current_size_mb > 0 else 0
            print(f"[OK] Comprimido: {current_size_mb:.1f}MB → {final_size_mb:.1f}MB ({reduction:.1f}% reducción)")
            return True
        else:
            print("[ERROR] No se generó el archivo de salida")
            return False

    except Exception as e:
        print(f"[ERROR] Excepción durante compresión: {e}")
        return False


def get_target_folder(filename, base_path):
    """Determina la carpeta destino según el prefijo del archivo"""
    filename_lower = filename.lower()

    # Mapa de prefijos a carpetas (igual que en pipeline/master.py)
    target_map = {
        "zo_": base_path / "Videos" / "py_zo",
        "valeris_": base_path / "Videos" / "py_valeris",
        "jm_": base_path / "Videos" / "py_jm",
    }

    for prefix, target in target_map.items():
        if filename_lower.startswith(prefix):
            return target

    if "interview" in filename_lower or "entrevista" in filename_lower:
        return base_path / "Videos" / "zo_Entrevista"

    return base_path / "Videos" / "general"


def process_video_compress_folder(base_path: Path = PROJECT_ROOT) -> int:
    """Procesa la carpeta Video_compress: comprime y mueve archivos"""
    compress_folder = base_path / "Video_compress"

    print("=" * 60)
    print("COMPRESION DE VIDEOS - H.265 (CRF 24-26)")
    print("=" * 60)
    print()

    if not compress_folder.exists():
        print("[INFO] Carpeta Video_compress no existe, creándola...")
        compress_folder.mkdir(exist_ok=True)
        print(f"[OK] Carpeta creada: {compress_folder}")
        return 0

    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    video_files = [f for f in compress_folder.iterdir()
                   if f.is_file() and f.suffix.lower() in video_extensions]

    if not video_files:
        print("[INFO] No hay videos pendientes de compresión en Video_compress/")
        return 0

    print(f"[INFO] Encontrados {len(video_files)} video(s) para comprimir")
    print()

    processed_count = 0

    for video_file in video_files:
        print(f"\n[PROCESANDO] {video_file.name}")
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

                print(f"[OK] Movido a: {final_path}")
                processed_count += 1
            else:
                if temp_compressed.exists():
                    temp_compressed.unlink()
                print(f"[ERROR] No se pudo comprimir {video_file.name}")

        except Exception as e:
            print(f"[ERROR] Procesando {video_file.name}: {e}")
            if temp_compressed.exists():
                temp_compressed.unlink()

    print()
    print("=" * 60)
    print(f"[RESUMEN] Videos procesados: {processed_count}/{len(video_files)}")
    print("=" * 60)

    return processed_count


def main() -> None:
    if sys.platform == "win32":
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())

    try:
        count = process_video_compress_folder()
        sys.exit(0 if count >= 0 else 1)
    except KeyboardInterrupt:
        print("\n[INTERRUMPIDO] Proceso cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR CRÍTICO] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
