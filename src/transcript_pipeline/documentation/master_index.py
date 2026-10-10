"""Consolidated INDEX.md across every session of a transcriptions tree.

`build_master_index(transcriptions_base)` scans recursively for
`**/manual/STUDY_GUIDE.md` and `**/manual/MANUAL.md`, groups sessions by
the first path level under `transcriptions_base` (the project folder —
the pipeline writes `<base>/<project>/<stem>_Frames/<stem>/manual/...`),
and writes `<transcriptions_base>/INDEX.md` in English with, per session:
video name, duration (from `manual/metadata.json` when present), up to six
Key Topics extracted from the study guide, and the manual's path relative
to the base.

Pure-stdlib and read-only over the tree except for INDEX.md itself, so it
is safe to call repeatedly (the study guide calls it after every success,
best-effort).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

INDEX_FILENAME = "INDEX.md"
_MAX_KEY_TOPICS = 6


def _format_duration(seconds) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "unknown"
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _key_topics(study_guide_path: Path) -> list[str]:
    """`### ` headings first, then bullet lines, from the study guide's
    `## Key Topics` section — both formats the renderer (and a human
    editor) may leave behind. Headings carry a `(ts, ts)` suffix that is
    stripped here; the index only wants topic names."""
    try:
        text = study_guide_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    topics: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            in_section = stripped[3:].strip().lower() == "key topics"
            continue
        if not in_section or not stripped:
            continue
        if stripped.startswith("### "):
            topic = stripped[4:].strip()
        elif stripped.startswith(("- ", "* ")):
            topic = stripped[2:].strip()
        else:
            continue
        if topic.endswith(")") and "(" in topic:
            topic = topic.rsplit("(", 1)[0].strip()
        if topic and topic not in topics:
            topics.append(topic)
        if len(topics) >= _MAX_KEY_TOPICS:
            break
    return topics


def _session_entry(manual_dir: Path, transcriptions_base: Path) -> dict:
    metadata: dict = {}
    metadata_path = manual_dir / "metadata.json"
    if metadata_path.is_file():
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metadata = loaded
        except (OSError, json.JSONDecodeError):
            pass

    manual_rel = manual_dir.relative_to(transcriptions_base).as_posix()
    study_guide_path = manual_dir / "STUDY_GUIDE.md"
    return {
        "video_name": str(metadata.get("video_name") or manual_dir.parent.name),
        "duration": _format_duration(metadata.get("duration")),
        "key_topics": _key_topics(study_guide_path) if study_guide_path.is_file() else [],
        "manual_rel": f"{manual_rel}/MANUAL.md" if (manual_dir / "MANUAL.md").is_file() else None,
        "study_guide_rel": f"{manual_rel}/STUDY_GUIDE.md" if study_guide_path.is_file() else None,
    }


def _render_index(grouped: dict[str, list[dict]], sessions: int, transcriptions_base: Path) -> str:
    lines: list[str] = []
    lines.append("# Master Index\n")
    lines.append(
        "> Auto-generated consolidated index of every session with a manual and/or "
        "study guide under this transcriptions tree. Regenerated automatically each "
        f"time a study guide is built. Root: `{transcriptions_base.name}/`\n"
    )
    if not sessions:
        lines.append("No sessions found yet — run the pipeline on a tutorial video.\n")
        return "\n".join(lines)

    for project_name in sorted(grouped):
        entries = grouped[project_name]
        lines.append(f"## {project_name} ({len(entries)} session{'s' if len(entries) != 1 else ''})\n")
        for entry in sorted(entries, key=lambda e: e["video_name"].lower()):
            lines.append(f"### {entry['video_name']}\n")
            lines.append(f"- Duration: {entry['duration']}\n")
            topics = "; ".join(entry["key_topics"])
            lines.append(f"- Key Topics: {topics or '—'}\n")
            if entry["manual_rel"]:
                lines.append(f"- Manual: `{entry['manual_rel']}`\n")
            if entry["study_guide_rel"]:
                lines.append(f"- Study Guide: `{entry['study_guide_rel']}`\n")
            lines.append("\n")
    return "\n".join(lines)


def build_master_index(transcriptions_base: Path) -> dict:
    """Scans the transcriptions tree and (re)writes INDEX.md at its root.

    Assumes the pipeline's layout: sessions live at
    `<transcriptions_base>/<project>/<stem>_Frames/<stem>/manual/`, so the
    first path level under the base is the project name. Sessions directly
    under the base (no project folder) group under `(root)`.
    """
    transcriptions_base = Path(transcriptions_base)

    manual_dirs: set[Path] = set()
    if transcriptions_base.is_dir():
        for pattern in ("**/manual/STUDY_GUIDE.md", "**/manual/MANUAL.md"):
            for marker in transcriptions_base.glob(pattern):
                manual_dirs.add(marker.parent)

    grouped: dict[str, list[dict]] = {}
    sessions = 0
    for manual_dir in sorted(manual_dirs):
        try:
            relative_parts = manual_dir.relative_to(transcriptions_base).parts
        except ValueError:
            continue
        project_name = relative_parts[0] if len(relative_parts) > 1 else "(root)"
        grouped.setdefault(project_name, []).append(_session_entry(manual_dir, transcriptions_base))
        sessions += 1

    index_path = transcriptions_base / INDEX_FILENAME
    try:
        transcriptions_base.mkdir(parents=True, exist_ok=True)
        index_path.write_text(_render_index(grouped, sessions, transcriptions_base), encoding="utf-8")
    except OSError as e:
        logger.warning("[INDEX] Could not write %s: %s", index_path, e)

    return {"sessions": sessions, "index_path": str(index_path)}
