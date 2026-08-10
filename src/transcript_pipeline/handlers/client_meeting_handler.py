import logging
from datetime import datetime
from pathlib import Path

from transcript_pipeline.bootstrap import ensure_watcher_importable

logger = logging.getLogger(__name__)

_LLM_AVAILABLE = False
if ensure_watcher_importable():
    try:
        from watcher.core.integration.llm_client import generate_summary as _llm_summary
        _LLM_AVAILABLE = True
    except ImportError:
        pass


class ClientMeetingHandler:
    """Handler for client dev-team meetings: transcript + summary per meeting folder."""

    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self.meetings_path = self.base_path / "meetings"

    def process(self, transcription_data, original_file_path, project_config: dict = None):
        """
        Processes a transcription for a client project.
        Creates the structure: meetings/{Date}_{Name}/[transcript.md, summary.md]
        """
        try:
            filename = original_file_path.stem
            clean_name = self._strip_prefixes(filename, project_config)

            date_str = datetime.now().strftime("%Y-%m-%d")

            folder_name = f"{date_str}_{clean_name}"
            target_folder = self.meetings_path / folder_name

            target_folder.mkdir(parents=True, exist_ok=True)

            transcript_path = target_folder / "transcript.md"
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(f"# Transcript: {clean_name}\n\n")
                f.write(f"**Date:** {date_str}\n")
                f.write(f"**Original file:** {original_file_path.name}\n\n")
                f.write("## Content\n\n")
                f.write(transcription_data['text'])

            logger.info(f"[CLIENT_MEETING] Transcript saved to: {transcript_path}")

            summary_path = target_folder / "summary.md"
            if not summary_path.exists():
                if _LLM_AVAILABLE:
                    try:
                        custom_prompt = (project_config or {}).get("summary_prompt") or None
                        summary_text = _llm_summary(transcription_data['text'], system_prompt=custom_prompt)
                        summary_path.write_text(f"# Summary: {clean_name}\n\n{summary_text}\n", encoding='utf-8')
                        logger.info(f"[CLIENT_MEETING] LLM summary generated: {summary_path}")
                    except Exception as e:
                        logger.warning(f"[CLIENT_MEETING] LLM failed ({e}), using empty template")
                        _write_empty_summary(summary_path, clean_name)
                else:
                    _write_empty_summary(summary_path, clean_name)

            return True

        except Exception as e:
            logger.error(f"[CLIENT_MEETING] Error processing {original_file_path.name}: {e}")
            return False

    @staticmethod
    def _strip_prefixes(filename: str, project_config: dict | None) -> str:
        """Strips the project's configured match prefixes/folder tokens from the filename."""
        name = filename
        rules = (project_config or {}).get("match", {})
        for prefix in rules.get("prefix", []):
            name = name.replace(prefix, "")
        for folder in rules.get("folder_contains", []):
            name = name.replace(folder, "")
        return name.strip("_") or filename


def _write_empty_summary(path: Path, name: str):
    path.write_text(
        f"# Summary: {name}\n\n## Key Points\n\n*(Pending)*\n\n## Tasks\n\n- [ ] Review transcript\n",
        encoding="utf-8"
    )
