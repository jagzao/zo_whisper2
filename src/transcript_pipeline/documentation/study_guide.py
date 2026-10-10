"""Exam-oriented study guide (STUDY_GUIDE.md) generated per tutorial video.

Unlike the manual (which only quotes captured evidence verbatim), the study
guide is an explicitly AI-generated *study aid*: an English guide for exam
preparation synthesized from the full transcript plus the manual's grounded
steps (titles, on-screen OCR text, timestamps). It is always labeled as
AI-generated at the top of the file.

LLM strategy for long transcripts (10-15k words are common):

- Over ~12k characters the transcript no longer fits a single prompt, so it
  is split into ~10k-character chunks with minimal overlap. Each chunk gets
  a cheap extraction pass ("topics, glossary candidates, Excel/tool
  walkthrough points with approximate timestamps", JSON out).
- A final synthesis pass receives the chunk JSONs plus the step metadata
  and produces the guide's structured content (JSON out), which this module
  renders deterministically to Markdown — section headings and layout are
  ours, only the content fields come from the LLM.
- Short transcripts skip the chunk phase entirely: one synthesis call on
  the raw transcript (a single phase).

Every LLM call goes through AIEnrichmentService.generate_text — the same
PrivacyGuard + redaction policy as every other outbound call. A guard block
returns {"status": "blocked"}; any other failure returns
{"status": "failed", ...} — this module never raises, so it can never break
the MANUAL generation that calls it (see engine.generate_documentation).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STUDY_GUIDE_FILENAME = "STUDY_GUIDE.md"

_TRANSCRIPT_LONG_THRESHOLD = 12_000
_CHUNK_TARGET = 10_000
_CHUNK_OVERLAP = 200

try:
    from transcript_pipeline.llm.enrichment import AIEnrichmentService
    from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
    from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
    from transcript_pipeline.settings import SETTINGS

    _llm_service = AIEnrichmentService(
        OpenAICompatibleProvider(SETTINGS), PrivacyGuard(SETTINGS), SETTINGS
    )
    _LLM_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in slim installs
    _llm_service = None
    _LLM_AVAILABLE = False

_CHUNK_SYSTEM_PROMPT = (
    "You extract study material from ONE CHUNK of a tutorial video transcript. "
    "Return ONLY JSON with this exact shape: "
    '{"topics": ["..."], "glossary": [{"term": "...", "definition": "..."}], '
    '"walkthroughs": [{"point": "...", "timestamp_hint": "..."}]}. '
    "Only include topics, terms, and Excel/tool/screen walkthrough points actually present "
    "in this chunk. Definitions must reflect what the transcript says, not outside knowledge."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You write English exam-preparation study guides for tutorial videos. You receive the "
    "video's procedural steps (titles, on-screen text, exact timestamps) and either the raw "
    "transcript (short videos) or JSON extractions from transcript chunks (long videos). "
    "Return ONLY JSON with this exact shape: "
    '{"overview": "5-8 sentences", '
    '"key_topics": [{"topic": "...", "details": "1-3 sentences", "timestamps": ["HH:MM:SS"]}], '
    '"glossary": [{"term": "...", "definition": "..."}], '
    '"walkthrough": [{"point": "...", "timestamp": "HH:MM:SS"}], '
    '"questions": [{"question": "...", "answer": "short answer"}]}. '
    "Timestamps must come from the provided steps/extractions only — never invent times. "
    "Produce 10 to 15 exam-style questions with short factual answers. All content in English."
)


def _find_transcript(frames_dir: Path, video_name: str) -> Path | None:
    """Locates the transcript `.txt` for a video, tolerating absence.

    Same layout convention the dashboard resolves (`_resolve_transcription`
    / `_documentation_dirs` in app.py): frames live at
    `<transcriptions>/<rel>/<stem>_Frames/<stem>/` and the transcript at
    `<transcriptions>/<rel>/<stem>.txt` — i.e. two levels above frames_dir.
    """
    stem = Path(video_name).stem
    transcriptions_dir = frames_dir.parent.parent
    for candidate in (
        transcriptions_dir / f"{stem}.txt",
        transcriptions_dir / f"{stem}_timestamps.txt",
    ):
        if candidate.is_file():
            return candidate
    return None


def _chunk_transcript(text: str) -> list[str]:
    """Splits transcripts over the threshold into ~10k-char chunks with a
    minimal overlap so a sentence cut at a boundary stays readable on the
    next chunk."""
    if len(text) <= _TRANSCRIPT_LONG_THRESHOLD:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_TARGET, len(text))
        chunks.append(text[start:end])
        start = end - _CHUNK_OVERLAP if end < len(text) else len(text)
    return chunks


def _parse_json_response(raw: str) -> dict:
    """Tolerant JSON parse: models like wrapping JSON in code fences or
    adding prose around it. Unparseable input yields {} (callers degrade
    gracefully instead of failing the whole guide)."""
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _steps_digest(manual_dir: Path) -> list[dict]:
    """Compact view of `manual/steps.json` for the synthesis prompt: what
    was demonstrated, when, and what the screen showed — the grounded
    anchors the LLM must cite timestamps from."""
    steps_path = manual_dir / "steps.json"
    if not steps_path.is_file():
        return []
    try:
        payload = json.loads(steps_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    digest = []
    for step in payload.get("steps", []):
        if not isinstance(step, dict):
            continue
        digest.append(
            {
                "title": str(step.get("title", ""))[:120],
                "timestamp_seconds": step.get("timestamp"),
                "on_screen_text": str(step.get("ocr_text") or "")[:300],
                "instruction": str(step.get("instruction") or "")[:400],
            }
        )
    return digest


def _format_ts(seconds) -> str:
    try:
        s = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return ""
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _run_extraction_passes(transcript_text: str, project_config: dict | None) -> list[dict]:
    """Phase (a): one extraction call per chunk. Only invoked for long
    transcripts — the caller checks the threshold."""
    chunks = _chunk_transcript(transcript_text)
    findings: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        user_prompt = f"Chunk {index}/{len(chunks)} of the transcript:\n\n{chunk}"
        raw = _llm_service.generate_text(
            user_prompt,
            _CHUNK_SYSTEM_PROMPT,
            project_config,
            max_tokens=2000,
            temperature=0.2,
        )
        findings.append(_parse_json_response(raw))
    return findings


def _run_synthesis(
    video_name: str,
    steps_digest: list[dict],
    findings: list[dict],
    transcript_text: str,
    project_config: dict | None,
) -> dict:
    """Phase (b): single synthesis call producing the guide's content."""
    parts = [f"Video: {video_name}"]
    parts.append("Procedural steps (grounded evidence with timestamps):")
    parts.append(json.dumps(steps_digest, ensure_ascii=False))
    if findings:
        parts.append("Transcript chunk extractions (JSON):")
        parts.append(json.dumps(findings, ensure_ascii=False))
    elif transcript_text:
        parts.append("Full transcript:")
        parts.append(transcript_text)
    else:
        parts.append("No transcript available — rely on the steps' on-screen text.")
    raw = _llm_service.generate_text(
        "\n\n".join(parts),
        _SYNTHESIS_SYSTEM_PROMPT,
        project_config,
        max_tokens=4000,
        temperature=0.2,
    )
    return _parse_json_response(raw)


def _clean_text(value) -> str:
    return str(value or "").strip()


def _render_markdown(video_name: str, content: dict) -> str:
    """Deterministic Markdown rendering — sections and headings are fixed
    here, so the file's structure never depends on LLM output shape."""
    lines: list[str] = []
    lines.append(f"# Study Guide — {video_name}\n")
    lines.append(
        "> AI-generated study aid built from this video's transcription and captured "
        "screen text. Verify every claim against the video before relying on it for an exam.\n"
    )

    lines.append("## Overview\n")
    overview = _clean_text(content.get("overview"))
    lines.append(f"{overview or '(no overview extracted)'}\n")

    lines.append("## Key Topics\n")
    topics = content.get("key_topics") if isinstance(content.get("key_topics"), list) else []
    rendered = 0
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        name = _clean_text(topic.get("topic"))
        if not name:
            continue
        timestamps = topic.get("timestamps") if isinstance(topic.get("timestamps"), list) else []
        refs = ", ".join(_clean_text(ts) for ts in timestamps[:4] if _clean_text(ts))
        lines.append(f"### {name}" + (f" ({refs})" if refs else "") + "\n")
        details = _clean_text(topic.get("details"))
        if details:
            lines.append(f"{details}\n")
        rendered += 1
    if not rendered:
        lines.append("(no key topics extracted)\n")

    lines.append("## Glossary\n")
    glossary = content.get("glossary") if isinstance(content.get("glossary"), list) else []
    rendered = 0
    for entry in glossary:
        if not isinstance(entry, dict):
            continue
        term = _clean_text(entry.get("term"))
        definition = _clean_text(entry.get("definition"))
        if term and definition:
            lines.append(f"- **{term}** — {definition}\n")
            rendered += 1
    if not rendered:
        lines.append("(no glossary terms extracted)\n")

    lines.append("## Screens, Excel & Tools Walkthrough\n")
    walkthrough = content.get("walkthrough") if isinstance(content.get("walkthrough"), list) else []
    rendered = 0
    for item in walkthrough:
        if not isinstance(item, dict):
            continue
        point = _clean_text(item.get("point"))
        if not point:
            continue
        timestamp = _format_ts(item.get("timestamp")) or _clean_text(item.get("timestamp"))
        prefix = f"`{timestamp}` — " if timestamp else ""
        lines.append(f"- {prefix}{point}\n")
        rendered += 1
    if not rendered:
        lines.append("(no walkthrough points extracted)\n")

    lines.append("## Practice Questions\n")
    questions = content.get("questions") if isinstance(content.get("questions"), list) else []
    rendered = 0
    for item in questions:
        if not isinstance(item, dict):
            continue
        question = _clean_text(item.get("question"))
        if not question:
            continue
        answer = _clean_text(item.get("answer"))
        lines.append(f"{rendered + 1}. **{question}** — {answer or '(no answer provided)'}\n")
        rendered += 1
    if not rendered:
        lines.append("(no practice questions extracted)\n")

    return "\n".join(lines)


def generate_study_guide(
    manual_dir: Path,
    frames_dir: Path,
    video_name: str,
    project_config: dict | None = None,
) -> dict:
    """Writes `manual_dir/STUDY_GUIDE.md` (always in English).

    Never raises: privacy-guard blocks return {"status": "blocked"}, any
    other failure returns {"status": "failed", "error": ...} — the manual
    generation calling this must never be broken by the study guide.

    On success it also refreshes the consolidated master index
    (`build_master_index`) using `frames_dir.parent.parent` as the
    transcriptions base — the folder that holds `<stem>_Frames/` trees,
    i.e. the project's transcriptions folder per the pipeline's layout
    convention (see `_find_transcript`).
    """
    if not _LLM_AVAILABLE:
        return {"status": "unavailable", "error": "LLM stack not importable"}

    try:
        transcript_path = _find_transcript(frames_dir, video_name)
        transcript_text = (
            transcript_path.read_text(encoding="utf-8", errors="replace") if transcript_path else ""
        )
        steps_digest = _steps_digest(manual_dir)

        if len(transcript_text) > _TRANSCRIPT_LONG_THRESHOLD:
            findings = _run_extraction_passes(transcript_text, project_config)
            raw_transcript_for_synthesis = ""
        else:
            findings = []
            raw_transcript_for_synthesis = transcript_text

        content = _run_synthesis(
            video_name, steps_digest, findings, raw_transcript_for_synthesis, project_config
        )
        if not content:
            return {"status": "failed", "error": "LLM synthesis response was not parseable JSON"}

        guide_path = manual_dir / STUDY_GUIDE_FILENAME
        manual_dir.mkdir(parents=True, exist_ok=True)
        guide_path.write_text(_render_markdown(video_name, content), encoding="utf-8")

        try:
            from transcript_pipeline.documentation.master_index import build_master_index

            build_master_index(frames_dir.parent.parent)
        except Exception as e:
            logger.warning("[STUDY-GUIDE] Master index refresh failed for %s: %s", video_name, e)

        return {"status": "ok", "path": str(guide_path), "chunks": len(findings) or 1}
    except ExternalLLMBlockedError as e:
        logger.info("[STUDY-GUIDE] Blocked by privacy guard for %s: %s", video_name, e)
        return {"status": "blocked", "error": str(e)}
    except Exception as e:
        logger.warning("[STUDY-GUIDE] Generation failed for %s: %s", video_name, e)
        return {"status": "failed", "error": str(e)}
