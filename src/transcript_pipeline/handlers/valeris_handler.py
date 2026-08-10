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


class ValerisHandler:
    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self.meetings_path = self.base_path / "meetings"

    def process(self, transcription_data, original_file_path, project_config: dict = None):
        """
        Procesa una transcripción para el proyecto Valeris.
        Crea la estructura: meetings/{Date}_{Name}/[transcripcion.md, resumen.md]
        """
        try:
            filename = original_file_path.stem
            clean_name = filename.replace("valeris_", "").replace("py_valeris", "")

            date_str = datetime.now().strftime("%Y-%m-%d")

            folder_name = f"{date_str}_{clean_name}"
            target_folder = self.meetings_path / folder_name

            target_folder.mkdir(parents=True, exist_ok=True)

            transcription_path = target_folder / "transcripcion.md"
            with open(transcription_path, 'w', encoding='utf-8') as f:
                f.write(f"# Transcripción: {clean_name}\n\n")
                f.write(f"**Fecha:** {date_str}\n")
                f.write(f"**Archivo Original:** {original_file_path.name}\n\n")
                f.write("## Contenido\n\n")
                f.write(transcription_data['text'])

            logger.info(f"[VALERIS] Transcripción guardada en: {transcription_path}")

            resumen_path = target_folder / "resumen.md"
            if not resumen_path.exists():
                if _LLM_AVAILABLE:
                    try:
                        custom_prompt = (project_config or {}).get("summary_prompt") or None
                        summary_text = _llm_summary(transcription_data['text'], system_prompt=custom_prompt)
                        resumen_path.write_text(f"# Resumen: {clean_name}\n\n{summary_text}\n", encoding='utf-8')
                        logger.info(f"[VALERIS] Resumen generado por LLM: {resumen_path}")
                    except Exception as e:
                        logger.warning(f"[VALERIS] LLM falló ({e}), usando plantilla vacía")
                        _write_empty_resumen(resumen_path, clean_name)
                else:
                    _write_empty_resumen(resumen_path, clean_name)

            return True

        except Exception as e:
            logger.error(f"[VALERIS] Error procesando {original_file_path.name}: {e}")
            return False


def _write_empty_resumen(path: Path, name: str):
    path.write_text(
        f"# Resumen: {name}\n\n## Puntos Clave\n\n*(Pendiente)*\n\n## Tareas\n\n- [ ] Revisar transcripción\n",
        encoding="utf-8"
    )
