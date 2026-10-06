"""Declarative project routing: config, not hardcoded if/else.

`projects.json` defines, per project, the match rules (folder, filename
prefix, keyword) and where/how to route the result. This module is pure
(it doesn't touch the filesystem except to read the JSON and the explicit
`mkdir` in `resolve_project_output_path`, which creates a missing output
folder so relative paths can be used out of the box), which makes it easy
to test without real audio or the Whisper model.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from transcript_pipeline.security.exceptions import PathTraversalError

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


def _is_within(candidate: Path, base: Path) -> bool:
    """True when `candidate` is `base` itself or lives somewhere below it.

    Replicates SafePathResolver._is_within instead of importing it: the
    resolver is the dashboard's media-root boundary (MediaRoot enum,
    media_id handling) and output routing only needs the containment
    predicate. normcase folds case and separators on Windows (NTFS is
    case-insensitive), and the explicit `os.sep` suffix prevents the
    string-prefix bypass ("C:\\data_evil" must not match base "C:\\data").
    Callers must pass already-resolve()d paths so symlink escapes are
    caught (resolve() follows symlinks to their real target).
    """
    candidate_s = os.path.normcase(str(candidate))
    base_s = os.path.normcase(str(base))
    return candidate_s == base_s or candidate_s.startswith(base_s + os.sep)


def resolve_project_output_path(
    raw: str,
    data_root: Path,
    container_mode: bool,
    allowed_roots: Sequence[Path] = (),
) -> Path:
    """Resolves a projects.json `output_path` to a safe, existing folder.

    Why this exists (WP-02 / US-ZMI-DKR-001 AC 5-7): `output_path` used to
    be a Windows absolute path trusted as-is. Relative values are the
    portable default now (they resolve under the runtime DATA_ROOT, which
    works unchanged inside Docker), while legacy absolute host paths stay
    backward compatible. Container mode refuses any absolute path that is
    not the data root or an explicitly configured allowed export root — a
    container must not silently start writing to whatever absolute path a
    copied config happens to contain.

    Rules, in order:

    1. `raw` must be a non-empty str without NUL bytes ("\\x00"), else
       PathTraversalError — same hardening as SafePathResolver.resolve.
    2. Drive-relative input (drive set, root empty, e.g. "C:foo") always
       raises PathTraversalError: pathlib anchors it to the CWD *of that
       drive*, an ambiguous escape independent of any containment check.
    3. Absolute input:
       - host mode (container_mode=False): legacy behavior — returned
         resolve()d with no containment check and no mkdir. projects.json
         is trusted local configuration on the host, and pre-WP-02
         installs depend on absolute paths outside DATA_ROOT.
       - container mode: allowed only when the resolved candidate is
         within `data_root` or within any of `allowed_roots` (each also
         resolved strict=False); otherwise PathTraversalError.
    4. Relative input: candidate = (data_root / raw).resolve(strict=False).
       If it is not within `data_root`, PathTraversalError — this rejects
       "../" traversal *and* symlink escapes, because resolve() follows
       symlinks to their real target before the containment check. When
       within, the folder is created (parents=True, exist_ok=True) so
       handlers receive an existing output dir; an OSError from mkdir
       propagates as-is so the caller (MasterProcessor) can disable just
       the affected handler instead of crashing startup.
    """
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise PathTraversalError(f"Invalid output_path: {raw!r}")

    p = Path(raw)

    if p.drive and not p.root:
        raise PathTraversalError(f"Drive-relative output_path not allowed: {raw!r}")

    if p.is_absolute() or p.root:
        candidate = p.resolve(strict=False)
        if not container_mode:
            return candidate
        resolved_data_root = data_root.resolve(strict=False)
        if _is_within(candidate, resolved_data_root):
            return candidate
        for allowed in allowed_roots:
            if _is_within(candidate, allowed.resolve(strict=False)):
                return candidate
        raise PathTraversalError(
            f"Absolute output_path outside the data root and not in any "
            f"allowed export root: {raw!r}"
        )

    resolved_data_root = data_root.resolve(strict=False)
    candidate = (resolved_data_root / p).resolve(strict=False)
    if not _is_within(candidate, resolved_data_root):
        raise PathTraversalError(f"output_path escapes the data root: {raw!r}")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate
