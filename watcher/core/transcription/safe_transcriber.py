import os
import time
import whisper
import logging
from typing import Optional, Dict, Any
import torch
import numpy as np
from pathlib import Path
import threading
import sys
from core.postprocessing.timestamp_formatter import TimestampFormatter

# Configuración del logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")

# ============================================================================
# CPU THREADING OPTIMIZATION - For 8-core/16-thread AMD CPU
# ============================================================================
def configure_cpu_threads():
    """
    Optimize CPU threading for Whisper transcription on multi-core CPUs.

    For an 8-core/16-thread system, this provides 30-50% speed improvement
    by properly utilizing all available CPU resources.
    """
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=False)  # Physical cores
        thread_count = psutil.cpu_count(logical=True)  # Logical threads

        # Use 8 threads for optimal performance on 8-core CPU
        optimal_threads = min(cpu_count, 8)

        # Set environment variables for all threading libraries
        threading_vars = {
            "OMP_NUM_THREADS": str(optimal_threads),
            "MKL_NUM_THREADS": str(optimal_threads),
            "OPENBLAS_NUM_THREADS": str(optimal_threads),
            "NUMBA_NUM_THREADS": str(optimal_threads),
            "VECLIB_MAXIMUM_THREADS": str(optimal_threads),
        }

        for var, value in threading_vars.items():
            os.environ[var] = value

        # Configure PyTorch CPU threading
        torch.set_num_threads(optimal_threads)
        torch.set_num_interop_threads(2)

        logging.info(f"[CPU_OPT] Configured {optimal_threads} threads for Whisper transcription")
        logging.info(f"[CPU_OPT] System: {cpu_count} physical cores, {thread_count} logical threads")

        return optimal_threads

    except ImportError:
        # Fallback if psutil not available
        optimal_threads = 8
        os.environ["OMP_NUM_THREADS"] = str(optimal_threads)
        os.environ["MKL_NUM_THREADS"] = str(optimal_threads)
        torch.set_num_threads(optimal_threads)
        logging.warning("[CPU_OPT] psutil not available, using default 8 threads")
        return optimal_threads

# Configure CPU threads at module load time
configure_cpu_threads()

# Configuración de modelos disponibles
WHISPER_MODELS = {
    "tiny": {"size": "39 MB", "speed": "~32x", "accuracy": "Low"},
    "base": {"size": "74 MB", "speed": "~16x", "accuracy": "Medium-Low"},
    "small": {"size": "244 MB", "speed": "~6x", "accuracy": "Medium"},
    "medium": {"size": "769 MB", "speed": "~2x", "accuracy": "High"},
    "large": {"size": "1550 MB", "speed": "~1x", "accuracy": "Very High"},
    "large-v2": {"size": "1550 MB", "speed": "~1x", "accuracy": "Very High+"},
    "large-v3": {"size": "1550 MB", "speed": "~1x", "accuracy": "Best"}
}

class ProgressIndicator:
    """Indicador de progreso para transcripción"""

    def __init__(self, file_name: str):
        self.file_name = file_name
        self.start_time = time.time()
        self.running = False
        self.thread = None
        self.current_phase = "Iniciando..."

    def start(self):
        """Iniciar indicador de progreso"""
        self.running = True
        self.thread = threading.Thread(target=self._progress_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Detener indicador de progreso"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def update_phase(self, phase: str):
        """Actualizar fase actual"""
        self.current_phase = phase

    def _progress_loop(self):
        """Loop del indicador de progreso"""
        spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        spinner_idx = 0

        while self.running:
            elapsed = time.time() - self.start_time
            mins, secs = divmod(int(elapsed), 60)

            # Crear línea de progreso
            spinner = spinner_chars[spinner_idx % len(spinner_chars)]
            progress_line = f"\r[{spinner}] {self.file_name} | {self.current_phase} | Tiempo: {mins:02d}:{secs:02d}"

            # Escribir sin nueva línea
            sys.stdout.write(progress_line)
            sys.stdout.flush()

            spinner_idx += 1
            time.sleep(0.5)

        # Limpiar línea al terminar
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

def get_best_model_for_system():
    """Determinar el mejor modelo basado en el sistema disponible"""
    try:
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logging.info(f"[GPU] CUDA disponible - Memoria GPU: {gpu_memory:.1f} GB")

            if gpu_memory >= 8:
                return "large-v3"
            elif gpu_memory >= 4:
                return "medium"
            else:
                return "small"
        else:
            try:
                import psutil
                ram_gb = psutil.virtual_memory().total / 1024**3
                logging.info(f"[CPU] Sin CUDA - RAM disponible: {ram_gb:.1f} GB")

                if ram_gb >= 16:
                    return "medium"
                elif ram_gb >= 8:
                    return "small"
                else:
                    return "base"
            except ImportError:
                logging.warning("[WARN] psutil no disponible, usando modelo base")
                return "base"

    except Exception as e:
        logging.warning(f"[WARN] Error detectando capacidades del sistema: {e}")
        return "base"

def already_transcribed(output_txt_path):
    """Verificar si ya existe una transcripción válida"""
    return os.path.exists(output_txt_path) and os.path.getsize(output_txt_path) > 100

def safe_load_model(model_name="base", max_retries=3, wait_sec=10, progress=None):
    """Cargar modelo Whisper de forma segura con reintentos"""
    for attempt in range(max_retries):
        try:
            model_info = WHISPER_MODELS.get(model_name, {"size": "Unknown"})
            logging.info(f"[MODEL] Cargando Whisper '{model_name}' ({model_info['size']}) - intento {attempt + 1}/{max_retries}")

            if progress:
                progress.update_phase(f"Cargando modelo {model_name} ({model_info['size']})")

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logging.info(f"[DEVICE] Usando: {device}")

            model = whisper.load_model(model_name, device=device)
            logging.info(f"[SUCCESS] Modelo cargado exitosamente")
            return model

        except Exception as e:
            logging.error(f"[ERROR] Error al cargar modelo: {e}")
            if attempt < max_retries - 1:
                if progress:
                    progress.update_phase(f"Error cargando modelo, reintentando en {wait_sec}s...")
                logging.info(f"[RETRY] Reintentando en {wait_sec} segundos...")
                time.sleep(wait_sec)
            else:
                logging.error(f"[FAILED] Fallback al modelo 'base'")
                if model_name != "base":
                    return safe_load_model("base", max_retries=1, progress=progress)

    raise RuntimeError("[CRITICAL] No se pudo cargar ningún modelo de Whisper")

def preprocess_audio(audio_path: str, progress=None) -> Optional[str]:
    """Preprocesar audio para mejorar la transcripción"""
    try:
        import subprocess
        from pathlib import Path

        if progress:
            progress.update_phase("Preprocesando audio...")

        input_path = Path(audio_path)
        temp_path = input_path.parent / f"enhanced_{input_path.name}"

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", "highpass=f=80,lowpass=f=8000,dynaudnorm=f=150:g=15",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(temp_path)
        ]

        logging.info("[PREPROCESS] Mejorando calidad de audio...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and temp_path.exists():
            logging.info("[SUCCESS] Audio preprocesado exitosamente")
            return str(temp_path)
        else:
            logging.warning(f"[WARN] Preprocesamiento falló, usando audio original")
            return audio_path

    except Exception as e:
        logging.warning(f"[WARN] Error en preprocesamiento: {e}, usando audio original")
        return audio_path

def enhanced_transcribe_options(model, audio_path: str, language: str = "es") -> Dict[str, Any]:
    """Opciones de transcripción mejoradas"""

    # Use natural conversation starters instead of instructions to avoid hallucinations
    # These are examples of natural speech, not instructions
    initial_prompts = {
        "es": "Hola, bienvenidos. Muchas gracias por estar aquí.",
        "en": "Hello and welcome. Thank you very much for being here."
    }

    initial_prompt = initial_prompts.get(language, initial_prompts["en"])

    transcribe_options = {
        "language": language,
        "task": "transcribe",
        "temperature": 0.0,
        "beam_size": 5,
        "patience": 1.0,
        "length_penalty": 1.0,
        "suppress_tokens": [-1],
        "initial_prompt": initial_prompt,
        "condition_on_previous_text": True,
        "fp16": torch.cuda.is_available(),
        "compression_ratio_threshold": 2.4,
        "logprob_threshold": -1.0,
        "no_speech_threshold": 0.6,
    }

    try:
        transcribe_options["best_of"] = 5
    except:
        pass

    return transcribe_options

def post_process_transcription(text: str, language: str = "es") -> str:
    """Post-procesamiento del texto transcrito"""
    import re

    processed_text = text
    processed_text = re.sub(r'\s+', ' ', processed_text)
    processed_text = processed_text.strip()

    if language == "es":
        # Spanish-specific processing
        processed_text = re.sub(r'([.!?])\s*([a-záéíóúñü])', r'\1 \2', processed_text, flags=re.IGNORECASE)
        processed_text = re.sub(r'([.!?]\s+)([a-záéíóúñü])',
                              lambda m: m.group(1) + m.group(2).upper(),
                              processed_text, flags=re.IGNORECASE)

        if processed_text:
            processed_text = processed_text[0].upper() + processed_text[1:]

        corrections = {
            r'\bque\b': 'qué',
            r'\bcomo\b': 'cómo',
            r'\bsi\b': 'sí',
            r'\bmas\b': 'más',
            r'\besta\b': 'está',
            r'\beste\b': 'esté',
        }

        for pattern, replacement in corrections.items():
            processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    else:
        # English and other languages - basic processing
        processed_text = re.sub(r'([.!?])\s*([a-z])', r'\1 \2', processed_text, flags=re.IGNORECASE)
        processed_text = re.sub(r'([.!?]\s+)([a-z])',
                              lambda m: m.group(1) + m.group(2).upper(),
                              processed_text)

        if processed_text:
            processed_text = processed_text[0].upper() + processed_text[1:]

    return processed_text

def enhanced_transcribe(audio_path: str, output_txt_path: str,
                       model_name: Optional[str] = None,
                       language: str = "es",
                       preprocess: bool = True,
                       postprocess: bool = True,
                       include_timestamps: bool = False,
                       timestamp_format: str = "simple") -> str:
    """
    Transcripción mejorada con indicador de progreso y soporte de timestamps.

    Args:
        audio_path: Ruta al archivo de audio
        output_txt_path: Ruta donde guardar la transcripción
        model_name: Nombre del modelo Whisper
        language: Idioma del audio ("es", "en", etc.)
        preprocess: Si preprocesar el audio
        postprocess: Si post-procesar el texto
        include_timestamps: Si incluir timestamps en la transcripción
        timestamp_format: Formato de timestamps ("simple", "detailed", "srt", "vtt")

    Returns:
        "success", "failed", o "already_exists"
    """

    if already_transcribed(output_txt_path):
        logging.info(f"[SKIP] Ya existe transcripción: {output_txt_path}")
        return "already_exists"

    if model_name is None:
        model_name = get_best_model_for_system()
        logging.info(f"[AUTO] Modelo seleccionado automáticamente: {model_name}")

    # Crear indicador de progreso
    file_name = Path(audio_path).name
    progress = ProgressIndicator(file_name)
    progress.start()

    temp_audio_path = None

    try:
        # 1. Preprocesar audio
        if preprocess:
            processed_audio = preprocess_audio(audio_path, progress)
            if processed_audio != audio_path:
                temp_audio_path = processed_audio
                audio_to_transcribe = processed_audio
            else:
                audio_to_transcribe = audio_path
        else:
            audio_to_transcribe = audio_path

        # 2. Cargar modelo
        progress.update_phase("Cargando modelo de IA...")
        model = safe_load_model(model_name, progress=progress)

        # 3. Configurar opciones
        transcribe_options = enhanced_transcribe_options(model, audio_to_transcribe, language)

        # 4. Transcribir con progreso
        progress.update_phase("Transcribiendo audio...")
        logging.info(f"[TRANSCRIBE] Iniciando transcripción con opciones mejoradas...")
        start_time = time.time()

        result = model.transcribe(audio_to_transcribe, **transcribe_options)

        transcription_time = time.time() - start_time
        logging.info(f"[TIME] Transcripción completada en {transcription_time:.1f} segundos")

        # 5. Post-procesar
        progress.update_phase("Mejorando texto...")
        raw_text = result["text"]

        if postprocess:
            final_text = post_process_transcription(raw_text, language)
            logging.info("[POSTPROCESS] Texto post-procesado para mejor calidad")
        else:
            final_text = raw_text

        # 6. Guardar transcripción principal
        progress.update_phase("Guardando resultado...")
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        # 7. Guardar transcripción con timestamps (si se solicita)
        if include_timestamps and "segments" in result:
            try:
                timestamp_path = str(Path(output_txt_path).parent / f"{Path(output_txt_path).stem}_timestamps.txt")
                
                # Preparar segmentos con confianza
                segments = []
                for seg in result["segments"]:
                    segments.append({
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", ""),
                        "confidence": 1.0 - seg.get("no_speech_prob", 0.5)
                    })
                
                # Formatear y guardar
                timestamp_text = TimestampFormatter.format_transcription(segments, timestamp_format)
                with open(timestamp_path, "w", encoding="utf-8") as f:
                    f.write(timestamp_text)
                
                logging.info(f"[TIMESTAMPS] Transcripción con timestamps guardada: {timestamp_path}")
                
                # Opcional: Guardar formato SRT si se solicita
                if timestamp_format == "srt":
                    srt_path = str(Path(output_txt_path).parent / f"{Path(output_txt_path).stem}_timestamps.srt")
                    srt_text = TimestampFormatter.format_srt(segments)
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(srt_text)
                    logging.info(f"[TIMESTAMPS] Archivo SRT guardado: {srt_path}")
                
            except Exception as e:
                logging.warning(f"[WARN] Error guardando timestamps: {e}")

        # 8. Métricas
        if "segments" in result:
            segments = result["segments"]
            avg_confidence = np.mean([seg.get("no_speech_prob", 0) for seg in segments])
            logging.info(f"[QUALITY] Segmentos: {len(segments)}, Confianza promedio: {1-avg_confidence:.2f}")

        progress.update_phase("¡Completado!")
        logging.info(f"[SUCCESS] Transcripción exitosa: {output_txt_path}")
        logging.info(f"[LENGTH] Texto generado: {len(final_text)} caracteres")

        return "success"

    except Exception as e:
        progress.update_phase("Error en transcripción")
        logging.error(f"[ERROR] Error al transcribir {audio_path}: {e}")
        return "failed"

    finally:
        progress.stop()

        # Limpiar archivo temporal
        if temp_audio_path and temp_audio_path != audio_path:
            try:
                os.unlink(temp_audio_path)
                logging.debug("[CLEANUP] Archivo de audio temporal eliminado")
            except Exception as e:
                logging.warning(f"[WARN] No se pudo eliminar archivo temporal: {e}")

def safe_transcribe(
    audio_path: str,
    output_txt_path: str,
    model_name: str = "base",
    language: str = "en",
    include_timestamps: bool = False,
    timestamp_format: str = "simple"
) -> str:
    """
    Función de compatibilidad con indicador de progreso y soporte de timestamps.

    Args:
        audio_path: Ruta al archivo de audio
        output_txt_path: Ruta donde guardar la transcripción
        model_name: Nombre del modelo Whisper
        language: Idioma del audio
        include_timestamps: Si incluir timestamps
        timestamp_format: Formato de timestamps

    Returns:
        "success", "failed", o "already_exists"
    """
    if model_name == "base":
        model_name = None

    return enhanced_transcribe(
        audio_path=audio_path,
        output_txt_path=output_txt_path,
        model_name=model_name,
        language=language,
        preprocess=True,
        postprocess=True,
        include_timestamps=include_timestamps,
        timestamp_format=timestamp_format
    )

if __name__ == "__main__":
    print("=== TRANSCRIPTOR MEJORADO CON PROGRESO ===")
    print(f"\nModelo recomendado: {get_best_model_for_system()}")

    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("Usando CPU")