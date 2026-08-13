#!/usr/bin/env python3
"""
Keyframe Extractor Module
Extracts keyframes from tutorial videos using FFmpeg
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class KeyframeExtractor:
    """Extractor de frames clave para videos de tutorial"""

    def __init__(
        self,
        output_base_dir: str = "Frames",
        frame_format: str = "png",
        ffmpeg_path: str | None = None
    ):
        """
        Inicializa el extractor de frames clave.

        Args:
            output_base_dir: Directorio base para guardar los frames
            frame_format: Formato de imagen ("png", "jpg", "webp")
            ffmpeg_path: Ruta personalizada a FFmpeg (opcional)
        """
        self.output_base_dir = Path(output_base_dir)
        self.frame_format = frame_format.lower()
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"

        # Validar formato
        if self.frame_format not in ["png", "jpg", "jpeg", "webp"]:
            logger.warning(f"Formato no válido: {frame_format}, usando PNG")
            self.frame_format = "png"

        # Crear directorio base
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

    def extract_keyframes(
        self,
        video_path: Path,
        method: str = "iframe",
        max_frames: int | None = None,
        quality: int = 2
    ) -> dict[str, Any]:
        """
        Extrae frames clave de un video usando FFmpeg.

        Args:
            video_path: Ruta al archivo de video
            method: Método de extracción ("iframe", "scene", "interval")
            max_frames: Número máximo de frames a extraer (None = sin límite)
            quality: Calidad de compresión (1-31, menor = mejor calidad)

        Returns:
            Dict con información sobre la extracción:
            - success: bool
            - frames_dir: str (ruta a la carpeta de frames)
            - frame_count: int
            - video_duration: float (segundos)
            - processing_time: float (segundos)
            - method: str (método usado)
            - error: str (si hubo error)
        """
        start_time = time.time()

        try:
            # Validar video
            if not video_path.exists():
                return {
                    "success": False,
                    "error": f"Video no encontrado: {video_path}",
                    "frames_dir": "",
                    "frame_count": 0,
                    "video_duration": 0.0,
                    "processing_time": time.time() - start_time,
                    "method": method
                }

            # Obtener duración del video
            duration = self._get_video_duration(video_path)
            if duration == 0:
                return {
                    "success": False,
                    "error": "No se pudo obtener la duración del video",
                    "frames_dir": "",
                    "frame_count": 0,
                    "video_duration": 0.0,
                    "processing_time": time.time() - start_time,
                    "method": method
                }
            
            # Optimización para videos largos (>2h)
            if duration > 7200 and max_frames and max_frames > 50:
                import os
                max_frames = int(os.getenv("FRAME_EXTRACTION_LONG_VIDEO_MAX_FRAMES", "50"))
                logger.info(f"[KEYFRAMES] Video largo detectado ({duration/3600:.1f}h), limitando a {max_frames} frames")

            # Crear directorio de salida
            project_name, video_name = self._get_output_paths(video_path)
            frames_dir = project_name / video_name
            frames_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"[KEYFRAMES] Extrayendo frames de: {video_path.name}")
            logger.info(f"[KEYFRAMES] Método: {method}, Duración: {duration:.1f}s")

            # Extraer frames según el método
            frame_count = self._extract_frames(video_path, frames_dir, method, max_frames, quality)

            # Crear mapa de frames con timestamps
            self._create_frame_mapping(video_path, frames_dir, duration, method)

            processing_time = time.time() - start_time

            logger.info(f"[KEYFRAMES] Extraídos {frame_count} frames en {processing_time:.1f}s")
            logger.info(f"[KEYFRAMES] Guardados en: {frames_dir}")

            return {
                "success": True,
                "frames_dir": str(frames_dir),
                "frame_count": frame_count,
                "video_duration": duration,
                "processing_time": processing_time,
                "method": method,
                "error": None
            }

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"[KEYFRAMES] Error extrayendo frames: {e}")
            return {
                "success": False,
                "error": str(e),
                "frames_dir": "",
                "frame_count": 0,
                "video_duration": 0.0,
                "processing_time": processing_time,
                "method": method
            }

    def _get_output_paths(self, video_path: Path):
        """
        Obtiene las rutas de salida basadas en la estructura del proyecto.

        Args:
            video_path: Ruta al video de origen

        Returns:
            Tupla (project_dir, video_name)
        """
        # Extraer nombre del proyecto y video
        parts = video_path.parts
        project_name = parts[-2] if len(parts) >= 2 else "default"
        video_name = video_path.stem

        base_path = Path(os.getenv("TRANSCRIPTIONS_PATH") or (Path(__file__).parents[3] / "CarpetaTranscripciones"))
        project_dir = base_path / project_name / f"{video_name}_Frames"

        return project_dir, video_name

    def _get_video_duration(self, video_path: Path) -> float:
        """
        Obtiene la duración del video usando FFprobe/FFmpeg.

        Args:
            video_path: Ruta al video

        Returns:
            Duración en segundos (0 si hay error)
        """
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", str(video_path),
                "-f", "null",
                "-"
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30
            )

            # Buscar duración en la salida
            for line in result.stdout.split('\n'):
                if "Duration:" in line:
                    # Formato: "Duration: 00:01:23.45, start: 0.000000, bitrate: 1234 kb/s"
                    duration_str = line.split("Duration:")[1].split(",")[0].strip()
                    # Parsear HH:MM:SS.mmm
                    parts = duration_str.split(":")
                    if len(parts) == 3:
                        hours = float(parts[0])
                        minutes = float(parts[1])
                        seconds = float(parts[2])
                        return hours * 3600 + minutes * 60 + seconds

            return 0.0

        except Exception as e:
            logger.warning(f"[KEYFRAMES] Error obteniendo duración: {e}")
            return 0.0

    def _create_frame_mapping(self, video_path: Path, frames_dir: Path, duration: float, method: str):
        """
        Crea un archivo JSON con el mapeo de frames a timestamps y espacio para transcripción.
        
        Args:
            video_path: Ruta al video original
            frames_dir: Directorio donde se guardaron los frames
            duration: Duración total del video
            method: Método de extracción usado
        """
        import json
        
        try:
            # Obtener lista de frames extraídos
            frame_files = sorted([f for f in frames_dir.glob(f"*.{self.frame_format}")])
            
            # Calcular timestamps aproximados
            frame_timestamps = []
            
            if method == "iframe":
                # Para I-frames, necesitamos extraer timestamps reales
                frame_timestamps = self._extract_frame_timestamps(video_path, frame_files)
            elif method == "interval":
                # Para intervalos, calcular basado en duración y cantidad
                interval = duration / len(frame_files) if frame_files else 0
                for i, frame_file in enumerate(frame_files):
                    timestamp = i * interval
                    frame_timestamps.append({
                        "frame_file": frame_file.name,
                        "timestamp": timestamp,
                        "timestamp_formatted": self._format_timestamp(timestamp)
                    })
            else:  # scene
                # Para scene detection, usar distribución uniforme como aproximación
                interval = duration / len(frame_files) if frame_files else 0
                for i, frame_file in enumerate(frame_files):
                    timestamp = i * interval
                    frame_timestamps.append({
                        "frame_file": frame_file.name,
                        "timestamp": timestamp,
                        "timestamp_formatted": self._format_timestamp(timestamp)
                    })
            
            # Crear mapa completo
            mapping_data = {
                "video_info": {
                    "name": video_path.name,
                    "duration": duration,
                    "duration_formatted": self._format_timestamp(duration),
                    "extraction_method": method,
                    "total_frames": len(frame_files),
                    "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                "frames": frame_timestamps,
                "transcription_mapping": {}  # Se llenará después de la transcripción
            }
            
            # Guardar mapa en JSON
            mapping_file = frames_dir / "frame_mapping.json"
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[KEYFRAMES] Mapa de frames creado: {mapping_file}")
            
        except Exception as e:
            logger.error(f"[KEYFRAMES] Error creando mapa de frames: {e}")

    def _extract_frame_timestamps(self, video_path: Path, frame_files: list) -> list[dict]:
        """
        Extrae timestamps reales de los I-frames usando FFprobe.
        """
        timestamps = []
        try:
            cmd = [
                self.ffmpeg_path.replace('ffmpeg', 'ffprobe') if self.ffmpeg_path else 'ffprobe',
                "-select_streams", "v:0",
                "-show_entries", "frame=pict_type:pkt_pts_time",
                "-of", "csv=p=0",
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                frame_index = 0
                
                for line in lines:
                    if line.startswith("I"):  # I-frame
                        parts = line.split(',')
                        if len(parts) >= 2:
                            timestamp = float(parts[1])
                            if frame_index < len(frame_files):
                                timestamps.append({
                                    "frame_file": frame_files[frame_index].name,
                                    "timestamp": timestamp,
                                    "timestamp_formatted": self._format_timestamp(timestamp)
                                })
                                frame_index += 1
                
                # Si no hay suficientes timestamps, generar aproximados
                while frame_index < len(frame_files):
                    timestamps.append({
                        "frame_file": frame_files[frame_index].name,
                        "timestamp": frame_index * 10.0,  # Estimación
                        "timestamp_formatted": self._format_timestamp(frame_index * 10.0)
                    })
                    frame_index += 1
                    
        except Exception as e:
            logger.warning(f"[KEYFRAMES] Error extrayendo timestamps reales: {e}")
            # Fallback a timestamps aproximados
            duration = self._get_video_duration(video_path)
            interval = duration / len(frame_files) if frame_files else 0
            for i, frame_file in enumerate(frame_files):
                timestamps.append({
                    "frame_file": frame_file.name,
                    "timestamp": i * interval,
                    "timestamp_formatted": self._format_timestamp(i * interval)
                })
        
        return timestamps

    def _format_timestamp(self, seconds: float) -> str:
        """Formatea segundos a HH:MM:SS.mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    def _extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        method: str,
        max_frames: int | None,
        quality: int
    ) -> int:
        """
        Extrae frames usando el método especificado.

        Args:
            video_path: Ruta al video
            output_dir: Directorio de salida
            method: Método de extracción
            max_frames: Límite de frames
            quality: Calidad de compresión

        Returns:
            Número de frames extraídos
        """
        if method == "iframe":
            return self._extract_iframes(video_path, output_dir, max_frames, quality)
        elif method == "scene":
            return self._extract_scene_frames(video_path, output_dir, max_frames, quality)
        elif method == "smart_scene":
            return self._extract_smart_scene_frames(video_path, output_dir, max_frames, quality)
        elif method == "interval":
            return self._extract_interval_frames(video_path, output_dir, max_frames, quality)
        else:
            logger.warning(f"[KEYFRAMES] Método no válido: {method}, usando iframe")
            return self._extract_iframes(video_path, output_dir, max_frames, quality)

    def _extract_iframes(
        self,
        video_path: Path,
        output_dir: Path,
        max_frames: int | None,
        quality: int
    ) -> int:
        """
        Extrae I-frames (keyframes nativos del codec).

        Args:
            video_path: Ruta al video
            output_dir: Directorio de salida
            max_frames: Límite de frames
            quality: Calidad de compresión

        Returns:
            Número de frames extraídos
        """
        output_pattern = str(output_dir / f"frame_%04d.{self.frame_format}")

        # Filtro para seleccionar I-frames
        filter_complex = "select='eq(pict_type,I)'"

        # Comando FFmpeg
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-vf", filter_complex,
            "-vsync", "vfr",
            "-q:v", str(quality),
            "-y",  # Sobrescribir archivos existentes
            output_pattern
        ]

        # Ejecutar comando
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.error(f"[KEYFRAMES] FFmpeg error: {result.stderr}")
            return 0

        # Contar frames extraídos
        frame_count = len(list(output_dir.glob(f"frame_*.{self.frame_format}")))

        # Aplicar límite si es necesario
        if max_frames and frame_count > max_frames:
            self._limit_frames(output_dir, max_frames)
            frame_count = max_frames

        return frame_count

    def _extract_scene_frames(
        self,
        video_path: Path,
        output_dir: Path,
        max_frames: int | None,
        quality: int
    ) -> int:
        """
        Extrae frames basándose en cambios de escena (naive).

        Args:
            video_path: Ruta al video
            output_dir: Directorio de salida
            max_frames: Límite de frames
            quality: Calidad de compresión

        Returns:
            Número de frames extraídos
        """
        output_pattern = str(output_dir / f"frame_%04d.{self.frame_format}")

        # Filtro para detectar cambios de escena
        filter_complex = "select='gt(scene,0.4)'"

        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-vf", filter_complex,
            "-vsync", "vfr",
            "-q:v", str(quality),
            "-y",
            output_pattern
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.error(f"[KEYFRAMES] FFmpeg error: {result.stderr}")
            return 0

        frame_count = len(list(output_dir.glob(f"frame_*.{self.frame_format}")))

        if max_frames and frame_count > max_frames:
            self._limit_frames(output_dir, max_frames)
            frame_count = max_frames

        return frame_count

    def _extract_smart_scene_frames(
        self,
        video_path: Path,
        output_dir: Path,
        max_frames: int | None,
        quality: int
    ) -> int:
        """
        Extrae frames solo cuando la pantalla cambia realmente,
        ignorando movimientos de cursor y micro-actualizaciones de UI.

        Pipeline:
          1. Blur ligero + scene detection con umbral alto.
          2. Cooldown de 5 s entre frames.
          3. Deduplicación por hash perceptual (elimina >90 %% similares).
          4. Límite estricto a max_frames.
        """
        scene_th = float(os.getenv("SMART_SCENE_THRESHOLD", "0.5"))
        cooldown_s = float(os.getenv("SMART_SCENE_COOLDOWN", "5.0"))
        min_scene_blur = int(os.getenv("SMART_SCENE_BLUR", "2"))

        # Phase 1: detect scene-change PTS with blurred input
        detect_filter = (
            f"gblur=sigma={min_scene_blur}:steps=1,"
            f"select='gt(scene\\,{scene_th})',showinfo"
        )

        detect_cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-vf", detect_filter,
            "-f", "null",
            "-"
        ]

        result = subprocess.run(detect_cmd, capture_output=True, text=True, timeout=600)
        pts_list = []
        for line in result.stderr.splitlines():
            if "pts:" in line and "pts_time:" in line:
                try:
                    parts = line.split("pts_time:")
                    if len(parts) >= 2:
                        val = parts[1].split()[0].strip()
                        pts_list.append(float(val))
                except Exception:
                    continue

        if not pts_list:
            logger.warning("[KEYFRAMES] smart_scene: no scene changes detected")
            return 0

        # Enforce cooldown between frames
        filtered_pts = []
        last = -cooldown_s
        for pts in sorted(set(pts_list)):
            if pts - last >= cooldown_s:
                filtered_pts.append(pts)
                last = pts

        # Hard limit before extraction
        if max_frames and len(filtered_pts) > max_frames:
            step = len(filtered_pts) / max_frames
            filtered_pts = [filtered_pts[int(i * step)] for i in range(max_frames)]

        # Phase 2: extract exact frames at selected PTS
        fmt = self.frame_format
        for idx, pts in enumerate(filtered_pts):
            out_file = output_dir / f"frame_{idx:04d}.{fmt}"
            cmd = [
                self.ffmpeg_path,
                "-ss", str(pts),
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", str(quality),
                "-y",
                str(out_file)
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        extracted = sorted(output_dir.glob(f"frame_*.{fmt}"))

        # Phase 3: deduplicate perceptual hashes
        if len(extracted) > 1:
            try:
                extracted = self._deduplicate_by_hash(extracted, similarity=0.90)
            except Exception as e:
                logger.warning(f"[KEYFRAMES] dedup skipped: {e}")

        # Phase 4: final strict max_frames
        if max_frames and len(extracted) > max_frames:
            for f in extracted[max_frames:]:
                try:
                    f.unlink()
                except Exception:
                    pass
            extracted = extracted[:max_frames]

        return len(extracted)

    def _deduplicate_by_hash(
        self,
        frame_paths: list[Path],
        similarity: float = 0.90
    ) -> list[Path]:
        """
        Elimina frames consecutivos cuya similitud de hash perceptual
        supere el umbral. Conserva el primero de cada serie duplicada.

        Requiere Pillow + imagehash; lanza RuntimeError si no están.
        """
        try:
            import imagehash
            from PIL import Image
        except Exception as exc:
            raise RuntimeError("imagehash not available") from exc

        kept = []
        last_hash = None
        threshold = int((1.0 - similarity) * 64)  # ahash = 64 bits

        for path in frame_paths:
            try:
                img = Image.open(path)
                h = imagehash.average_hash(img)
            except Exception:
                kept.append(path)
                continue

            if last_hash is None or (h - last_hash) > threshold:
                kept.append(path)
                last_hash = h
            else:
                try:
                    path.unlink()
                except Exception:
                    pass

        return kept

    def _extract_interval_frames(
        self,
        video_path: Path,
        output_dir: Path,
        max_frames: int | None,
        quality: int
    ) -> int:
        """
        Extrae frames a intervalos regulares (ej. cada 30 segundos).

        Args:
            video_path: Ruta al video
            output_dir: Directorio de salida
            max_frames: Límite de frames
            quality: Calidad de compresión

        Returns:
            Número de frames extraídos
        """
        duration = self._get_video_duration(video_path)
        if duration == 0:
            return 0

        # Calcular intervalo: 1 frame cada 30 segundos o según max_frames
        if max_frames:
            interval = duration / max_frames
        else:
            interval = 30  # Por defecto, 1 frame cada 30 segundos

        fps = 1 / interval

        output_pattern = str(output_dir / f"frame_%04d.{self.frame_format}")

        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-vf", f"fps={fps:.3f}",
            "-q:v", str(quality),
            "-y",
            output_pattern
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.error(f"[KEYFRAMES] FFmpeg error: {result.stderr}")
            return 0

        frame_count = len(list(output_dir.glob(f"frame_*.{self.frame_format}")))

        return frame_count

    def _limit_frames(self, output_dir: Path, max_frames: int):
        """
        Limita el número de frames manteniendo los más importantes.

        Args:
            output_dir: Directorio con los frames
            max_frames: Número máximo de frames a mantener
        """
        # Obtener todos los frames
        frames = sorted(output_dir.glob(f"frame_*.{self.frame_format}"))

        if len(frames) <= max_frames:
            return

        # Eliminar frames excedentes (mantener los primeros)
        for frame in frames[max_frames:]:
            try:
                frame.unlink()
            except Exception as e:
                logger.warning(f"[KEYFRAMES] Error eliminando frame: {e}")

    def get_frame_list(self, video_path: Path) -> list[str]:
        """
        Obtiene la lista de frames extraídos para un video.

        Args:
            video_path: Ruta al video original

        Returns:
            Lista de rutas a los frames
        """
        _, video_name = self._get_output_paths(video_path)
        project_name = video_path.parts[-2] if len(video_path.parts) >= 2 else "default"
        frames_dir = self.output_base_dir / project_name / video_name

        if not frames_dir.exists():
            return []

        return sorted([str(f) for f in frames_dir.glob(f"frame_*.{self.frame_format}")])

    def cleanup_frames(self, video_path: Path):
        """
        Elimina todos los frames de un video.

        Args:
            video_path: Ruta al video original
        """
        _, video_name = self._get_output_paths(video_path)
        project_name = video_path.parts[-2] if len(video_path.parts) >= 2 else "default"
        frames_dir = self.output_base_dir / project_name / video_name

        if not frames_dir.exists():
            return

        try:
            # Eliminar todos los frames
            for frame in frames_dir.glob(f"frame_*.{self.frame_format}"):
                frame.unlink()

            # Eliminar directorio si está vacío
            try:
                frames_dir.rmdir()
            except OSError:
                pass  # Directorio no vacío

            logger.info(f"[KEYFRAMES] Frames eliminados: {frames_dir}")

        except Exception as e:
            logger.error(f"[KEYFRAMES] Error eliminando frames: {e}")


if __name__ == "__main__":
    # Test the keyframe extractor
    import sys

    if len(sys.argv) < 2:
        print("Uso: python keyframe_extractor.py <video_path> [method]")
        print("Métodos: iframe, scene, interval")
        sys.exit(1)

    video_path = Path(sys.argv[1])
    method = sys.argv[2] if len(sys.argv) > 2 else "iframe"

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    extractor = KeyframeExtractor()
    result = extractor.extract_keyframes(video_path, method=method)

    print("\n=== RESULTADO ===")
    print(f"Éxito: {result['success']}")
    print(f"Frames extraídos: {result['frame_count']}")
    print(f"Duración del video: {result['video_duration']:.1f}s")
    print(f"Tiempo de procesamiento: {result['processing_time']:.1f}s")
    print(f"Método: {result['method']}")
    print(f"Directorio de frames: {result['frames_dir']}")

    if result['error']:
        print(f"Error: {result['error']}")
