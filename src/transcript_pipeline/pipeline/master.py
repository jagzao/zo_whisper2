"""MasterProcessor — orquesta organización de archivos + transcripción + routing.

No conoce Valeris, Zo ni ningún proyecto en particular: `projects.json`
declara las reglas de match y qué `ProjectHandler` (ver
`transcript_pipeline.handlers`) usar para cada uno. Agregar un proyecto
nuevo es una entrada en el JSON, no una rama de código aquí.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from transcript_pipeline.config import PROJECT_ROOT, PROJECTS_CONFIG_PATH, load_env
from transcript_pipeline.handlers.meeting_dev_handler import MeetingDevHandler
from transcript_pipeline.handlers.valeris_handler import ValerisHandler
from transcript_pipeline.handlers.zo_handler import ZoHandler
from transcript_pipeline.projects import load_projects, match_project
from transcript_pipeline.transcription.processor import SimpleScanProcessor

load_env()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'master_process.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

HANDLER_MAP = {"valeris": ValerisHandler, "zo": ZoHandler, "meeting_dev": MeetingDevHandler}


class MasterProcessor:
    def __init__(self):
        self.base_path = PROJECT_ROOT
        self.projects = load_projects(PROJECTS_CONFIG_PATH)

        # Build handler instances from projects.json output_path + handler key
        self._handlers: dict[str, object] = {}
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
                    "[CONFIG] output_path no existe para '%s': %s — handler desactivado",
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
        self.icecream_music = Path(os.getenv("ICECREAM_MUSIC", ""))
        self.icecream_videos = Path(os.getenv("ICECREAM_VIDEOS", ""))

    # ── Step 1: organize ────────────────────────────────────────────────────

    def organize_files(self):
        logger.info("--- ORGANIZACIÓN DE ARCHIVOS ---")
        source_dirs = [d for d in [self.icecream_music, self.icecream_videos] if d.exists()]
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

        logger.info("Archivos organizados: %d", moved)

    # ── Step 2: transcribe + route ──────────────────────────────────────────

    def run_transcription_and_routing(self) -> bool:
        logger.info("--- TRANSCRIPCIÓN Y ROUTING ---")
        had_errors = False
        processor = SimpleScanProcessor()
        audio_files = processor.find_audio_files()

        for audio_path in audio_files:
            if processor.tracker.is_file_processed(audio_path):
                continue

            logger.info("Procesando: %s", audio_path.name)
            try:
                result = processor.transcribe_file(audio_path)

                frame_info = result.get("frame_info")
                if frame_info:
                    processor._integrate_transcription_with_frames(result, frame_info)

                processor.save_transcription(audio_path, result)

                # Dynamic routing via projects.json
                matched = match_project(audio_path, self.projects)
                routed = False
                if matched:
                    handler = self._handlers.get(matched["name"])
                    if handler:
                        logger.info("[ROUTE] %s → %s", audio_path.name, matched["name"])
                        handler.process(result, audio_path, project_config=matched)
                        routed = True
                    else:
                        logger.info("[ROUTE] %s → %s (sin handler externo)", audio_path.name, matched["name"])

                processor.tracker.mark_as_processed(
                    audio_path, "completed_routed" if routed else "completed"
                )

            except Exception as e:
                logger.error("Error procesando %s: %s", audio_path.name, e)
                had_errors = True

        return not had_errors

    def run(self) -> bool:
        print("=" * 60)
        print("MASTER PROCESSOR")
        print("=" * 60)
        self.organize_files()
        success = self.run_transcription_and_routing()
        print("\nProceso Maestro Finalizado.")
        return success


def main() -> None:
    sys.exit(0 if MasterProcessor().run() else 1)


if __name__ == "__main__":
    main()
