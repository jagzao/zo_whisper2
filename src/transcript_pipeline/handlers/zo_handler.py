import logging
from datetime import datetime
from pathlib import Path

from transcript_pipeline.handlers.base import HandlerResult
from transcript_pipeline.llm.enrichment import AIEnrichmentService
from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
from transcript_pipeline.settings import SETTINGS

logger = logging.getLogger(__name__)

_ai_service = AIEnrichmentService(OpenAICompatibleProvider(SETTINGS), PrivacyGuard(SETTINGS), SETTINGS)

_INTERVIEW_PROMPT = (
    "You are an interview-prep assistant. Analyze this transcript and respond in the same language:\n\n"
    "## Executive summary (3-5 bullets)\n"
    "## Technical questions asked (list)\n"
    "## Areas the candidate could improve\n"
    "## Recommended next steps\n\n"
    "Be concise and actionable."
)

class ZoHandler:
    def __init__(self, base_path):
        self.base_path = Path(base_path)

    def process(self, transcription_data, original_file_path, project_config: dict | None = None):
        """
        Processes an interview for Zo Portfolio.
        Creates a subfolder and generates templates: Offer, Interview_Log, Summary, Study_Guide.
        """
        try:
            filename = original_file_path.stem
            clean_name = filename.replace("interview", "").replace("entrevista", "").strip("_")
            if not clean_name:
                clean_name = f"Interview_{datetime.now().strftime('%Y%m%d')}"

            target_folder = self.base_path / clean_name
            target_folder.mkdir(parents=True, exist_ok=True)

            date_str = datetime.now().strftime("%Y-%m-%d")

            log_path = target_folder / "Interview_Log.md"
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"# Interview Log: {clean_name}\n\n")
                f.write(f"**Date:** {date_str}\n")
                f.write(f"**File:** {original_file_path.name}\n\n")
                f.write("## Full Transcript\n\n")
                f.write(transcription_data['text'])
            logger.info(f"[ZO] Log saved to: {log_path}")

            offer_path = target_folder / "Offer.md"
            if not offer_path.exists():
                with open(offer_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Job Offer: {clean_name}\n\n")
                    f.write("## Position Details\n\n")
                    f.write("- **Role:** \n")
                    f.write("- **Company:** \n")
                    f.write("- **Salary:** \n\n")
                    f.write("## Requirements\n\n")
                logger.info("[ZO] Offer template created")

            summary_path = target_folder / "Summary.md"
            if not summary_path.exists():
                try:
                    custom_prompt = (project_config or {}).get("summary_prompt") or _INTERVIEW_PROMPT
                    analysis = _ai_service.summarize(
                        transcription_data['text'], project_config, system_prompt=custom_prompt
                    )
                    summary_path.write_text(
                        f"# Interview Analysis: {clean_name}\n\n{analysis}\n",
                        encoding='utf-8'
                    )
                    logger.info(f"[ZO] LLM analysis generated: {summary_path}")
                except ExternalLLMBlockedError as e:
                    logger.info(f"[ZO] LLM call blocked by privacy guard: {e}")
                    _write_empty_summary(summary_path, clean_name)
                except Exception as e:
                    logger.warning(f"[ZO] LLM failed ({e}), using template")
                    _write_empty_summary(summary_path, clean_name)

            guide_path = target_folder / "Study_Guide.md"
            if not guide_path.exists():
                with open(guide_path, 'w', encoding='utf-8') as f:
                    f.write("# Post-Interview Study Guide\n\n")
                    f.write("## Technical Questions Missed\n\n")
                    f.write("## Topics to Reinforce\n\n")
                logger.info("[ZO] Study Guide template created")

            return HandlerResult.completed(target_folder)

        except OSError as e:
            logger.error(f"[ZO] Filesystem error processing {original_file_path.name}: {e}")
            return HandlerResult.failed(str(e), retryable=True)
        except Exception as e:
            logger.error(f"[ZO] Error processing {original_file_path.name}: {e}")
            return HandlerResult.failed(str(e))


def _write_empty_summary(path: Path, name: str):
    path.write_text(
        f"# Summary and Observations: {name}\n\n"
        "## General Impressions\n\n## Feedback Received\n",
        encoding="utf-8"
    )
