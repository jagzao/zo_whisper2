"""Declarative project routing: config, not hardcoded if/else.

`projects.json` defines, per project, the match rules (folder, filename
prefix, keyword) and where/how to route the result. This module is pure
(it doesn't touch the filesystem except to read the JSON), which makes it
easy to test without real audio or the Whisper model.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_projects(config_path: Path) -> list[dict]:
    """Loads the project list from projects.json. [] if it doesn't exist."""
    if not config_path.exists():
        logger.warning("[CONFIG] %s not found — static routing disabled", config_path.name)
        return []
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("projects", [])


def match_project(audio_path: Path, projects: list[dict]) -> dict | None:
    """Returns the first project whose match rules apply to audio_path."""
    name_lower = audio_path.name.lower()
    parent_str = str(audio_path.parent)

    for proj in projects:
        rules = proj.get("match", {})

        for folder in rules.get("folder_contains", []):
            if folder.lower() in parent_str.lower():
                return proj

        for prefix in rules.get("prefix", []):
            if name_lower.startswith(prefix.lower()):
                return proj

        for keyword in rules.get("filename_contains", []):
            if keyword.lower() in name_lower:
                return proj

    return None
