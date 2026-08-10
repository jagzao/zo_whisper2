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
from typing import Dict, List

import psutil

from transcript_pipeline.bootstrap import ensure_watcher_importable
from transcript_pipeline.config import (
    AUDIO_DIR,
    FRAMES_DIR,
    PROJECT_ROOT,
    PROJECTS_CONFIG_PATH,
    TRANSCRIPTIONS_DIR,
    VIDEOS_DIR,
    load_env,
)
from transcript_pipeline.file_tracker import FileTracker
from transcript_pipeline.language import LanguageDetector
from transcript_pipeline.projects import load_projects, match_project

load_env()


def configure_cpu_threads() -> int:
    """Tunes CPU threading for CTranslate2/MKL/OpenBLAS."""
    try:
        cpu_count = psutil.cpu_count(logical=False)
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
    print("[ERROR] faster-whisper not installed")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'simple_scan.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TUTORIAL_FEATURES_AVAILABLE = False
if ensure_watcher_importable():
    try:
        from watcher.core.utils import is_tutorial_video, clean_transcription
        from watcher.core.video.keyframe_extractor import KeyframeExtractor
        from watcher.core.postprocessing.timestamp_formatter import TimestampFormatter
        TUTORIAL_FEATURES_AVAILABLE = True
        logger.info("[INIT] Tutorial features available")
    except ImportError as e:
        logger.warning(f"[WARN] Tutorial features not available: {e}")


class SimpleScanProcessor:
    """Processor built on faster-whisper, tuned for maximum quality on CPU int8."""

    SUPPORTED_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.mp4', '.mkv', '.mov', '.avi', '.webm']
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm'}

    def __init__(self):
        self.base_path = PROJECT_ROOT
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
        self._model_name = os.getenv("WHISPER_MODEL", "large-v3")

        self.keyframe_extractor = None
        if TUTORIAL_FEATURES_AVAILABLE:
            try:
                self.keyframe_extractor = KeyframeExtractor()
                logger.info("[INIT] Keyframe extractor initialized")
            except Exception as e:
                logger.warning(f"[WARN] Error initializing keyframe extractor: {e}")

        self.require_keyframes_for_videos = os.getenv("KEYFRAMES_REQUIRED", "1").strip().lower() not in {"0", "false", "no"}
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
            logger.info(f"[SCAN] Root folder: audio/")
            for subfolder in self.audio_base.iterdir():
                if subfolder.is_dir() and not subfolder.name.startswith('.'):
                    self.target_folders.append(subfolder)
                    logger.info(f"[SCAN] Folder detected: audio/{subfolder.name}")

        if self.videos_base.exists():
            self.target_folders.append(self.videos_base)
            logger.info(f"[SCAN] Root folder: Videos/")
            for subfolder in self.videos_base.iterdir():
                if subfolder.is_dir() and not subfolder.name.startswith('.'):
                    self.target_folders.append(subfolder)
                    logger.info(f"[SCAN] Folder detected: Videos/{subfolder.name}")

    def _ensure_model(self):
        if self.model is None:
            logger.info("[INIT] Loading Whisper model %s...", self._model_name)
            self.model = WhisperModel(
                self._model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=CPU_THREADS
            )
            logger.info("[INIT] Model loaded")

    def _find_project(self, audio_path: Path) -> dict | None:
        return match_project(audio_path, self._projects_config)

    def find_audio_files(self) -> List[Path]:
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

    def _ensure_keyframes(self, video_path: Path):
        """Extracts and validates keyframes for a video, with method fallback."""
        if not self._is_video_file(video_path):
            return None

        if not self.keyframe_extractor:
            msg = f"[KEYFRAMES] Extractor not available for video: {video_path.name}"
            if self.require_keyframes_for_videos:
                raise RuntimeError(msg)
            logger.warning(msg)
            return None

        primary_method = os.getenv("KEYFRAME_METHOD", "smart_scene").strip().lower() or "smart_scene"
        methods = []
        for method in [primary_method, "scene", "interval"]:
            if method not in methods:
                methods.append(method)

        for method in methods:
            logger.info(f"[KEYFRAMES] Extracting frames with method: {method}")
            result_frames = self.keyframe_extractor.extract_keyframes(
                video_path,
                method=method,
                max_frames=None
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

    def transcribe_file(self, audio_path: Path) -> Dict:
        """Transcribes an audio file at MAXIMUM QUALITY"""
        try:
            self._ensure_model()
            frame_info = self._ensure_keyframes(audio_path)

            # Detect language: prefix > lang.txt > projects.json > auto-detect
            detected_lang = self._language_detector.detect(audio_path.name, audio_path.parent)
            project = self._find_project(audio_path)
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
                'word_timestamps': os.getenv("WORD_TIMESTAMPS", "false").lower() == "true",
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
                    logger.info(f"  ✓ VAD enabled")
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
                logger.warning(f"  ⚠ VAD produced 0 segments, retrying without VAD...")
                segments_no_vad, info = self.model.transcribe(str(audio_path), **transcribe_params)
                full_text, segments_list = _collect_segments(segments_no_vad)

            transcription_text = " ".join(full_text)

            # Filler-word cleanup — opt-in via CLEAN_TRANSCRIPTION=true
            if os.getenv("CLEAN_TRANSCRIPTION", "false").lower() == "true" and TUTORIAL_FEATURES_AVAILABLE:
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
                "processing_time": elapsed
            }

            if frame_info:
                result["frame_info"] = frame_info

            logger.info(f"[OK] {audio_path.name} - {elapsed:.1f}s | {len(segments_list)} segments")

            return result

        except Exception as e:
            logger.error(f"[ERROR] {audio_path.name}: {str(e)}")
            raise

    def _integrate_transcription_with_frames(self, transcription_result: dict, frame_info: dict):
        """Merges the transcription into the frame map."""
        try:
            mapping_file = Path(frame_info["frames_dir"]) / "frame_mapping.json"

            if mapping_file.exists():
                with open(mapping_file, 'r', encoding='utf-8') as f:
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

                self._create_readable_mapping(mapping_file.parent, mapping_data)

        except Exception as e:
            logger.error(f"[FRAMES+TRANS] Error merging transcription: {e}")

    def _create_readable_mapping(self, frames_dir: Path, mapping_data: dict):
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
                    from watcher.core.integration.llm_client import describe_frames_for_tutorial
                    frame_descriptions = describe_frames_for_tutorial(
                        frames_dir, transcription_mapping
                    )
                    if frame_descriptions:
                        logger.info(f"[FRAMES+TRANS] {len(frame_descriptions)} frames described by LLM")
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

    def save_transcription(self, audio_path: Path, result: Dict):
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
        try:
            if self.tracker.is_file_processed(audio_path):
                logger.info(f"[SKIP] Already processed: {audio_path.name}")
                self.stats["already_processed"] += 1
                return True

            is_tutorial = TUTORIAL_FEATURES_AVAILABLE and is_tutorial_video(audio_path)

            if is_tutorial:
                logger.info(f"[TUTORIAL] Tutorial video detected: {audio_path.name}")
                self.stats["tutorials_processed"] += 1

            result = self.transcribe_file(audio_path)

            frame_info = result.get("frame_info")
            if frame_info:
                self._integrate_transcription_with_frames(result, frame_info)

            self.save_transcription(audio_path, result)

            self.tracker.mark_as_processed(audio_path, "completed")

            self.stats["processed"] += 1
            return True

        except Exception as e:
            logger.error(f"[ERROR] Failed processing {audio_path.name}: {str(e)}")
            self.stats["errors"] += 1
            return False

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
