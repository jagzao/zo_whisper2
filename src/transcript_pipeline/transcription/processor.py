#!/usr/bin/env python3
"""
SIMPLE SCAN - Processor OPTIMIZED FOR MAXIMUM QUALITY

QUALITY IMPROVEMENTS:
   - Automatic language detection via filename prefix (es_, en_)
   - beam_size=10 (vs default 5) - Wider search-space exploration
   - best_of=5 - Generates 5 candidates and picks the best
   - temperature=[0.0-1.0] - Multiple temperatures for better accuracy
   - patience=2.0 - More patience in beam search
   - VAD (Voice Activity Detection) with fallback
   - condition_on_previous_text=True - Contextual coherence

PRIORITY: QUALITY > SPEED — processes everything pending in audio/ and subfolders.
"""

import os

# Fix OpenMP conflict BEFORE importing any libraries that link against OpenMP/MKL
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

from transcript_pipeline.config import (
    AUDIO_DIR,
    DATA_ROOT,
    FRAMES_DIR,
    PROJECTS_CONFIG_PATH,
    TRANSCRIPTIONS_DIR,
    VIDEOS_DIR,
    load_env,
)
from transcript_pipeline.errors import TranscriptionDependencyUnavailable
from transcript_pipeline.file_tracker import FileTracker
from transcript_pipeline.language import LanguageDetector
from transcript_pipeline.llm.enrichment import AIEnrichmentService
from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
from transcript_pipeline.logging_setup import configure_logging
from transcript_pipeline.media.utils import media_has_audio_stream
from transcript_pipeline.live_capture.models import ChunkState
from transcript_pipeline.projects import load_projects, match_project
from transcript_pipeline.settings import SETTINGS

_ai_service = AIEnrichmentService(OpenAICompatibleProvider(SETTINGS), PrivacyGuard(SETTINGS), SETTINGS)

load_env()


def configure_cpu_threads() -> int:
    """Tunes CPU threading for CTranslate2/MKL/OpenBLAS."""
    try:
        cpu_count = psutil.cpu_count(logical=False) or 4
        optimal_threads = min(cpu_count, 8)

        threading_vars = {
            "OMP_NUM_THREADS": str(optimal_threads),
            "MKL_NUM_THREADS": str(optimal_threads),
            "OPENBLAS_NUM_THREADS": str(optimal_threads),
            "CT2_NUM_THREADS": str(optimal_threads),
        }
        for var, value in threading_vars.items():
            os.environ[var] = value

        print(f"[CPU] {optimal_threads} threads configured")
        return optimal_threads
    except Exception as e:
        print(f"[CPU] Warning: {e}")
        return 4


CPU_THREADS = configure_cpu_threads()

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None  # type: ignore[assignment,misc]
    WHISPER_AVAILABLE = False

RUN_ID = configure_logging("simple_scan.log")
logger = logging.getLogger(__name__)


class CaptureProcessingCancelled(Exception):
    pass

TUTORIAL_FEATURES_AVAILABLE = False
try:
    from transcript_pipeline.documentation.engine import generate_documentation
    from transcript_pipeline.media.keyframe_extractor import KeyframeExtractor
    from transcript_pipeline.media.utils import clean_transcription, is_tutorial_video
    from transcript_pipeline.postprocessing.timestamp_formatter import TimestampFormatter
    TUTORIAL_FEATURES_AVAILABLE = True
    logger.info("[INIT] Tutorial features available")
except ImportError as e:
    logger.warning(f"[WARN] Tutorial features not available: {e}")


class SimpleScanProcessor:
    """Processor built on faster-whisper, tuned for maximum quality on CPU int8."""

    SUPPORTED_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.mp4', '.mkv', '.mov', '.avi', '.webm']
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm'}

    def __init__(self):
        self.base_path = DATA_ROOT
        self.audio_base = AUDIO_DIR
        self.videos_base = VIDEOS_DIR
        self.transcriptions_base = TRANSCRIPTIONS_DIR
        self.frames_base = FRAMES_DIR

        self.transcriptions_base.mkdir(exist_ok=True)
        self.frames_base.mkdir(exist_ok=True)

        self.tracker = FileTracker()
        self._language_detector = LanguageDetector()
        self._projects_config = load_projects(PROJECTS_CONFIG_PATH)

        self.vad_available = self._check_vad_available()
        if self.vad_available:
            logger.info("[INIT] VAD available")
        else:
            logger.warning("[INIT] VAD NOT available (onnxruntime error) - continuing without VAD")

        # Model — lazy-loaded; configurable via WHISPER_MODEL (default large-v3)
        self.model = None
        self._model_name = SETTINGS.whisper_model

        self.keyframe_extractor = None
        if TUTORIAL_FEATURES_AVAILABLE:
            try:
                self.keyframe_extractor = KeyframeExtractor()
                logger.info("[INIT] Keyframe extractor initialized")
            except Exception as e:
                logger.warning(f"[WARN] Error initializing keyframe extractor: {e}")

        self.require_keyframes_for_videos = SETTINGS.keyframes_required
        logger.info(f"[INIT] Keyframes required for videos: {self.require_keyframes_for_videos}")

        self.stats = {
            "total_found": 0,
            "already_processed": 0,
            "processed": 0,
            "errors": 0,
            "skipped": 0,
            "tutorials_processed": 0,
            "frames_extracted": 0
        }

        # Auto-detect folders (include audio/ and Videos/ roots)
        self.target_folders = []

        if self.audio_base.exists():
            self.target_folders.append(self.audio_base)
            logger.info("[SCAN] Root folder: audio/")
            for subfolder in self.audio_base.iterdir():
                if subfolder.is_dir() and not subfolder.name.startswith('.'):
                    self.target_folders.append(subfolder)
                    logger.info(f"[SCAN] Folder detected: audio/{subfolder.name}")

        if self.videos_base.exists():
            self.target_folders.append(self.videos_base)
            logger.info("[SCAN] Root folder: Videos/")
            for subfolder in self.videos_base.iterdir():
                if subfolder.is_dir() and not subfolder.name.startswith('.'):
                    self.target_folders.append(subfolder)
                    logger.info(f"[SCAN] Folder detected: Videos/{subfolder.name}")

    def _ensure_model(self):
        if self.model is None:
            if not WHISPER_AVAILABLE:
                raise TranscriptionDependencyUnavailable(
                    "faster-whisper is not installed — install it to run transcription "
                    "(pip install -e '.[dev]' or `pip install faster-whisper`)."
                )
            logger.info("[INIT] Loading Whisper model %s...", self._model_name)
            # WhisperModel is only None when WHISPER_AVAILABLE is False, already
            # ruled out above — pyright can't trace that across the two names.
            self.model = WhisperModel(  # type: ignore[misc]
                self._model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=CPU_THREADS
            )
            logger.info("[INIT] Model loaded")

    def _find_project(self, audio_path: Path) -> dict | None:
        return match_project(audio_path, self._projects_config)

    def _capture_project(self, capture) -> dict | None:
        if capture is None or not capture.project_id:
            return None
        return next(
            (project for project in self._projects_config if project.get("name") == capture.project_id),
            None,
        )

    def find_audio_files(self) -> list[Path]:
        """Finds all audio files in the target folders"""
        audio_files = []

        for folder in self.target_folders:
            if not folder.exists():
                logger.warning(f"[SCAN] Folder does not exist: {folder}")
                continue

            if folder == self.audio_base or folder == self.videos_base:
                folder_name = "audio/" if folder == self.audio_base else "Videos/"
                for ext in self.SUPPORTED_EXTENSIONS:
                    pattern = f"*{ext}"  # Non-recursive
                    files = list(folder.glob(pattern))
                    audio_files.extend(files)
                    if files:
                        logger.info(f"[SCAN] {folder_name} (root): {len(files)} {ext} files")
            else:
                for ext in self.SUPPORTED_EXTENSIONS:
                    pattern = f"**/*{ext}"
                    files = list(folder.glob(pattern))
                    audio_files.extend(files)
                    if files:
                        logger.info(f"[SCAN] {folder.name}: {len(files)} {ext} files")

        self.stats["total_found"] = len(audio_files)
        logger.info(f"[SCAN] Total found: {len(audio_files)} files")

        return audio_files

    def _check_vad_available(self) -> bool:
        try:
            import onnxruntime  # noqa: F401
            return True
        except Exception:
            return False

    def _has_video_stream(self, file_path: Path) -> bool:
        """Use ffprobe to check if file has an actual video stream (handles audio-only .mp4)."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                 str(file_path)],
                capture_output=True, text=True, timeout=10
            )
            return bool(result.stdout.strip())
        except Exception:
            return True  # assume video if ffprobe unavailable

    def _is_video_file(self, file_path: Path) -> bool:
        if file_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
            return False
        # .mp4 can be audio-only (exported from meeting tools) — verify with ffprobe
        if file_path.suffix.lower() == ".mp4":
            return self._has_video_stream(file_path)
        return True

    def _ensure_keyframes(self, video_path: Path, crop=None):
        """Extracts and validates keyframes for a video, with method fallback.

        `crop` (a normalized Live Capture `CropRegion`, or None) is forwarded
        to the extractor so capture-frame provenance is preserved; the
        extractor's own crop primitive is the single crop implementation.
        """
        if not self._is_video_file(video_path):
            return None

        if not self.keyframe_extractor:
            msg = f"[KEYFRAMES] Extractor not available for video: {video_path.name}"
            if self.require_keyframes_for_videos:
                raise RuntimeError(msg)
            logger.warning(msg)
            return None

        primary_method = SETTINGS.keyframe_method
        methods = []
        for method in [primary_method, "scene", "interval"]:
            if method not in methods:
                methods.append(method)

        for method in methods:
            logger.info(f"[KEYFRAMES] Extracting frames with method: {method}")
            result_frames = self.keyframe_extractor.extract_keyframes(
                video_path,
                method=method,
                max_frames=None,
                crop=crop,
            )

            if not result_frames.get("success"):
                logger.warning(f"[KEYFRAMES] Method {method} failed: {result_frames.get('error', 'Unknown')}")
                continue

            frame_count = int(result_frames.get("frame_count", 0) or 0)
            frames_dir = Path(result_frames.get("frames_dir", "")) if result_frames.get("frames_dir") else None

            mapping_ok = bool(frames_dir and (frames_dir / "frame_mapping.json").exists())
            files_ok = False
            if frames_dir and frames_dir.exists():
                extracted_files = list(frames_dir.glob("frame_*.png")) + list(frames_dir.glob("frame_*.jpg")) + list(frames_dir.glob("frame_*.jpeg")) + list(frames_dir.glob("frame_*.webp"))
                files_ok = len(extracted_files) > 0

            if frame_count > 0 and mapping_ok and files_ok:
                logger.info(f"[KEYFRAMES] OK ({method}) -> {frame_count} frames in {result_frames['processing_time']:.1f}s")
                logger.info(f"[KEYFRAMES] Saved to: {result_frames['frames_dir']}")
                self.stats["frames_extracted"] += frame_count
                return {
                    "frames_dir": result_frames["frames_dir"],
                    "frame_count": frame_count,
                    "video_duration": result_frames["video_duration"],
                    "method": result_frames["method"]
                }

            logger.warning(
                f"[KEYFRAMES] Incomplete result ({method}) | "
                f"frames={frame_count}, mapping_ok={mapping_ok}, files_ok={files_ok}"
            )

        msg = f"[KEYFRAMES] Could not obtain valid keyframes for {video_path.name}"
        if self.require_keyframes_for_videos:
            raise RuntimeError(msg)
        logger.warning(msg)
        return None

    def transcribe_file(self, audio_path: Path) -> dict:
        """Transcribes an audio file at MAXIMUM QUALITY.

        Live Capture chunks are resolved from their session manifest. A
        video-only chunk (manifest audio MISSING) skips Whisper entirely but
        still extracts frames; a chunk with audio, or a legacy file, runs the
        normal Whisper path. The resolved capture context travels with the
        result so `process_file` can attach provenance to the docs bundle.
        """
        capture = self._capture_context(audio_path)
        if capture is not None and self._has_audio(audio_path, capture) is False:
            return self._transcribe_capture_without_audio(audio_path, capture)

        try:
            self._ensure_model()
            assert self.model is not None  # guaranteed by _ensure_model() above
            frame_info = self._ensure_keyframes(
                audio_path, crop=capture.crop if capture is not None else None
            )
            self._assert_capture_not_cancelled(capture)

            # Detect language: prefix > lang.txt > projects.json > auto-detect
            detected_lang = self._language_detector.detect(audio_path.name, audio_path.parent)
            project = self._capture_project(capture) or self._find_project(audio_path)
            project_lang = project.get("language") if project else None
            effective_lang = detected_lang or project_lang  # filename/folder takes priority
            lang_source = "prefix" if detected_lang else ("project" if project_lang else "auto")
            logger.info(f"[TRANSCRIBE] {audio_path.name} | Language: {(effective_lang or 'AUTO').upper()} ({lang_source})")
            start_time = time.time()

            # MAXIMUM QUALITY CONFIGURATION
            transcribe_params = {
                'beam_size': 10,
                'best_of': 5,
                'temperature': [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                'patience': 2.0,
                'length_penalty': 1.0,
                'compression_ratio_threshold': 2.4,
                'log_prob_threshold': -1.0,
                'no_speech_threshold': 0.6,
                'condition_on_previous_text': True,
                'word_timestamps': SETTINGS.word_timestamps,
            }

            if effective_lang:
                transcribe_params['language'] = effective_lang

            # Per-project initial_prompt — reduces hallucinations and improves vocabulary
            project_prompt = project.get("initial_prompt") if project else None
            if project_prompt:
                transcribe_params['initial_prompt'] = project_prompt
                logger.info(f"  prompt: {project_prompt[:70]}...")

            # Use VAD only if available
            if self.vad_available:
                try:
                    segments, info = self.model.transcribe(
                        str(audio_path),
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=500),
                        **transcribe_params
                    )
                    logger.info("  ✓ VAD enabled")
                except Exception as vad_error:
                    logger.warning(f"  ⚠ VAD failed: {str(vad_error)[:50]}, continuing without VAD")
                    segments, info = self.model.transcribe(
                        str(audio_path),
                        **transcribe_params
                    )
            else:
                segments, info = self.model.transcribe(
                    str(audio_path),
                    **transcribe_params
                )

            def _collect_segments(segs):
                texts, seg_list = [], []
                for seg in segs:
                    texts.append(seg.text)
                    seg_data = {"start": seg.start, "end": seg.end, "text": seg.text}
                    if hasattr(seg, "words") and seg.words:
                        seg_data["words"] = [
                            {"word": w.word, "start": round(w.start, 3),
                             "end": round(w.end, 3), "prob": round(w.probability, 3)}
                            for w in seg.words
                        ]
                    seg_list.append(seg_data)
                return texts, seg_list

            full_text, segments_list = _collect_segments(segments)

            # If VAD filtered out all the audio, retry without VAD
            if not full_text and self.vad_available:
                logger.warning("  ⚠ VAD produced 0 segments, retrying without VAD...")
                segments_no_vad, info = self.model.transcribe(str(audio_path), **transcribe_params)
                full_text, segments_list = _collect_segments(segments_no_vad)

            transcription_text = " ".join(full_text)

            # Filler-word cleanup — opt-in via CLEAN_TRANSCRIPTION=true
            if SETTINGS.clean_transcription and TUTORIAL_FEATURES_AVAILABLE:
                clean_lang = info.language or effective_lang
                transcription_text = clean_transcription(
                    transcription_text,
                    language=clean_lang,
                    custom_fillers=project.get("custom_fillers", []) if project else [],
                    corrections=project.get("corrections", {}) if project else {},
                )

            elapsed = time.time() - start_time

            result = {
                "text": transcription_text,
                "segments": segments_list,
                "language": info.language,
                "duration": info.duration,
                "processing_time": elapsed,
                "project": project,
            }

            if frame_info:
                result["frame_info"] = frame_info
            if capture is not None:
                result["capture"] = capture

            logger.info(f"[OK] {audio_path.name} - {elapsed:.1f}s | {len(segments_list)} segments")

            return result

        except Exception as e:
            logger.error(f"[ERROR] {audio_path.name}: {str(e)}")
            raise

    # ── Live Capture bridge (W9) ─────────────────────────────────────

    def _capture_context(self, media_path: Path):
        """Resolved Live Capture context for `media_path`, or None.

        Never raises: a legacy (non-capture) path, a malformed/missing
        manifest or an uninitialized instance all yield None so the caller
        falls back to the default (non-capture) behavior.
        """
        try:
            from transcript_pipeline.live_capture.pipeline import resolve_capture_context

            return resolve_capture_context(
                Path(media_path), videos_root=getattr(self, "videos_base", None)
            )
        except Exception:
            return None

    def _has_audio(self, media_path: Path, capture) -> bool | None:
        """Whether a capture chunk carries audio.

        The manifest's explicit availability is authoritative (MISSING ->
        False, AVAILABLE -> True); UNKNOWN delegates to a real ffprobe probe,
        which returns None when it cannot decide (never raises).
        """
        from transcript_pipeline.live_capture import models as live_models

        availability = getattr(capture, "audio_availability", None)
        if availability is live_models.AudioAvailability.MISSING:
            return False
        if availability is live_models.AudioAvailability.AVAILABLE:
            return True
        return media_has_audio_stream(str(media_path))

    def _transcribe_capture_without_audio(self, audio_path: Path, capture) -> dict:
        """Video-only capture chunk: extract frames, never load Whisper.

        No transcript is invented — the late session transcript, when it
        exists, is attached later as loose untimed documentation context.
        """
        logger.info(
            "[CAPTURE] %s has no audio (manifest); extracting frames without Whisper",
            audio_path.name,
        )
        frame_info = self._ensure_keyframes(audio_path, crop=capture.crop)
        self._assert_capture_not_cancelled(capture)
        result = {
            "text": "",
            "segments": [],
            "language": None,
            "duration": float(frame_info.get("video_duration", 0.0)) if frame_info else 0.0,
            "processing_time": 0.0,
            "project": self._capture_project(capture),
            "capture": capture,
        }
        if frame_info:
            result["frame_info"] = frame_info
        return result

    def _read_frame_mapping(self, frame_info: dict) -> tuple[Path | None, dict | None]:
        try:
            mapping_file = Path(frame_info["frames_dir"]) / "frame_mapping.json"
            if not mapping_file.exists():
                return None, None
            return mapping_file, json.loads(mapping_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[CAPTURE] Could not read frame mapping: {e}")
            return None, None

    def _apply_capture_context(self, frame_info: dict, capture) -> dict | None:
        """Attaches a capture transcript as the untimed `full_transcription`.

        Runs only for a fresh processing pass, so the existing untimed
        full-transcript evidence fallback consumes it (never per-frame).
        """
        if capture is None:
            return None
        try:
            from transcript_pipeline.live_capture.integration import apply_capture_context

            mapping_file, mapping = self._read_frame_mapping(frame_info)
            if mapping_file is None or mapping is None:
                return None
            status = apply_capture_context(mapping, capture)
            mapping_file.write_text(
                json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return status
        except Exception as e:
            logger.error(f"[CAPTURE] Could not attach capture context: {e}")
            return None

    def _integrate_capture_context(self, frame_info: dict, capture) -> None:
        """Persists capture provenance + the loose session transcript.

        Stores the late session transcript under
        `transcription_summary.session_transcript` (one untimed block) so the
        Docs V2 evidence plane can consume it as explicitly loose evidence.
        """
        if capture is None:
            return
        try:
            mapping_file, mapping = self._read_frame_mapping(frame_info)
            if mapping_file is None or mapping is None:
                return
            mapping.setdefault("video_info", {})["capture"] = capture.provenance()
            transcript = getattr(capture, "transcript", None)
            summary = mapping.setdefault("transcription_summary", {})
            if transcript is not None and not str(summary.get("full_transcription") or "").strip():
                summary["session_transcript"] = {
                    "text": transcript.text,
                    "language": transcript.language,
                    "alignment": transcript.alignment,
                    "source": "live_capture_session",
                }
            mapping_file.write_text(
                json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"[CAPTURE] Could not persist capture provenance: {e}")

    def _integrate_transcription_with_frames(self, transcription_result: dict, frame_info: dict):
        """Merges the transcription into the frame map."""
        try:
            mapping_file = Path(frame_info["frames_dir"]) / "frame_mapping.json"

            if mapping_file.exists():
                with open(mapping_file, encoding='utf-8') as f:
                    mapping_data = json.load(f)

                segments = transcription_result.get('segments', [])

                transcription_mapping = {}
                for frame in mapping_data.get('frames', []):
                    frame_timestamp = frame['timestamp']

                    nearby_segments = []
                    for segment in segments:
                        seg_start = segment.get('start', 0)
                        seg_end = segment.get('end', 0)

                        if seg_start <= frame_timestamp <= seg_end or \
                           abs(frame_timestamp - seg_start) <= 2 or \
                           abs(frame_timestamp - seg_end) <= 2:
                            nearby_segments.append({
                                'start': seg_start,
                                'end': seg_end,
                                'text': segment.get('text', '').strip(),
                                'confidence': segment.get('avg_logprob', 0)
                            })

                    transcription_mapping[frame['frame_file']] = {
                        'timestamp': frame['timestamp'],
                        'formatted_timestamp': frame['timestamp_formatted'],
                        'transcription_segments': nearby_segments,
                        'full_text': ' '.join([s['text'] for s in nearby_segments])
                    }

                mapping_data['transcription_mapping'] = transcription_mapping
                mapping_data['transcription_summary'] = {
                    'total_segments': len(segments),
                    'mapped_frames': len([f for f in transcription_mapping.values() if f['transcription_segments']]),
                    'full_transcription': transcription_result.get('text', ''),
                    'language': transcription_result.get('language', 'unknown')
                }

                with open(mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(mapping_data, f, indent=2, ensure_ascii=False)

                logger.info(f"[FRAMES+TRANS] Transcription merged with frames: {mapping_file}")

                self._create_readable_mapping(
                    mapping_file.parent, mapping_data,
                    project_config=transcription_result.get("project"),
                )

        except Exception as e:
            logger.error(f"[FRAMES+TRANS] Error merging transcription: {e}")

    def _generate_documentation_bundle(self, audio_path: Path, frame_info: dict, project_config: dict | None = None):
        """Builds the human manual + AI-ready package from the frame mapping
        this same run just wrote (real PTS, transcript-aligned). Non-fatal:
        a failure here must never block the transcription output itself.
        `project_config` threads through to the same privacy gate every
        other outbound-AI call site uses (vision-LLM frame descriptions).
        """
        if not TUTORIAL_FEATURES_AVAILABLE:
            return
        try:
            frames_dir = Path(frame_info["frames_dir"])
            summary = generate_documentation(frames_dir, audio_path.name, project_config=project_config)
            logger.info(
                "[DOCS] Generated manual + AI package for %s (%d steps, %d low-confidence)",
                audio_path.name, summary["step_count"], summary["low_confidence_count"]
            )
        except Exception as e:
            logger.warning(f"[DOCS] Documentation generation skipped for {audio_path.name}: {e}")

    def _create_readable_mapping(self, frames_dir: Path, mapping_data: dict, project_config: dict | None = None):
        """
        Creates a human-readable markdown file with frames, transcription, and
        LLM visual descriptions. Visual descriptions are enabled via
        FRAME_DESCRIPTIONS=true in scan_config.env.
        """
        try:
            md_file = frames_dir / "frames_with_transcription.md"
            video_info = mapping_data.get('video_info', {})
            transcription_summary = mapping_data.get('transcription_summary', {})
            transcription_mapping = mapping_data.get('transcription_mapping', {})

            frame_descriptions = {}
            if TUTORIAL_FEATURES_AVAILABLE:
                try:
                    frame_descriptions = _ai_service.describe_frames_for_tutorial(
                        frames_dir, transcription_mapping, project_config
                    )
                    if frame_descriptions:
                        logger.info(f"[FRAMES+TRANS] {len(frame_descriptions)} frames described by LLM")
                except ExternalLLMBlockedError as e:
                    logger.info(f"[FRAMES+TRANS] Frame descriptions blocked by privacy guard: {e}")
                except Exception as e:
                    logger.warning(f"[FRAMES+TRANS] LLM description skipped: {e}")

            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(f"# Frames and Transcription: {video_info.get('name', 'Video')}\n\n")
                f.write(f"**Duration:** {video_info.get('duration_formatted', 'N/A')}\n")
                f.write(f"**Extraction method:** {video_info.get('extraction_method', 'N/A')}\n")
                f.write(f"**Total frames:** {video_info.get('total_frames', 0)}\n")
                f.write(f"**Language:** {transcription_summary.get('language', 'N/A')}\n")
                f.write(f"**Date:** {video_info.get('extraction_date', 'N/A')}\n\n")

                f.write("## Full Transcription\n\n")
                f.write(f"{transcription_summary.get('full_transcription', 'No transcription')}\n\n")

                f.write("---\n\n")
                f.write("## Frames with Transcription\n\n")

                for frame_file, frame_data in transcription_mapping.items():
                    f.write(f"### {frame_file}\n")
                    f.write(f"**Timestamp:** {frame_data.get('formatted_timestamp', 'N/A')}\n\n")

                    if frame_file in frame_descriptions:
                        f.write(f"**Visual description:** {frame_descriptions[frame_file]}\n\n")

                    full_text = frame_data.get('full_text', '').strip()
                    if full_text:
                        f.write(f"**Transcription:**\n{full_text}\n\n")
                    else:
                        f.write("*No nearby transcription*\n\n")

                    f.write("---\n\n")

            logger.info(f"[FRAMES+TRANS] Readable file created: {md_file}")

        except Exception as e:
            logger.error(f"[FRAMES+TRANS] Error creating readable file: {e}")

    def save_transcription(self, audio_path: Path, result: dict):
        """Saves the transcription"""
        try:
            relative_path = audio_path.relative_to(self.audio_base)
            output_folder = self.transcriptions_base / relative_path.parent
        except ValueError:
            try:
                relative_path = audio_path.relative_to(self.videos_base)
                output_folder = self.transcriptions_base / relative_path.parent
            except ValueError:
                output_folder = self.transcriptions_base

        output_folder.mkdir(parents=True, exist_ok=True)

        txt_path = output_folder / f"{audio_path.stem}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(result['text'])

        json_path = output_folder / f"{audio_path.stem}_metadata.json"
        metadata = {
            "audio_file": str(audio_path),
            "language": result['language'],
            "duration": result['duration'],
            "processing_time": result['processing_time'],
            "processed_at": datetime.now().isoformat(),
            "segments_count": len(result['segments'])
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Segments with timestamps, consumed by the dashboard editor
        segments_path = output_folder / f"{audio_path.stem}_segments.json"
        segments_data = {
            "audio_file": str(audio_path),
            "language": result['language'],
            "duration": result['duration'],
            "processing_time": result['processing_time'],
            "processed_at": datetime.now().isoformat(),
            "text": result['text'],
            "segments": result['segments'],
        }
        with open(segments_path, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, indent=2, ensure_ascii=False)

        is_tutorial = TUTORIAL_FEATURES_AVAILABLE and is_tutorial_video(audio_path)

        if is_tutorial and result.get('segments'):
            try:
                timestamp_path = output_folder / f"{audio_path.stem}_timestamps.txt"
                timestamp_text = TimestampFormatter.format_simple(result['segments'])

                with open(timestamp_path, 'w', encoding='utf-8') as f:
                    f.write(timestamp_text)

                logger.info(f"[TIMESTAMPS] {timestamp_path.name}")

                srt_path = output_folder / f"{audio_path.stem}_timestamps.srt"
                srt_text = TimestampFormatter.format_srt(result['segments'])

                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(srt_text)

                logger.info(f"[TIMESTAMPS] {srt_path.name}")

            except Exception as e:
                logger.warning(f"[WARN] Error saving timestamps: {e}")

        logger.info(f"[SAVE] {txt_path.name}")

    def process_file(self, audio_path: Path) -> bool:
        """Processes a single file end to end"""
        capture = self._capture_context(audio_path)
        capture_started = False
        try:
            if self.tracker.is_file_processed(audio_path):
                logger.info(f"[SKIP] Already processed: {audio_path.name}")
                self.stats["already_processed"] += 1
                return True

            if capture is not None:
                capture_started = self._set_capture_processing(capture)

            is_tutorial = TUTORIAL_FEATURES_AVAILABLE and is_tutorial_video(audio_path)

            if is_tutorial:
                logger.info(f"[TUTORIAL] Tutorial video detected: {audio_path.name}")
                self.stats["tutorials_processed"] += 1

            result = self.transcribe_file(audio_path)

            frame_info = result.get("frame_info")
            capture = result.get("capture") or capture
            if frame_info:
                self._assert_capture_not_cancelled(capture)
                self._integrate_transcription_with_frames(result, frame_info)
                if capture is not None:
                    self._integrate_capture_context(frame_info, capture)

            self.save_transcription(audio_path, result)

            if frame_info:
                self._assert_capture_not_cancelled(capture)
                self._generate_documentation_bundle(audio_path, frame_info, result.get("project"))

            if capture is not None:
                completed = self._set_capture_processed(
                    capture,
                    transcript_available=bool(result.get("text")) or capture.transcript is not None,
                )
                if not completed:
                    return False

            self.tracker.mark_as_processed(audio_path, "completed")

            self.stats["processed"] += 1
            return True

        except CaptureProcessingCancelled:
            self._set_capture_cancelled(capture)
            return False
        except Exception as e:
            if capture is not None and capture_started:
                self._set_capture_failed(capture)
            logger.error(f"[ERROR] Failed processing {audio_path.name}: {str(e)}")
            self.stats["errors"] += 1
            return False

    def _capture_service_and_chunk(self, capture):
        if capture is None or capture.chunk_index is None:
            return None, None
        from transcript_pipeline.live_capture.service import CaptureService

        return CaptureService(self.videos_base), (capture.session_id, capture.chunk_index)

    def _assert_capture_not_cancelled(self, capture) -> None:
        service, key = self._capture_service_and_chunk(capture)
        if service is not None:
            state = service.store.load_session(key[0]).get_chunk(key[1]).state
            if state is ChunkState.CANCEL_REQUESTED:
                raise CaptureProcessingCancelled("Live Capture processing cancellation requested")

    def _set_capture_processing(self, capture) -> bool:
        try:
            service, key = self._capture_service_and_chunk(capture)
            if service is None:
                return False
            session = service.store.load_session(key[0])
            chunk = session.get_chunk(key[1])
            if chunk.state in (ChunkState.FINALIZED, ChunkState.FAILED):
                service.mark_processing(*key)
                return True
        except Exception as exc:
            logger.warning("[CAPTURE] Could not persist processing state: %s", exc)
        return False

    def _set_capture_processed(self, capture, *, transcript_available: bool) -> bool:
        try:
            service, key = self._capture_service_and_chunk(capture)
            if service is None:
                return True
            result = service.complete_processing(*key, transcript_available=transcript_available)
            return result.state is ChunkState.PROCESSED
        except Exception as exc:
            logger.warning("[CAPTURE] Could not persist processed state: %s", exc)
            return True

    def _set_capture_cancelled(self, capture) -> None:
        try:
            service, key = self._capture_service_and_chunk(capture)
            if service is None:
                return
            session = service.store.load_session(key[0])
            if session.get_chunk(key[1]).state is ChunkState.CANCEL_REQUESTED:
                service.mark_cancelled(*key)
        except Exception as exc:
            logger.warning("[CAPTURE] Could not persist cancelled state: %s", exc)

    def _set_capture_failed(self, capture) -> None:
        try:
            service, key = self._capture_service_and_chunk(capture)
            if service is None:
                return
            session = service.store.load_session(key[0])
            if session.get_chunk(key[1]).state is ChunkState.PROCESSING:
                service.mark_failed(*key)
        except Exception as exc:
            logger.warning("[CAPTURE] Could not persist failed state: %s", exc)

    def run(self):
        """Runs the full processing pass"""
        print("=" * 72)
        print("SIMPLE SCAN - faster-whisper processor")
        print("=" * 72)
        print()

        self.tracker.cleanup_old_entries(days=90)

        logger.info("[INIT] Looking for audio files...")
        audio_files = self.find_audio_files()

        if not audio_files:
            logger.warning("[WARN] No audio files found")
            return

        print()
        print(f"[INFO] Files to process: {len(audio_files)}")
        print()

        start_time = time.time()

        for i, audio_path in enumerate(audio_files, 1):
            try:
                rel_path = audio_path.relative_to(self.audio_base)
                print(f"\n[{i}/{len(audio_files)}] audio/{rel_path}")
            except ValueError:
                try:
                    rel_path = audio_path.relative_to(self.videos_base)
                    print(f"\n[{i}/{len(audio_files)}] Videos/{rel_path}")
                except ValueError:
                    print(f"\n[{i}/{len(audio_files)}] {audio_path.name}")

            self.process_file(audio_path)

        total_time = time.time() - start_time

        print()
        print("=" * 72)
        print("FINAL SUMMARY")
        print("=" * 72)
        print()
        print(f"Files found:               {self.stats['total_found']}")
        print(f"Already processed (skip):  {self.stats['already_processed']}")
        print(f"Successfully processed:    {self.stats['processed']}")
        print(f"Errors:                    {self.stats['errors']}")
        if TUTORIAL_FEATURES_AVAILABLE:
            print(f"Tutorials processed:       {self.stats['tutorials_processed']}")
            print(f"Frames extracted:          {self.stats['frames_extracted']}")
        print()
        print(f"Total time:                {total_time:.1f}s")
        if self.stats['processed'] > 0:
            avg_time = total_time / self.stats['processed']
            print(f"Average time:              {avg_time:.1f}s/file")
        print()
        print(f"Results in: {self.transcriptions_base}")
        if TUTORIAL_FEATURES_AVAILABLE:
            print(f"Frames saved to: {self.frames_base}")
        print()
        print("=" * 72)

        if self.stats['errors'] > 0:
            print(f"\n[WARN] There were {self.stats['errors']} errors. Check the log.")


def main():
    try:
        processor = SimpleScanProcessor()
        processor.run()
    except KeyboardInterrupt:
        print("\n\n[CANCEL] Process cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[FATAL] Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
