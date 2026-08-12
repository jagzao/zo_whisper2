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

VALID_HANDLERS = {"client_meeting", "zo", "meeting_dev"}
VALID_DATA_CLASSIFICATIONS = {"public", "internal", "confidential"}
_MATCH_LIST_FIELDS = ("folder_contains", "prefix", "filename_contains")


def validate_project(project: object) -> list[str]:
    """Returns a list of validation error messages ([] if valid).

    `projects.json` is trusted local configuration, but the dashboard lets a
    browser submit new/updated entries (`POST /api/projects`) — this is the
    boundary that rejects malformed or unexpected structures before they're
    written to disk and later trusted by the pipeline/handlers.
    """
    errors: list[str] = []
    if not isinstance(project, dict):
        return ["project must be a JSON object"]

    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("'name' is required and must be a non-empty string")

    match = project.get("match")
    if match is not None:
        if not isinstance(match, dict):
            errors.append("'match' must be an object")
        else:
            for field in _MATCH_LIST_FIELDS:
                value = match.get(field)
                if value is not None and not (
                    isinstance(value, list) and all(isinstance(v, str) for v in value)
                ):
                    errors.append(f"'match.{field}' must be a list of strings")

    handler = project.get("handler")
    if handler is not None and handler not in VALID_HANDLERS:
        errors.append(f"'handler' must be one of {sorted(VALID_HANDLERS)} or null")

    language = project.get("language")
    if language is not None and not isinstance(language, str):
        errors.append("'language' must be a string or null")

    output_path = project.get("output_path")
    if output_path is not None and not isinstance(output_path, str):
        errors.append("'output_path' must be a string or null")

    classification = project.get("data_classification", "internal")
    if classification not in VALID_DATA_CLASSIFICATIONS:
        errors.append(f"'data_classification' must be one of {sorted(VALID_DATA_CLASSIFICATIONS)}")

    for field in ("custom_fillers",):
        value = project.get(field)
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            errors.append(f"'{field}' must be a list of strings")

    corrections = project.get("corrections")
    if corrections is not None and not (
        isinstance(corrections, dict) and all(isinstance(v, str) for v in corrections.values())
    ):
        errors.append("'corrections' must be an object of string -> string")

    return errors


def load_projects(config_path: Path) -> list[dict]:
    """Loads the project list from projects.json. [] if it doesn't exist.

    Entries that fail `validate_project` are skipped (logged, not raised) —
    a single malformed entry shouldn't take down routing for every project.
    """
    if not config_path.exists():
        logger.warning("[CONFIG] %s not found — static routing disabled", config_path.name)
        return []
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    raw_projects = data.get("projects", [])

    valid_projects: list[dict] = []
    for project in raw_projects:
        errors = validate_project(project)
        if errors:
            logger.warning(
                "[CONFIG] Skipping invalid project entry %r: %s",
                project.get("name") if isinstance(project, dict) else project,
                "; ".join(errors),
            )
            continue
        valid_projects.append(project)
    return valid_projects


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
