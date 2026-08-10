"""
MeetingDevHandler — Processes development team meetings.

Differences vs. the tutorial handler:
- Frame extraction at a fixed INTERVAL (not smart_scene) → captures every N sec regardless of motion
- OCR diff: compares extracted text between frames → only runs the Vision LLM if content changed
- Developer-oriented Vision LLM prompt: app, file, values, code, errors
- MarkItDownScanner: scans the output folder for compatible PDF/Word/Excel/image files
- Integrated final report: transcript + screen context + documents found
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

# OCR — optional, improves content-change detection
try:
    import pytesseract
    from PIL import Image as PILImage
    _tesseract_cmd = os.getenv("TESSERACT_CMD")
    if _tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

# MarkItDown — optional, converts documents to Markdown
try:
    from markitdown import MarkItDown
    _MARKITDOWN_AVAILABLE = True
except ImportError:
    _MARKITDOWN_AVAILABLE = False

# imagehash — fallback when OCR isn't available
try:
    import imagehash
    from PIL import Image as PILImage
    _HASH_AVAILABLE = True
except ImportError:
    _HASH_AVAILABLE = False


# Formats MarkItDown can process
MARKITDOWN_EXTS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".html", ".htm", ".xml", ".json",
    ".epub", ".zip",
}

# Developer-oriented Vision LLM prompt
_DEV_SCREEN_PROMPT = (
    "Analyze this screenshot from a development meeting. "
    "Respond ONLY with valid JSON (no markdown, no comments) with this exact structure:\n"
    '{"app": "name of the visible application or main window", '
    '"file": "path or name of the open file if visible, or null", '
    '"content_type": "code|terminal|browser|figma|excel|slide|chat|other", '
    '"key_values": ["visible relevant value or data 1", "value 2"], '
    '"code_snippet": "visible code snippet if any, or null", '
    '"error": "visible error message if any, or null", '
    '"summary": "1-2 sentences describing what is happening on screen"}'
)


class MeetingDevHandler:
    """Handler for development meetings with contextual screen analysis."""

    # Filename keywords that trigger this handler
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
        # By default, frames are deleted after analysis — only the MD file remains
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

            logger.info("[MEETING_DEV] Processing: %s → %s", original_file_path.name, folder_name)

            # 1. Extract transcription data
            transcript_text = transcription_data.get("text", "")
            segments = transcription_data.get("segments", [])

            # 2. Extract and analyze frames if it's a video (in a temp folder)
            screen_contexts: list[dict] = []
            ext = original_file_path.suffix.lower()
            if ext in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
                with tempfile.TemporaryDirectory(prefix="meeting_frames_") as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    screen_contexts = self._extract_and_analyze_frames(
                        original_file_path, tmp_path, segments
                    )
                    # tmp_dir is removed automatically on exiting the with block
                logger.info("[MEETING_DEV] %d screen contexts analyzed (frames deleted)", len(screen_contexts))

            # 3. Scan documents in the same folder as the video
            doc_summaries = self._scan_documents(original_file_path.parent, target_folder)
            logger.info("[MEETING_DEV] %d documents processed with MarkItDown", len(doc_summaries))

            # 4. Single context file for the LLM
            context_path = target_folder / "context.md"
            self._generate_context(
                context_path, clean_name, date_str, original_file_path,
                transcript_text, segments, screen_contexts, doc_summaries
            )

            # 5. Executive summary (shorter, decisions/tasks only)
            summary_path = target_folder / "summary.md"
            self._generate_summary(summary_path, clean_name, transcript_text, screen_contexts)

            logger.info("[MEETING_DEV] Done: %s", target_folder)
            return True

        except Exception as e:
            logger.error("[MEETING_DEV] Error processing %s: %s", original_file_path.name, e, exc_info=True)
            return False

    # ─── Frame extraction & analysis ────────────────────────────────────────

    def _extract_and_analyze_frames(self, video_path: Path, frames_folder: Path, segments: list) -> list[dict]:
        """Extracts frames every N seconds and runs the Vision LLM only on the ones that changed."""
        frame_paths = self._ffmpeg_interval_extract(video_path, frames_folder)
        if not frame_paths:
            logger.warning("[MEETING_DEV] No frames extracted from %s", video_path.name)
            return []

        contexts = []
        prev_ocr_text = ""
        analyses_done = 0

        for frame_path, timestamp_sec in frame_paths:
            if analyses_done >= self.max_screen_analyses:
                logger.info("[MEETING_DEV] Limit of %d analyses reached", self.max_screen_analyses)
                break

            # Detect whether the content changed (OCR diff or hash diff)
            changed, current_text = self._content_changed(frame_path, prev_ocr_text)
            if not changed:
                continue

            prev_ocr_text = current_text

            # Look up transcript text near this timestamp
            transcript_context = self._find_transcript_at(segments, timestamp_sec, window_sec=8)

            # Analyze with the Vision LLM
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
                logger.debug("[MEETING_DEV] Frame %s analyzed @ %s", frame_path.name, self._fmt_time(timestamp_sec))

        return contexts

    def _ffmpeg_interval_extract(self, video_path: Path, out_folder: Path) -> list[tuple[Path, int]]:
        """Extracts frames every self.interval_seconds seconds via FFmpeg."""
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
        # Frame N → timestamp N*interval seconds
        return [(f, (i + 1) * self.interval_seconds) for i, f in enumerate(frames)]

    def _content_changed(self, frame_path: Path, prev_text: str) -> tuple[bool, str]:
        """Returns (changed, current_text). Uses OCR if available, hash otherwise."""
        if _OCR_AVAILABLE:
            try:
                img = PILImage.open(frame_path)
                text = pytesseract.image_to_string(img, lang="spa+eng").strip()
                # Consider it "changed" if at least 15% of the text differs
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

        # No OCR or hash available: always analyze
        return True, ""

    def _analyze_frame_vision(self, frame_path: Path, transcript_hint: str) -> dict | None:
        """Sends the frame to the Vision LLM and parses the JSON response."""
        if not self.llm_api_key:
            return {"summary": "(No API key for visual analysis)", "app": None, "file": None,
                    "content_type": None, "key_values": [], "code_snippet": None, "error": None}
        try:
            with open(frame_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            import requests
            prompt = _DEV_SCREEN_PROMPT
            if transcript_hint:
                prompt += f'\n\nContext of what was being said at this moment: "{transcript_hint}"'

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

            # Strip markdown fences if the LLM adds them
            content = re.sub(r"^```[a-z]*\n?", "", content).rstrip("`").strip()
            return json.loads(content)

        except json.JSONDecodeError:
            logger.warning("[MEETING_DEV] LLM did not return valid JSON for %s", frame_path.name)
            return {"summary": content if "content" in dir() else "Error parsing", "app": None,
                    "file": None, "content_type": None, "key_values": [], "code_snippet": None, "error": None}
        except Exception as e:
            logger.warning("[MEETING_DEV] Vision LLM error on %s: %s", frame_path.name, e)
            return None

    # ─── MarkItDown document scanner ────────────────────────────────────────

    def _scan_documents(self, source_folder: Path, target_folder: Path) -> list[dict]:
        """Scans source_folder for documents compatible with MarkItDown."""
        if not _MARKITDOWN_AVAILABLE:
            logger.warning("[MEETING_DEV] markitdown not installed — skipping document scan")
            return []

        summaries = []
        docs_folder = target_folder / "documents"

        try:
            # Configure MarkItDown with a Vision LLM if an API key is set (for images)
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

                    # Save the Markdown version of the document
                    out_name = doc_path.stem + "_converted.md"
                    out_path = docs_folder / out_name
                    out_path.write_text(
                        f"# {doc_path.name}\n\n*Converted by MarkItDown*\n\n{md_text}\n",
                        encoding="utf-8"
                    )

                    summaries.append({
                        "filename": doc_path.name,
                        "converted_to": out_name,
                        "preview": md_text[:500] + ("..." if len(md_text) > 500 else ""),
                        "full_length": len(md_text),
                    })
                    logger.info("[MARKITDOWN] Converted: %s (%d chars)", doc_path.name, len(md_text))

                except Exception as e:
                    logger.warning("[MARKITDOWN] Could not convert %s: %s", doc_path.name, e)

        except Exception as e:
            logger.error("[MARKITDOWN] Error scanning documents: %s", e)

        return summaries

    # ─── Report generation ───────────────────────────────────────────────────

    def _save_transcript(self, path: Path, name: str, date: str, original: Path,
                         text: str, segments: list):
        lines = [f"# Transcript: {name}\n", f"**Date:** {date}  \n",
                 f"**File:** {original.name}\n\n", "## Transcript\n\n"]
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
        Generates context.md — a single file optimized for LLM consumption.
        No images. Just structured text with all the relevant information.
        """
        lines = [
            f"# Meeting Context: {name}\n\n",
            f"> **Date:** {date} | **Source:** {original.name} | "
            f"**Screen moments captured:** {len(screen_contexts)} | "
            f"**Attached documents:** {len(doc_summaries)}\n\n",
            "---\n\n",
            "## Instructions for the LLM\n\n",
            "This file contains the full context of a development meeting. "
            "Use it to understand what was discussed, what screens were shared, "
            "what code/values were on screen, and what documents were reviewed. "
            "The transcript includes timestamps to correlate with the screen contexts.\n\n",
            "---\n\n",
        ]

        # Screen contexts — the densest section for the LLM
        if screen_contexts:
            lines.append("## What was seen on screen\n\n")
            lines.append(
                "*Captured automatically whenever screen content changed "
                "significantly during the meeting.*\n\n"
            )
            for ctx in screen_contexts:
                app = ctx.get("app") or "Screen"
                lines.append(f"### [{ctx['timestamp_fmt']}] {app}\n\n")

                parts = []
                if ctx.get("file"):
                    parts.append(f"- **Open file:** `{ctx['file']}`")
                if ctx.get("content_type"):
                    parts.append(f"- **Content type:** {ctx['content_type']}")
                if ctx.get("key_values"):
                    parts.append(f"- **Visible values/data:** {', '.join(str(v) for v in ctx['key_values'])}")
                if ctx.get("error"):
                    parts.append(f"- **⚠ On-screen error:** `{ctx['error']}`")
                if parts:
                    lines.append("\n".join(parts) + "\n\n")

                if ctx.get("summary"):
                    lines.append(f"{ctx['summary']}\n\n")

                if ctx.get("code_snippet"):
                    lines.append(f"```\n{ctx['code_snippet']}\n```\n\n")

                if ctx.get("transcript_context"):
                    lines.append(f"> **Audio at this moment:** {ctx['transcript_context']}\n\n")

            lines.append("---\n\n")

        # Attached documents — full text content
        if doc_summaries:
            lines.append("## Documents reviewed in the meeting\n\n")
            lines.append(
                "*Files found in the same folder as the video, "
                "converted to text by MarkItDown.*\n\n"
            )
            for doc in doc_summaries:
                lines.append(f"### {doc['filename']}\n\n")
                lines.append(f"{doc['preview']}\n\n")
            lines.append("---\n\n")

        # Transcript with timestamps
        lines.append("## Meeting transcript\n\n")
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
        logger.info("[MEETING_DEV] context.md generated: %d chars", path.stat().st_size)

    def _generate_summary(self, path: Path, name: str, transcript: str, screen_contexts: list):
        if not _LLM_AVAILABLE or not transcript.strip():
            _write_empty_summary(path, name)
            return
        try:
            screen_summary = ""
            if screen_contexts:
                items = [f"- `{c['timestamp_fmt']}`: {c.get('summary', '')}" for c in screen_contexts[:15]]
                screen_summary = "\n\nScreen context during the meeting:\n" + "\n".join(items)

            prompt = (
                "You are a software development meeting assistant. "
                "Analyze the transcript and screen context and respond in the same "
                "language as the transcript:\n\n"
                "## Executive summary (3-5 bullets)\n"
                "## Technical decisions made\n"
                "## Agreed-upon tasks (with owner if mentioned)\n"
                "## Problems or blockers identified\n"
                "## Next steps\n\n"
                "Be concise and focused on concrete actions."
            )
            analysis = _llm_summary(transcript + screen_summary, system_prompt=prompt)
            path.write_text(f"# Summary: {name}\n\n{analysis}\n", encoding="utf-8")
        except Exception as e:
            logger.warning("[MEETING_DEV] LLM summary failed: %s", e)
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
        f"# Summary: {name}\n\n"
        "## Key Points\n\n*(Pending review)*\n\n"
        "## Tasks\n\n- [ ] Review transcript\n- [ ] Complete this summary\n",
        encoding="utf-8",
    )
