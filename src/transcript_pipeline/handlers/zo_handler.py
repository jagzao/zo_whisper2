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

_INTERVIEW_PROMPT = (
    "Eres un asistente de preparación de entrevistas. Analiza esta transcripción y responde en el mismo idioma:\n\n"
    "## Resumen ejecutivo (3-5 bullets)\n"
    "## Preguntas técnicas que hicieron (lista)\n"
    "## Temas donde el candidato puede mejorar\n"
    "## Próximos pasos recomendados\n\n"
    "Sé conciso y accionable."
)

class ZoHandler:
    def __init__(self, base_path):
        self.base_path = Path(base_path)

    def process(self, transcription_data, original_file_path, project_config: dict = None):
        """
        Procesa una entrevista para Zo Portfolio.
        Crea subcarpeta y genera templates: Offer, Interview_Log, Summary, Study_Guide.
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
                f.write(f"# Registro de Entrevista: {clean_name}\n\n")
                f.write(f"**Fecha:** {date_str}\n")
                f.write(f"**Archivo:** {original_file_path.name}\n\n")
                f.write("## Transcripción Completa\n\n")
                f.write(transcription_data['text'])
            logger.info(f"[ZO] Log guardado en: {log_path}")

            offer_path = target_folder / "Offer.md"
            if not offer_path.exists():
                with open(offer_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Oferta Laboral: {clean_name}\n\n")
                    f.write("## Detalles del Puesto\n\n")
                    f.write("- **Rol:** \n")
                    f.write("- **Empresa:** \n")
                    f.write("- **Salario:** \n\n")
                    f.write("## Requisitos\n\n")
                logger.info(f"[ZO] Template Offer creado")

            summary_path = target_folder / "Summary.md"
            if not summary_path.exists():
                if _LLM_AVAILABLE:
                    try:
                        custom_prompt = (project_config or {}).get("summary_prompt") or _INTERVIEW_PROMPT
                        analysis = _llm_summary(
                            transcription_data['text'],
                            system_prompt=custom_prompt
                        )
                        summary_path.write_text(
                            f"# Análisis de Entrevista: {clean_name}\n\n{analysis}\n",
                            encoding='utf-8'
                        )
                        logger.info(f"[ZO] Análisis LLM generado: {summary_path}")
                    except Exception as e:
                        logger.warning(f"[ZO] LLM falló ({e}), usando plantilla")
                        _write_empty_summary(summary_path, clean_name)
                else:
                    _write_empty_summary(summary_path, clean_name)

            guide_path = target_folder / "Study_Guide.md"
            if not guide_path.exists():
                with open(guide_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Guía de Estudio Post-Entrevista\n\n")
                    f.write("## Preguntas Técnicas Falladas\n\n")
                    f.write("## Temas a Reforzar\n\n")
                logger.info(f"[ZO] Template Study Guide creado")

            return True

        except Exception as e:
            logger.error(f"[ZO] Error procesando {original_file_path.name}: {e}")
            return False


def _write_empty_summary(path: Path, name: str):
    path.write_text(
        f"# Resumen y Observaciones: {name}\n\n"
        "## Impresiones Generales\n\n## Feedback Recibido\n",
        encoding="utf-8"
    )
