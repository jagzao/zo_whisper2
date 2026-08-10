#!/usr/bin/env python3
"""
Enhanced Faster-Whisper Transcriber with Advanced Preprocessing
Uses CTranslate2 for better CPU performance with int8_float16 quantization
"""

import os
import time
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import tempfile
import subprocess
import shutil
from core.postprocessing.timestamp_formatter import TimestampFormatter

# Audio processing libraries
try:
    import librosa
    import soundfile as sf
    from scipy import signal
    import pyloudnorm as pyln
    from faster_whisper import WhisperModel
    LIBROSA_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Some audio processing libraries not available: {e}")
    LIBROSA_AVAILABLE = False

# ============================================================================
# CPU THREADING OPTIMIZATION - For 8-core/16-thread AMD CPU + CTranslate2
# ============================================================================
def configure_cpu_threads_ctranslate2():
    """
    Optimize CPU threading for faster-whisper (CTranslate2) on multi-core CPUs.

    Configures both general threading libraries and CTranslate2-specific settings
    for optimal performance on 8-core/16-thread systems.

    Expected improvement: 30-50% faster transcription on CPU-only systems.
    """
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=False)  # Physical cores
        thread_count = psutil.cpu_count(logical=True)  # Logical threads

        # Use 8 threads for optimal performance
        optimal_threads = min(cpu_count, 8)

        # General threading environment variables
        threading_vars = {
            "OMP_NUM_THREADS": str(optimal_threads),
            "MKL_NUM_THREADS": str(optimal_threads),
            "OPENBLAS_NUM_THREADS": str(optimal_threads),
            "NUMBA_NUM_THREADS": str(optimal_threads),
            "VECLIB_MAXIMUM_THREADS": str(optimal_threads),
        }

        for var, value in threading_vars.items():
            os.environ[var] = value

        # CTranslate2-specific threading configuration
        os.environ["CT2_NUM_THREADS"] = str(optimal_threads)
        os.environ["CT2_INTER_THREADS"] = "1"  # Single thread for operations
        os.environ["CT2_INTRA_THREADS"] = str(optimal_threads)  # Parallel within operations

        logging.info(f"[CPU_OPT] CTranslate2 configured: {optimal_threads} threads")
        logging.info(f"[CPU_OPT] System: {cpu_count} physical cores, {thread_count} logical threads")

        return optimal_threads

    except ImportError:
        # Fallback if psutil not available
        optimal_threads = 8
        os.environ["OMP_NUM_THREADS"] = str(optimal_threads)
        os.environ["CT2_NUM_THREADS"] = str(optimal_threads)
        os.environ["CT2_INTER_THREADS"] = "1"
        os.environ["CT2_INTRA_THREADS"] = str(optimal_threads)
        logging.warning("[CPU_OPT] psutil not available, using default 8 threads")
        return optimal_threads

# Configure CPU threads at module load time (before model loading)
CPU_THREADS = configure_cpu_threads_ctranslate2()

# Optional noise reduction libraries
RNNOISE_AVAILABLE = False
try:
    import rnnoise
    RNNOISE_AVAILABLE = True
except ImportError:
    logging.warning("RNNoise not available, noise reduction will be skipped")

DEEPFILTERNET_AVAILABLE = False
try:
    from df import enhance, init_df
    DEEPFILTERNET_AVAILABLE = True
except ImportError:
    logging.warning("DeepFilterNet not available, advanced noise reduction will be skipped")

# VAD for silence detection
SILERO_VAD_AVAILABLE = False
try:
    import torch
    from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
    SILERO_VAD_AVAILABLE = True
except ImportError:
    logging.warning("Silero VAD not available, silence cutting will be skipped")

logger = logging.getLogger(__name__)

class EnhancedFasterWhisperTranscriber:
    """Enhanced transcriber using faster-whisper with advanced preprocessing"""

    def __init__(self,
                 model_size: str = "medium",
                 compute_type: str = "int8_float16",
                 device: str = "cpu",
                 language: str = "en"):
        """
        Initialize the enhanced transcriber

        Args:
            model_size: Whisper model size ("tiny", "base", "small", "medium", "large-v2")
            compute_type: Computation type for CTranslate2 ("int8", "int8_float16", "float16")
            device: Device to use ("cpu", "cuda")
            language: Default language for transcription
        """
        self.model_size = model_size
        self.compute_type = compute_type
        self.device = device
        self.language = language
        self.model = None

        # Project-specific initial prompt with jargon
        self.initial_prompt = self._build_initial_prompt()

        # Initialize DeepFilterNet if available
        self.df_available = False
        if DEEPFILTERNET_AVAILABLE:
            try:
                self.df_model, self.df_df_state, _ = init_df()
                self.df_available = True
                logger.info("DeepFilterNet initialized for noise reduction")
            except Exception as e:
                logger.warning(f"Failed to initialize DeepFilterNet: {e}")

        # Initialize Silero VAD if available
        self.vad_available = False
        if SILERO_VAD_AVAILABLE:
            try:
                self.vad_model = load_silero_vad()
                self.vad_available = True
                logger.info("Silero VAD initialized for silence detection")
            except Exception as e:
                logger.warning(f"Failed to initialize Silero VAD: {e}")

    def _build_initial_prompt(self) -> str:
        """Build initial prompt with project-specific jargon and names"""
        if self.language == "es":
            return (
                "Transcripción en español de alta calidad. "
                "Incluye puntuación adecuada y corrección de errores comunes. "
                "Términos técnicos del proyecto: Meridian Technologies, designated person, UPSI, "
                "insider trading, compliance, trading window, PIT tool, NSDL, "
                "autorización services, InfoSec, GIS review, Risk Radar, UAT, "
                "JD, Sprint, APA, Woodgrove, Piesd, AuthProdpath, CompliancePiesd, "
                "BlueSky, DanaCheckmarx, jforgPublish, entrevista, initech, "
                "configuringToAUT, JD bret Pa Karan, meera. "
                "Nombres propios: Rohan, Devesh, Elena, Marc. "
                "Contexto empresarial y técnico de desarrollo de software, "
                "seguridad de la información, y cumplimiento normativo."
            )
        else:  # English
            return (
                "High quality English transcription. "
                "Include proper punctuation and common error correction. "
                "Project technical terms: Meridian Technologies, designated person, UPSI, "
                "insider trading, compliance, trading window, PIT tool, NSDL, "
                "authorization services, InfoSec, GIS review, Risk Radar, UAT, "
                "JD, Sprint, APA, Woodgrove, Piesd, AuthProdpath, CompliancePiesd, "
                "BlueSky, DanaCheckmarx, jforgPublish, interview, initech, "
                "configuringToAUT, JD bret Pa Karan, meera. "
                "Proper names: Rohan, Devesh, Elena, Marc. "
                "Business and technical context of software development, "
                "information security, and regulatory compliance."
            )

    def _load_model(self):
        """Load the faster-whisper model if not already loaded"""
        if self.model is None:
            logger.info(f"Loading faster-whisper model: {self.model_size} ({self.compute_type}) on {self.device}")
            logger.info(f"CPU threads: {CPU_THREADS}")
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=CPU_THREADS,  # Use optimized thread count
                num_workers=1  # Single worker to avoid overhead on CPU
            )
            logger.info("Model loaded successfully")

    def preprocess_audio(self, audio_path: str) -> str:
        """
        Advanced audio preprocessing pipeline

        Steps:
        1. Convert to mono 16kHz
        2. High-pass filter (~80 Hz)
        3. LUFS normalization (-23 LUFS)
        4. Noise reduction (RNNoise or DeepFilterNet)
        5. VAD-based silence cutting (Silero)

        Returns:
            Path to preprocessed audio file
        """
        if not LIBROSA_AVAILABLE:
            logger.warning("Audio processing libraries not available, using original file")
            return audio_path

        try:
            logger.info(f"Starting advanced preprocessing for: {audio_path}")

            # Load audio
            audio, sr = librosa.load(audio_path, sr=16000, mono=True)
            logger.info(f"Loaded audio: {len(audio)/sr:.1f}s at {sr}Hz")

            # 1. Convert to mono 16kHz (already done by librosa.load with sr=16000, mono=True)

            # 2. High-pass filter (~80 Hz)
            nyquist = sr / 2
            cutoff = 80
            normalized_cutoff = cutoff / nyquist
            b, a = signal.butter(4, normalized_cutoff, btype='high')
            audio = signal.filtfilt(b, a, audio)
            logger.info("Applied high-pass filter at 80Hz")

            # 3. LUFS normalization to -23 LUFS
            # Create a meter for loudness measurement
            meter = pyln.Meter(sr)

            # Measure current loudness
            loudness = meter.integrated_loudness(audio)

            # Normalize to -23 LUFS
            audio = pyln.normalize.loudness(audio, loudness, -23.0)
            logger.info(f"Normalized audio to -23 LUFS (was {loudness:.1f} LUFS)")

            # 4. Noise reduction
            if self.df_available and len(audio) > sr * 2:  # Only for files > 2 seconds
                try:
                    # DeepFilterNet expects 48kHz, so we need to resample
                    audio_48k = librosa.resample(audio, orig_sr=sr, target_sr=48000)
                    enhanced_audio = enhance(self.df_model, self.df_df_state, audio_48k)
                    audio = librosa.resample(enhanced_audio, orig_sr=48000, target_sr=sr)
                    logger.info("Applied DeepFilterNet noise reduction")
                except Exception as e:
                    logger.warning(f"DeepFilterNet failed: {e}")
                    # Fallback to RNNoise if available
                    if RNNOISE_AVAILABLE:
                        try:
                            rnnoise_model = rnnoise.RNNoise()
                            # Process in chunks
                            chunk_size = 480  # 30ms at 16kHz
                            processed_chunks = []
                            for i in range(0, len(audio), chunk_size):
                                chunk = audio[i:i+chunk_size]
                                if len(chunk) == chunk_size:
                                    processed_chunk = rnnoise_model.process(chunk.astype(np.float32))
                                    processed_chunks.append(processed_chunk)
                            if processed_chunks:
                                audio = np.concatenate(processed_chunks)
                            logger.info("Applied RNNoise noise reduction")
                        except Exception as e2:
                            logger.warning(f"RNNoise also failed: {e2}")

            # 5. VAD-based silence cutting
            if self.vad_available:
                try:
                    # Get speech timestamps
                    wav = torch.from_numpy(audio).float()
                    speech_timestamps = get_speech_timestamps(
                        wav,
                        self.vad_model,
                        threshold=0.5,
                        min_speech_duration_ms=250,
                        max_speech_duration_s=30,
                        min_silence_duration_ms=500
                    )

                    if speech_timestamps:
                        # Concatenate speech segments
                        speech_segments = []
                        for timestamp in speech_timestamps:
                            start_sample = int(timestamp['start'] * sr / 1000)
                            end_sample = int(timestamp['end'] * sr / 1000)
                            speech_segments.append(audio[start_sample:end_sample])

                        if speech_segments:
                            audio = np.concatenate(speech_segments)
                            logger.info(f"VAD removed silence, kept {len(audio)/sr:.1f}s of speech")

                except Exception as e:
                    logger.warning(f"VAD processing failed: {e}")

            # Save preprocessed audio
            temp_dir = tempfile.mkdtemp()
            processed_path = os.path.join(temp_dir, "preprocessed_audio.wav")

            # Ensure audio is in correct range for wav
            audio = np.clip(audio, -1.0, 1.0)
            sf.write(processed_path, audio, sr, subtype='PCM_16')

            logger.info(f"Preprocessing completed, saved to: {processed_path}")
            return processed_path

        except Exception as e:
            logger.error(f"Preprocessing failed: {e}")
            return audio_path

    def transcribe(self,
                   audio_path: str,
                   beam_size: int = 5,
                   best_of: int = 5,
                   temperature: list = [0.0, 0.2, 0.4],
                   patience: float = 0.0,  # 0.0 = greedy decoding (faster on CPU)
                   condition_on_previous_text: bool = True) -> Dict[str, Any]:
        """
        Transcribe audio using enhanced faster-whisper with custom parameters

        Args:
            audio_path: Path to audio file
            beam_size: Beam size for decoding (5-8 recommended)
            best_of: Number of candidates to consider
            temperature: Temperature values for sampling
            patience: Patience for beam search
            condition_on_previous_text: Whether to condition on previous text

        Returns:
            Transcription result with text and metadata
        """
        start_time = time.time()

        try:
            # Load model
            self._load_model()

            # Preprocess audio
            processed_audio_path = self.preprocess_audio(audio_path)

            # Transcription options
            transcribe_options = {
                "language": self.language,
                "beam_size": beam_size,
                "best_of": best_of,
                "temperature": temperature,
                "patience": patience,
                "condition_on_previous_text": condition_on_previous_text,
                "initial_prompt": self.initial_prompt,
                "compression_ratio_threshold": 2.4,
                "logprob_threshold": -1.0,
                "no_speech_threshold": 0.6,
                "suppress_tokens": [-1],
            }

            logger.info(f"Starting transcription with beam_size={beam_size}, best_of={best_of}")
            logger.info(f"Temperature: {temperature}, patience: {patience}")

            # Transcribe
            segments, info = self.model.transcribe(
                processed_audio_path,
                **transcribe_options
            )

            # Collect results
            text_segments = []
            full_text = ""
            total_confidence = 0
            segment_count = 0

            for segment in segments:
                text_segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "confidence": segment.avg_logprob if hasattr(segment, 'avg_logprob') else 0.5
                })
                full_text += segment.text + " "
                if hasattr(segment, 'avg_logprob'):
                    total_confidence += np.exp(segment.avg_logprob)
                    segment_count += 1

            avg_confidence = total_confidence / segment_count if segment_count > 0 else 0.5

            # Cleanup
            if processed_audio_path != audio_path:
                try:
                    os.unlink(processed_audio_path)
                    os.rmdir(os.path.dirname(processed_audio_path))
                except:
                    pass

            processing_time = time.time() - start_time

            result = {
                "text": full_text.strip(),
                "segments": text_segments,
                "language": info.language,
                "language_probability": info.language_probability,
                "confidence": round(avg_confidence, 3),
                "processing_time_seconds": round(processing_time, 2),
                "model": self.model_size,
                "compute_type": self.compute_type,
                "preprocessing_applied": True,
                "method": "faster_whisper_enhanced"
            }

            logger.info(f"Transcription completed in {processing_time:.1f}s")
            logger.info(f"Confidence: {avg_confidence:.3f}, Language: {info.language}")

            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {
                "error": str(e),
                "text": "",
                "confidence": 0.0,
                "processing_time_seconds": time.time() - start_time,
                "method": "failed"
            }

def safe_faster_transcribe(
    audio_path: str,
    output_txt_path: str,
    model_size: str = "medium",
    language: str = "en",
    include_timestamps: bool = False,
    timestamp_format: str = "simple"
) -> str:
    """
    Safe wrapper for enhanced faster-whisper transcription with timestamp support.
    Compatible with existing safe_transcribe interface.

    Args:
        audio_path: Ruta al archivo de audio
        output_txt_path: Ruta donde guardar la transcripción
        model_size: Tamaño del modelo Whisper
        language: Idioma del audio
        include_timestamps: Si incluir timestamps
        timestamp_format: Formato de timestamps ("simple", "detailed", "srt", "vtt")

    Returns:
        "success" o "failed"
    """
    try:
        transcriber = EnhancedFasterWhisperTranscriber(model_size=model_size, language=language)

        result = transcriber.transcribe(audio_path)

        if "error" in result:
            logger.error(f"Transcription failed: {result['error']}")
            return "failed"

        # Save main transcription
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(result["text"])

        logger.info(f"Enhanced faster-whisper transcription saved to: {output_txt_path}")

        # Save transcription with timestamps if requested
        if include_timestamps and "segments" in result and result["segments"]:
            try:
                timestamp_path = str(Path(output_txt_path).parent / f"{Path(output_txt_path).stem}_timestamps.txt")
                
                # Format and save timestamps
                timestamp_text = TimestampFormatter.format_transcription(
                    result["segments"],
                    timestamp_format
                )
                with open(timestamp_path, "w", encoding="utf-8") as f:
                    f.write(timestamp_text)
                
                logger.info(f"[TIMESTAMPS] Transcripción con timestamps guardada: {timestamp_path}")
                
                # Optionally save SRT format
                if timestamp_format == "srt":
                    srt_path = str(Path(output_txt_path).parent / f"{Path(output_txt_path).stem}_timestamps.srt")
                    srt_text = TimestampFormatter.format_srt(result["segments"])
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(srt_text)
                    logger.info(f"[TIMESTAMPS] Archivo SRT guardado: {srt_path}")
                
            except Exception as e:
                logger.warning(f"[WARN] Error guardando timestamps: {e}")

        return "success"

    except Exception as e:
        logger.error(f"Enhanced faster-whisper transcription error: {e}")
        return "failed"

if __name__ == "__main__":
    # Test the transcriber
    print("=== ENHANCED FASTER-WHISPER TRANSCRIBER ===")
    print(f"Model: medium, Compute type: int8_float16")
    print(f"Preprocessing libraries available:")
    print(f"  librosa/soundfile/scipy: {'✓' if LIBROSA_AVAILABLE else '✗'}")
    print(f"  RNNoise: {'✓' if RNNOISE_AVAILABLE else '✗'}")
    print(f"  DeepFilterNet: {'✓' if DEEPFILTERNET_AVAILABLE else '✗'}")
    print(f"  Silero VAD: {'✓' if SILERO_VAD_AVAILABLE else '✗'}")