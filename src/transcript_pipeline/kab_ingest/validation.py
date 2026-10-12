"""Input validation for the K'ab ingest API.

Everything a client can influence (session IDs, indexes, tracks, chunk
metadata, extensions, titles, timestamps) is validated here before it ever
touches the filesystem. Server-side paths are always generated from these
validated pieces — a client never supplies a path.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final

from transcript_pipeline.kab_ingest.errors import KabIngestValidationError

SESSION_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
PROJECT_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

MAX_PROJECT_KEY_LENGTH: Final[int] = 64


def validate_project_key(value: object) -> str | None:
    """Optional explicit K'ab project identity (SPEC §13).

    None is valid (legacy senders omit it). A provided key must be a plain
    identifier — it references a projects.json entry by name and is never a
    path, prompt, or free text.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise KabIngestValidationError("projectKey must be a string", code="invalid_project_key")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_PROJECT_KEY_LENGTH or not PROJECT_KEY_RE.fullmatch(cleaned):
        raise KabIngestValidationError(
            "projectKey must match ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", code="invalid_project_key"
        )
    return cleaned

TRACKS: Final[tuple[str, ...]] = ("video", "audio")
VIDEO_EXTENSIONS: Final[frozenset[str]] = frozenset({".mp4", ".mkv", ".mov", ".webm"})
AUDIO_EXTENSIONS: Final[frozenset[str]] = frozenset({".wav", ".m4a", ".mp3", ".flac", ".ogg", ".opus"})

MAX_TITLE_LENGTH: Final[int] = 200
MAX_REASON_LENGTH: Final[int] = 200
MAX_SEGMENT_DURATION_SEC: Final[float] = 7 * 24 * 3600.0
MAX_INDEX: Final[int] = 10**9
SCHEMA_VERSION: Final[int] = 1

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def validate_session_id(value: str) -> str:
    if not value or not SESSION_ID_RE.fullmatch(value):
        raise KabIngestValidationError(
            "sessionId must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", code="invalid_session_id"
        )
    return value


def validate_index(value: int, *, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KabIngestValidationError(f"{what} must be a nonnegative integer", code="invalid_index")
    if value < 0 or value > MAX_INDEX:
        raise KabIngestValidationError(f"{what} out of range (0..{MAX_INDEX})", code="invalid_index")
    return value


def validate_track(value: str) -> str:
    if value not in TRACKS:
        raise KabIngestValidationError(f"track must be one of {list(TRACKS)}", code="invalid_track")
    return value


def validate_required_tracks(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise KabIngestValidationError(
            "requiredTracks must be a non-empty list drawn from ['video', 'audio']",
            code="invalid_required_tracks",
        )
    for item in value:
        if item not in TRACKS:
            raise KabIngestValidationError(
                f"requiredTracks contains invalid track {item!r}", code="invalid_required_tracks"
            )
    if len(set(value)) != len(value):
        raise KabIngestValidationError("requiredTracks contains duplicates", code="invalid_required_tracks")
    return [t for t in TRACKS if t in value]


def validate_extension(track: str, raw: str) -> str:
    ext = raw.strip().lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if "/" in ext or "\\" in ext or "\x00" in ext:
        raise KabIngestValidationError(f"invalid extension: {raw!r}", code="invalid_extension")
    allowed = VIDEO_EXTENSIONS if track == "video" else AUDIO_EXTENSIONS
    if ext not in allowed:
        raise KabIngestValidationError(
            f"extension {ext!r} not allowed for track {track!r} (allowed: {sorted(allowed)})",
            code="invalid_extension",
        )
    return ext


def validate_sha256(raw: str) -> str:
    value = (raw or "").strip().lower()
    if not SHA256_RE.fullmatch(value):
        raise KabIngestValidationError("sha256 must be a 64-character lowercase hex digest", code="invalid_sha256")
    return value


def sanitize_title(raw: object) -> str:
    if not isinstance(raw, str):
        raise KabIngestValidationError("title must be a string", code="invalid_title")
    cleaned = _CONTROL_CHARS_RE.sub(" ", raw)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        raise KabIngestValidationError("title must not be empty", code="invalid_title")
    if len(cleaned) > MAX_TITLE_LENGTH:
        raise KabIngestValidationError(f"title exceeds {MAX_TITLE_LENGTH} characters", code="invalid_title")
    return cleaned


def sanitize_reason(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise KabIngestValidationError("reason must be a string", code="invalid_reason")
    cleaned = _CONTROL_CHARS_RE.sub(" ", raw)
    cleaned = " ".join(cleaned.split()).strip()
    if len(cleaned) > MAX_REASON_LENGTH:
        raise KabIngestValidationError(f"reason exceeds {MAX_REASON_LENGTH} characters", code="invalid_reason")
    return cleaned or None


def parse_iso8601(raw: object, *, what: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise KabIngestValidationError(f"{what} must be an ISO-8601 timestamp", code="invalid_timestamp")
    candidate = raw.strip()
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise KabIngestValidationError(f"{what} is not a valid ISO-8601 timestamp: {raw!r}", code="invalid_timestamp") from exc
    return raw.strip()


def validate_positive_number(raw: object, *, what: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise KabIngestValidationError(f"{what} must be a positive number", code="invalid_number")
    value = float(raw)
    if not value > 0 or value != value or value in (float("inf"), float("-inf")):
        raise KabIngestValidationError(f"{what} must be a finite positive number", code="invalid_number")
    return value


def validate_nonnegative_int_field(raw: object, *, what: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0 or raw > MAX_INDEX:
        raise KabIngestValidationError(f"{what} must be a nonnegative integer", code="invalid_number")
    return raw
