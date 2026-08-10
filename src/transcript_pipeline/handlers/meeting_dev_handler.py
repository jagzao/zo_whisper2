"""
MeetingDevHandler — Procesa juntas/reuniones de desarrollo.

Diferencias vs tutorial handler:
- Extracción de frames por INTERVALO fijo (no smart_scene) → captura cada N seg sin importar movimiento
- OCR diff: compara texto extraído entre frames → solo analiza con Vision LLM si el contenido cambió
- Vision LLM prompt orientado a desarrollador: app, archivo, valores, código, errores
- MarkItDownScanner: escanea la carpeta de salida buscando PDF/Word/Excel/imágenes compatibles
- Reporte final integrado: transcript + contexto de pantallas + documentos encontrados
"""
import logging
import os
import subprocess
import json
import base64
import re
import tempfile
from pathlib import Path
from datetime import datetime

from transcript_pipeline.bootstrap import ensure_watcher_importable

logger = logging.getLogger(__name__)

_LLM_AVAILABLE = False
if ensure_watcher_importable():
    try:
        from watcher.core.integration.llm_client import generate_summary as _llm_summary
        _LLM_AVAILABLE = True
    except ImportError:
        pass

# OCR — opcional, mejora la detección de cambios de contenido
try:
    import pytesseract
    from PIL import Image as PILImage
    _tesseract_cmd = os.getenv("TESSERACT_CMD")
    if _tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

# MarkItDown — opcional, convierte documentos a Markdown
try:
    from markitdown import MarkItDown
    _MARKITDOWN_AVAILABLE = True
except ImportError:
    _MARKITDOWN_AVAILABLE = False

# imagehash — fallback cuando no hay OCR
try:
    import imagehash
    from PIL import Image as PILImage
    _HASH_AVAILABLE = True
except ImportError:
    _HASH_AVAILABLE = False


# Formatos que MarkItDown puede procesar
MARKITDOWN_EXTS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".html", ".htm", ".xml", ".json",
    ".epub", ".zip",
}

# Prompt para Vision LLM orientado a desarrollador
_DEV_SCREEN_PROMPT = (
    "Analiza este screenshot de una junta de desarrollo. "
    "Responde SOLO con un JSON válido (sin markdown, sin comentarios) con esta estructura exacta:\n"
    '{"app": "nombre de la aplicación o ventana principal visible", '
    '"file": "ruta o nombre del archivo abierto si se ve, o null", '
    '"content_type": "código|terminal|browser|figma|excel|slide|chat|otro", '
    '"key_values": ["valor o dato relevante visible 1", "valor 2"], '
    '"code_snippet": "fragmento de código visible si existe, o null", '
    '"error": "mensaje de error visible si existe, o null", '
    '"summary": "1-2 oraciones describiendo qué se está haciendo en pantalla"}'
)


class MeetingDevHandler:
    """Handler para juntas de desarrollo con análisis de pantalla contextual."""

    # Keywords en nombre de archivo que activan este handler
    TRIGGER_KEYWORDS = ["meeting", "junta", "reunion", "reunión", "dev_", "_dev", "standup", "retro", "sprint"]

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.meetings_path = self.base_path / "meetings"
        self.meetings_path.mkdir(parents=True, exist_ok=True)

        self.interval_seconds = int(os.getenv("MEETING_FRAME_INTERVAL", "15"))
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "kimi-k2.6")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "")
        self.max_screen_analyses = int(os.getenv("MEETING_MAX_SCREEN_ANALYSES", "30"))
        # Por defecto elimina frames después de analizarlos — solo queda el MD
        self.keep_frames = os.getenv("MEETING_KEEP_FRAMES", "false").lower() == "true"

    @classmethod
    def should_handle(cls, filename: str) -> bool:
        name_lower = filename.lower()
        return any(kw in name_lower for kw in cls.TRIGGER_KEYWORDS)

    def process(self, transcription_data: dict, original_file_path: Path, project_config: dict = None) -> bool:
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            clean_name = self._clean_name(original_file_path.stem)
            folder_name = f"{date_str}_{clean_name}"
            target_folder = self.meetings_path / folder_name
            target_folder.mkdir(parents=True, exist_ok=True)

            logger.info("[MEETING_DEV] Procesando: %s → %s", original_file_path.name, folder_name)

            # 1. Extraer datos de transcripción
            transcript_text = transcription_data.get("text", "")
            segments = transcription_data.get("segments", [])

            # 2. Extraer y analizar frames si es video (en carpeta temporal)
            screen_contexts: list[dict] = []
            ext = original_file_path.suffix.lower()
            if ext in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
                with tempfile.TemporaryDirectory(prefix="meeting_frames_") as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    screen_contexts = self._extract_and_analyze_frames(
                        original_file_path, tmp_path, segments
                    )
                    # tmp_dir se elimina automáticamente al salir del with
                logger.info("[MEETING_DEV] %d contextos de pantalla analizados (frames eliminados)", len(screen_contexts))

            # 3. Escanear documentos en la misma carpeta que el video
            doc_summaries = self._scan_documents(original_file_path.parent, target_folder)
            logger.info("[MEETING_DEV] %d documentos procesados con MarkItDown", len(doc_summaries))

            # 4. Único archivo de contexto para LLM
            context_path = target_folder / "context.md"
            self._generate_context(
                context_path, clean_name, date_str, original_file_path,
                transcript_text, segments, screen_contexts, doc_summaries
            )

            # 5. Resumen ejecutivo (más corto, solo decisiones/tareas)
            summary_path = target_folder / "summary.md"
            self._generate_summary(summary_path, clean_name, transcript_text, screen_contexts)

            logger.info("[MEETING_DEV] ✅ Completado: %s", target_folder)
            return True

        except Exception as e:
            logger.error("[MEETING_DEV] Error procesando %s: %s", original_file_path.name, e, exc_info=True)
            return False

    # ─── Frame extraction & analysis ────────────────────────────────────────

    def _extract_and_analyze_frames(self, video_path: Path, frames_folder: Path, segments: list) -> list[dict]:
        """Extrae frames cada N segundos y analiza con Vision LLM solo los que cambiaron."""
        frame_paths = self._ffmpeg_interval_extract(video_path, frames_folder)
        if not frame_paths:
            logger.warning("[MEETING_DEV] No se extrajeron frames de %s", video_path.name)
            return []

        contexts = []
        prev_ocr_text = ""
        analyses_done = 0

        for frame_path, timestamp_sec in frame_paths:
            if analyses_done >= self.max_screen_analyses:
                logger.info("[MEETING_DEV] Límite de %d análisis alcanzado", self.max_screen_analyses)
                break

            # Detectar si el contenido cambió (OCR diff o hash diff)
            changed, current_text = self._content_changed(frame_path, prev_ocr_text)
            if not changed:
                continue

            prev_ocr_text = current_text

            # Buscar texto de transcript cercano a este timestamp
            transcript_context = self._find_transcript_at(segments, timestamp_sec, window_sec=8)

            # Analizar con Vision LLM
            analysis = self._analyze_frame_vision(frame_path, transcript_context)
            if analysis:
                contexts.append({
                    "timestamp_sec": timestamp_sec,
                    "timestamp_fmt": self._fmt_time(timestamp_sec),
                    "frame": frame_path.name,
                    "transcript_context": transcript_context,
                    **analysis,
                })
                analyses_done += 1
                logger.debug("[MEETING_DEV] Frame %s analizado @ %s", frame_path.name, self._fmt_time(timestamp_sec))

        return contexts

    def _ffmpeg_interval_extract(self, video_path: Path, out_folder: Path) -> list[tuple[Path, int]]:
        """Extrae frames cada self.interval_seconds segundos vía FFmpeg."""
        pattern = str(out_folder / "frame_%04d.jpg")
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", f"fps=1/{self.interval_seconds}",
            "-q:v", "3",
            pattern,
            "-loglevel", "error",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error("[MEETING_DEV] FFmpeg error: %s", e)
            return []

        frames = sorted(out_folder.glob("frame_*.jpg"))
        # El frame N → timestamp N*interval segundos
        return [(f, (i + 1) * self.interval_seconds) for i, f in enumerate(frames)]

    def _content_changed(self, frame_path: Path, prev_text: str) -> tuple[bool, str]:
        """Retorna (cambió, texto_actual). Usa OCR si disponible, si no hash."""
        if _OCR_AVAILABLE:
            try:
                img = PILImage.open(frame_path)
                text = pytesseract.image_to_string(img, lang="spa+eng").strip()
                # Considerar "cambio" si al menos 15% del texto es diferente
                if not prev_text:
                    return True, text
                common = len(set(text.split()) & set(prev_text.split()))
                total = max(len(set(text.split())), 1)
                similarity = common / total
                return similarity < 0.85, text
            except Exception:
                pass

        if _HASH_AVAILABLE:
            try:
                img = PILImage.open(frame_path)
                h = str(imagehash.phash(img))
                changed = h != prev_text
                return changed, h
            except Exception:
                pass

        # Sin OCR ni hash: analizar siempre
        return True, ""

    def _analyze_frame_vision(self, frame_path: Path, transcript_hint: str) -> dict | None:
        """Envía el frame al Vision LLM y parsea el JSON de respuesta."""
        if not self.llm_api_key:
            return {"summary": "(Sin API key para análisis visual)", "app": None, "file": None,
                    "content_type": None, "key_values": [], "code_snippet": None, "error": None}
        try:
            with open(frame_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            import requests
            prompt = _DEV_SCREEN_PROMPT
            if transcript_hint:
                prompt += f'\n\nContexto de lo que se habló en este momento: "{transcript_hint}"'

            payload = {
                "model": self.llm_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }
                ],
                "max_tokens": 500,
                "temperature": 0,
            }
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            }
            base_url = self.llm_base_url.rstrip("/")
            resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

            # Limpiar markdown fences si el LLM las añade
            content = re.sub(r"^```[a-z]*\n?", "", content).rstrip("`").strip()
            return json.loads(content)

        except json.JSONDecodeError:
            logger.warning("[MEETING_DEV] LLM no devolvió JSON válido para %s", frame_path.name)
            return {"summary": content if "content" in dir() else "Error parsing", "app": None,
                    "file": None, "content_type": None, "key_values": [], "code_snippet": None, "error": None}
        except Exception as e:
            logger.warning("[MEETING_DEV] Vision LLM error en %s: %s", frame_path.name, e)
            return None

    # ─── MarkItDown document scanner ────────────────────────────────────────

    def _scan_documents(self, source_folder: Path, target_folder: Path) -> list[dict]:
        """Escanea source_folder buscando documentos compatibles con MarkItDown."""
        if not _MARKITDOWN_AVAILABLE:
            logger.warning("[MEETING_DEV] markitdown no instalado — omitiendo escaneo de documentos")
            return []

        summaries = []
        docs_folder = target_folder / "documents"

        try:
            # Configurar MarkItDown con Vision LLM si hay API key (para imágenes)
            if self.llm_api_key and self.llm_base_url:
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=self.llm_api_key, base_url=self.llm_base_url)
                    md = MarkItDown(llm_client=client, llm_model=self.llm_model)
                except Exception:
                    md = MarkItDown()
            else:
                md = MarkItDown()

            candidates = [
                f for f in source_folder.iterdir()
                if f.is_file() and f.suffix.lower() in MARKITDOWN_EXTS
            ]

            if not candidates:
                return []

            docs_folder.mkdir(exist_ok=True)

            for doc_path in candidates:
                try:
                    result = md.convert(str(doc_path))
                    md_text = result.text_content.strip()
                    if not md_text:
                        continue

                    # Guardar versión MD del documento
                    out_name = doc_path.stem + "_converted.md"
                    out_path = docs_folder / out_name
                    out_path.write_text(
                        f"# {doc_path.name}\n\n*Convertido por MarkItDown*\n\n{md_text}\n",
                        encoding="utf-8"
                    )

                    summaries.append({
                        "filename": doc_path.name,
                        "converted_to": out_name,
                        "preview": md_text[:500] + ("..." if len(md_text) > 500 else ""),
                        "full_length": len(md_text),
                    })
                    logger.info("[MARKITDOWN] Convertido: %s (%d chars)", doc_path.name, len(md_text))

                except Exception as e:
                    logger.warning("[MARKITDOWN] No se pudo convertir %s: %s", doc_path.name, e)

        except Exception as e:
            logger.error("[MARKITDOWN] Error escaneando documentos: %s", e)

        return summaries

    # ─── Report generation ───────────────────────────────────────────────────

    def _save_transcript(self, path: Path, name: str, date: str, original: Path,
                         text: str, segments: list):
        lines = [f"# Transcript: {name}\n", f"**Fecha:** {date}  \n",
                 f"**Archivo:** {original.name}\n\n", "## Transcripción\n\n"]
        if segments:
            for seg in segments:
                t = self._fmt_time(int(getattr(seg, "start", 0)))
                lines.append(f"`{t}` {getattr(seg, 'text', '').strip()}\n\n")
        else:
            lines.append(text)
        path.write_text("".join(lines), encoding="utf-8")

    def _generate_context(self, path: Path, name: str, date: str, original: Path,
                          transcript: str, segments: list,
                          screen_contexts: list, doc_summaries: list):
        """
        Genera context.md — archivo único optimizado para consumo por LLM.
        Sin imágenes. Solo texto estructurado con toda la información relevante.
        """
        lines = [
            f"# Contexto de Junta: {name}\n\n",
            f"> **Fecha:** {date} | **Fuente:** {original.name} | "
            f"**Momentos de pantalla capturados:** {len(screen_contexts)} | "
            f"**Documentos adjuntos:** {len(doc_summaries)}\n\n",
            "---\n\n",
            "## Instrucciones para el LLM\n\n",
            "Este archivo contiene el contexto completo de una junta de desarrollo. "
            "Úsalo para entender qué se discutió, qué pantallas se compartieron, "
            "qué código/valores estaban en pantalla, y qué documentos se revisaron. "
            "El transcript está con timestamps para correlacionar con los contextos de pantalla.\n\n",
            "---\n\n",
        ]

        # Contextos de pantalla — sección más densa para el LLM
        if screen_contexts:
            lines.append("## Lo que se vio en pantalla\n\n")
            lines.append(
                "*Capturado automáticamente cada vez que el contenido de pantalla cambió "
                "significativamente durante la junta.*\n\n"
            )
            for ctx in screen_contexts:
                app = ctx.get("app") or "Pantalla"
                lines.append(f"### [{ctx['timestamp_fmt']}] {app}\n\n")

                parts = []
                if ctx.get("file"):
                    parts.append(f"- **Archivo abierto:** `{ctx['file']}`")
                if ctx.get("content_type"):
                    parts.append(f"- **Tipo de contenido:** {ctx['content_type']}")
                if ctx.get("key_values"):
                    parts.append(f"- **Valores/datos visibles:** {', '.join(str(v) for v in ctx['key_values'])}")
                if ctx.get("error"):
                    parts.append(f"- **⚠ Error en pantalla:** `{ctx['error']}`")
                if parts:
                    lines.append("\n".join(parts) + "\n\n")

                if ctx.get("summary"):
                    lines.append(f"{ctx['summary']}\n\n")

                if ctx.get("code_snippet"):
                    lines.append(f"```\n{ctx['code_snippet']}\n```\n\n")

                if ctx.get("transcript_context"):
                    lines.append(f"> **Audio en este momento:** {ctx['transcript_context']}\n\n")

            lines.append("---\n\n")

        # Documentos adjuntos — contenido completo en texto
        if doc_summaries:
            lines.append("## Documentos revisados en la junta\n\n")
            lines.append(
                "*Archivos encontrados en la misma carpeta del video, "
                "convertidos a texto por MarkItDown.*\n\n"
            )
            for doc in doc_summaries:
                lines.append(f"### {doc['filename']}\n\n")
                lines.append(f"{doc['preview']}\n\n")
            lines.append("---\n\n")

        # Transcript con timestamps
        lines.append("## Transcript de la junta\n\n")
        if segments:
            for seg in segments:
                start = getattr(seg, "start", None)
                text = getattr(seg, "text", "").strip()
                if text:
                    t = self._fmt_time(int(start)) if start is not None else "??:??"
                    lines.append(f"`{t}` {text}\n\n")
        else:
            lines.append(transcript + "\n")

        path.write_text("".join(lines), encoding="utf-8")
        logger.info("[MEETING_DEV] context.md generado: %d chars", path.stat().st_size)

    def _generate_summary(self, path: Path, name: str, transcript: str, screen_contexts: list):
        if not _LLM_AVAILABLE or not transcript.strip():
            _write_empty_summary(path, name)
            return
        try:
            screen_summary = ""
            if screen_contexts:
                items = [f"- `{c['timestamp_fmt']}`: {c.get('summary', '')}" for c in screen_contexts[:15]]
                screen_summary = "\n\nContexto de pantallas durante la junta:\n" + "\n".join(items)

            prompt = (
                "Eres un asistente de reuniones de desarrollo de software. "
                "Analiza la transcripción y el contexto de pantallas y responde en español:\n\n"
                "## Resumen ejecutivo (3-5 bullets)\n"
                "## Decisiones técnicas tomadas\n"
                "## Tareas acordadas (con responsable si se menciona)\n"
                "## Problemas o blockers identificados\n"
                "## Próximos pasos\n\n"
                "Sé conciso y enfocado en acciones concretas."
            )
            analysis = _llm_summary(transcript + screen_summary, system_prompt=prompt)
            path.write_text(f"# Resumen: {name}\n\n{analysis}\n", encoding="utf-8")
        except Exception as e:
            logger.warning("[MEETING_DEV] LLM summary falló: %s", e)
            _write_empty_summary(path, name)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _clean_name(self, stem: str) -> str:
        for kw in ["meeting_", "junta_", "reunion_", "reunión_", "_meeting", "_junta"]:
            stem = stem.replace(kw, "").replace(kw.replace("_", ""), "")
        return stem.strip("_") or f"Meeting_{datetime.now().strftime('%Y%m%d')}"

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        h, r = divmod(int(seconds), 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    @staticmethod
    def _find_transcript_at(segments: list, target_sec: int, window_sec: int = 8) -> str:
        texts = []
        for seg in segments:
            start = getattr(seg, "start", None)
            if start is not None and abs(start - target_sec) <= window_sec:
                texts.append(getattr(seg, "text", "").strip())
        return " ".join(texts)[:300]


def _write_empty_summary(path: Path, name: str):
    path.write_text(
        f"# Resumen: {name}\n\n"
        "## Puntos Clave\n\n*(Pendiente de revisión)*\n\n"
        "## Tareas\n\n- [ ] Revisar transcript\n- [ ] Completar este resumen\n",
        encoding="utf-8",
    )
