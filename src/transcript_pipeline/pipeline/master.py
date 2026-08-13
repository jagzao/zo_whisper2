"""MasterProcessor — orchestrates file organization + transcription + routing.

Doesn't know about any specific project: `projects.json` declares the match
rules and which `ProjectHandler` (see `transcript_pipeline.handlers`) to use
for each one. Adding a new project is a JSON entry, not a code branch here.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from transcript_pipeline.config import PROJECT_ROOT, PROJECTS_CONFIG_PATH, load_env
from transcript_pipeline.handlers.base import HandlerStatus, ProjectHandler
from transcript_pipeline.handlers.client_meeting_handler import ClientMeetingHandler
from transcript_pipeline.handlers.meeting_dev_handler import MeetingDevHandler
from transcript_pipeline.handlers.zo_handler import ZoHandler
from transcript_pipeline.logging_setup import configure_logging
from transcript_pipeline.projects import load_projects, match_project
from transcript_pipeline.settings import SETTINGS

load_env()
RUN_ID = configure_logging("master_process.log")
logger = logging.getLogger(__name__)

# Imported after configure_logging() so master_process.log wins the
# process-wide logging config instead of processor.py's own simple_scan.log
# (configure_logging() is idempotent — first caller in the process wins).
from transcript_pipeline.transcription.processor import SimpleScanProcessor  # noqa: E402

HANDLER_MAP = {"client_meeting": ClientMeetingHandler, "zo": ZoHandler, "meeting_dev": MeetingDevHandler}


class MasterProcessor:
    def __init__(self):
        self.base_path = PROJECT_ROOT
        self.projects = load_projects(PROJECTS_CONFIG_PATH)

        # Build handler instances from projects.json output_path + handler key
        self._handlers: dict[str, ProjectHandler] = {}
        for proj in self.projects:
            handler_key = proj.get("handler")
            output_path = proj.get("output_path")
            if not handler_key or not output_path:
                continue
            handler_cls = HANDLER_MAP.get(handler_key)
            if not handler_cls:
                continue
            resolved = Path(output_path)
            if not resolved.exists():
                logger.warning(
                    "[CONFIG] output_path does not exist for '%s': %s — handler disabled",
                    proj["name"], output_path
                )
                continue
            self._handlers[proj["name"]] = handler_cls(str(resolved))
            logger.info("[CONFIG] Handler '%s' → %s", proj["name"], output_path)

        # Build organize map: prefix/keyword → Videos subfolder
        self._organize_map: list[tuple[str, Path]] = []
        for proj in self.projects:
            subfolder = proj.get("videos_subfolder")
            if not subfolder:
                continue
            target = self.base_path / "Videos" / subfolder
            rules = proj.get("match", {})
            for prefix in rules.get("prefix", []):
                self._organize_map.append((prefix.lower(), target))
            for kw in rules.get("filename_contains", []):
                self._organize_map.append((kw.lower(), target))

        # Icecream source folders
        self.icecream_music = SETTINGS.icecream_music
        self.icecream_videos = SETTINGS.icecream_videos

    # ── Step 1: organize ────────────────────────────────────────────────────

    def organize_files(self):
        logger.info("--- FILE ORGANIZATION ---")
        source_dirs = [
            d for d in [self.icecream_music, self.icecream_videos] if d is not None and d.exists()
        ]
        moved = 0

        for source_dir in source_dirs:
            for file_path in source_dir.iterdir():
                if not file_path.is_file():
                    continue
                name_lower = file_path.name.lower()
                target = next(
                    (dst for token, dst in self._organize_map if token in name_lower),
                    None
                )
                if target:
                    target.mkdir(parents=True, exist_ok=True)
                    dest = target / file_path.name
                    if not dest.exists():
                        try:
                            shutil.move(str(file_path), str(dest))
                            logger.info("[MOVE] %s → %s", file_path.name, target.name)
                            moved += 1
                        except Exception as e:
                            logger.error("[MOVE] Error: %s", e)

        logger.info("Files organized: %d", moved)

    # ── Step 2: transcribe + route ──────────────────────────────────────────

    def run_transcription_and_routing(self) -> bool:
        logger.info("--- TRANSCRIPTION AND ROUTING ---")
        had_errors = False
        processor = SimpleScanProcessor()
        audio_files = processor.find_audio_files()

        for audio_path in audio_files:
            if processor.tracker.is_file_processed(audio_path):
                continue

            file_log = logging.LoggerAdapter(logger, {"file_id": audio_path.stem})
            file_log.info("Processing: %s", audio_path.name)
            try:
                result = processor.transcribe_file(audio_path)

                frame_info = result.get("frame_info")
                if frame_info:
                    processor._integrate_transcription_with_frames(result, frame_info)

                processor.save_transcription(audio_path, result)

                # Dynamic routing via projects.json
                matched = match_project(audio_path, self.projects)
                if matched:
                    handler = self._handlers.get(matched["name"])
                    if handler:
                        file_log.info("[ROUTE] %s → %s", audio_path.name, matched["name"])
                        handler_result = handler.process(result, audio_path, project_config=matched)
                        if handler_result.status is HandlerStatus.COMPLETED:
                            processor.tracker.mark_as_processed(audio_path, "completed_routed")
                        elif handler_result.status is HandlerStatus.FAILED:
                            had_errors = True
                            file_log.error(
                                "[ROUTE] %s handler failed permanently for %s: %s",
                                matched["name"], audio_path.name, handler_result.detail,
                            )
                            processor.tracker.mark_as_processed(audio_path, "failed_routed")
                        else:  # RETRYABLE_FAILED — leave unmarked so the next scan retries it
                            had_errors = True
                            file_log.warning(
                                "[ROUTE] %s handler failed for %s (retryable): %s — will retry next scan",
                                matched["name"], audio_path.name, handler_result.detail,
                            )
                    else:
                        file_log.info("[ROUTE] %s → %s (no external handler)", audio_path.name, matched["name"])
                        processor.tracker.mark_as_processed(audio_path, "completed")
                else:
                    processor.tracker.mark_as_processed(audio_path, "completed")

            except Exception as e:
                file_log.error("Error processing %s: %s", audio_path.name, e)
                had_errors = True

        return not had_errors

    def run(self) -> bool:
        print("=" * 60)
        print("MASTER PROCESSOR")
        print("=" * 60)
        self.organize_files()
        success = self.run_transcription_and_routing()
        print("\nMaster process finished.")
        return success


def main() -> None:
    sys.exit(0 if MasterProcessor().run() else 1)


if __name__ == "__main__":
    main()
