"""Unit coverage for the consolidated master index (documentation/master_index.py)."""
from __future__ import annotations

import json

from transcript_pipeline.documentation.master_index import build_master_index

GUIDE_WITH_TOPICS = """# Study Guide — clipA.mp4

> AI-generated study aid built from this video's transcription and captured screen text.

## Overview

The video covers building the monthly report.

## Key Topics

### Pivot tables (00:00:01)
Creating and refreshing pivot tables.

### Printing setup

- Excel headers and footers
- Freeze panes
- Page Layout tab

## Glossary

- **Pivot table** — A summary table that aggregates raw rows.

## Screens, Excel & Tools Walkthrough

- `00:00:06` — Insert a pivot table

## Practice Questions

1. **Which ribbon tab?** — Insert
"""


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_tree(tmp_path):
    a_manual = tmp_path / "PG" / "clipA_Frames" / "clipA" / "manual"
    _write(a_manual / "MANUAL.md", "# manual A")
    _write(a_manual / "metadata.json", json.dumps({"video_name": "clipA.mp4", "duration": 754}))
    _write(a_manual / "STUDY_GUIDE.md", GUIDE_WITH_TOPICS)

    b_manual = tmp_path / "PG" / "clipB_Frames" / "clipB" / "manual"
    _write(b_manual / "MANUAL.md", "# manual B")
    _write(b_manual / "metadata.json", json.dumps({"video_name": "clipB.mp4", "duration": 61}))

    c_manual = tmp_path / "Otros" / "clipC_Frames" / "clipC" / "manual"
    _write(c_manual / "STUDY_GUIDE.md", "# Study Guide — clipC\n\n## Overview\nx\n")
    return tmp_path


def test_build_master_index_groups_formats_and_writes_index(tmp_path):
    base = _make_tree(tmp_path)

    result = build_master_index(base)

    assert result == {"sessions": 3, "index_path": str(base / "INDEX.md")}
    index = (base / "INDEX.md").read_text(encoding="utf-8")
    assert index.startswith("# Master Index")
    # One section per project folder (first level under the base).
    assert "## PG (2 sessions)" in index
    assert "## Otros (1 session)" in index
    # Session fields: name, formatted duration, key topics, manual path.
    assert "### clipA.mp4" in index
    assert "Duration: 00:12:34" in index
    assert "Pivot tables; Printing setup; Excel headers and footers; Freeze panes; Page Layout tab" in index
    assert "`PG/clipA_Frames/clipA/manual/MANUAL.md`" in index
    assert "`PG/clipA_Frames/clipA/manual/STUDY_GUIDE.md`" in index
    # Manual-only session (no study guide): no topics, no study-guide line.
    assert "### clipB.mp4" in index
    assert "Duration: 00:01:01" in index
    assert "Key Topics: —" in index
    # Study-guide-only session without metadata.json: name falls back to the
    # frames folder name and the duration to "unknown".
    assert "### clipC" in index
    assert "Duration: unknown" in index


def test_build_master_index_caps_key_topics_at_six(tmp_path):
    guide = "# Study Guide — many\n\n## Key Topics\n\n" + "\n".join(
        f"### Topic {i}" for i in range(1, 10)
    )
    manual_dir = tmp_path / "PG" / "many_Frames" / "many" / "manual"
    _write(manual_dir / "STUDY_GUIDE.md", guide)
    _write(manual_dir / "MANUAL.md", "# manual")

    build_master_index(tmp_path)

    index = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    topics_line = next(line for line in index.splitlines() if line.startswith("- Key Topics:"))
    listed = [t.strip() for t in topics_line.split(":", 1)[1].split(";")]
    assert len(listed) == 6
    assert listed[0] == "Topic 1"


def test_build_master_index_empty_base_still_writes_index(tmp_path):
    result = build_master_index(tmp_path)

    assert result["sessions"] == 0
    index = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert "No sessions found yet" in index


def test_build_master_index_missing_base_creates_it(tmp_path):
    result = build_master_index(tmp_path / "does-not-exist")

    assert result["sessions"] == 0
    assert (tmp_path / "does-not-exist" / "INDEX.md").exists()
