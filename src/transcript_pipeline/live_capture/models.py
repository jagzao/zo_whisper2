"""Capture session/chunk domain model and validated state transitions.

Pure value objects with explicit, validated states. A chunk is either
RECORDING (accumulating, never playable), FINALIZED (durable, playable
media), PROCESSING (handed to transcription), PROCESSED (transcript
available) or FAILED (retryable). A session is ACTIVE, FINALIZED or
FAILED. Every transition is validated against a fixed state machine, so
an invalid transition is rejected before any manifest is touched.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from transcript_pipeline.live_capture.errors import (
    ChunkNotFoundError,
    InvalidTransitionError,
    ValidationError,
)

SCHEMA_VERSION = 1
DEFAULT_CHUNK_DURATION_SEC = 600

# A late-supplied transcript is always stored as one opaque text block with
# only its arrival time. No per-second segment sync is ever invented, so the
# alignment marker is a fixed constant, not user- or model-derived data.
TRANSCRIPT_ALIGNMENT_LOOSE = "loose"

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def now_iso() -> str:
    """UTC timestamp with offset, consistent with the K'ab ingest."""
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    return "sess-" + uuid.uuid4().hex[:12]


def validate_session_id(value: str) -> str:
    if not isinstance(value, str) or not SESSION_ID_RE.fullmatch(value):
        raise ValidationError("sessionId must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    return value


def chunk_id(index: int) -> str:
    return f"chunk-{index:06d}"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class ChunkState(str, Enum):
    RECORDING = "RECORDING"
    UPLOAD_CANCELLED = "UPLOAD_CANCELLED"
    FINALIZED = "FINALIZED"
    PROCESSING = "PROCESSING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class AudioAvailability(str, Enum):
    UNKNOWN = "UNKNOWN"
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"


_SESSION_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.ACTIVE: frozenset({SessionStatus.FINALIZED, SessionStatus.FAILED}),
    SessionStatus.FINALIZED: frozenset(),
    SessionStatus.FAILED: frozenset(),
}

_CHUNK_TRANSITIONS: dict[ChunkState, frozenset[ChunkState]] = {
    ChunkState.RECORDING: frozenset({ChunkState.FINALIZED, ChunkState.FAILED, ChunkState.UPLOAD_CANCELLED}),
    ChunkState.UPLOAD_CANCELLED: frozenset({ChunkState.RECORDING}),
    ChunkState.FINALIZED: frozenset({ChunkState.PROCESSING, ChunkState.CANCELLED, ChunkState.FAILED}),
    ChunkState.PROCESSING: frozenset({ChunkState.CANCEL_REQUESTED, ChunkState.PROCESSED, ChunkState.FAILED}),
    ChunkState.CANCEL_REQUESTED: frozenset({ChunkState.CANCELLED}),
    ChunkState.CANCELLED: frozenset({ChunkState.FINALIZED}),
    ChunkState.PROCESSED: frozenset(),
    ChunkState.FAILED: frozenset({ChunkState.PROCESSING}),
}


def validate_session_transition(current: SessionStatus, target: SessionStatus) -> SessionStatus:
    if target not in _SESSION_TRANSITIONS[current]:
        raise InvalidTransitionError(f"session cannot transition {current.value} -> {target.value}")
    return target


def validate_chunk_transition(current: ChunkState, target: ChunkState) -> ChunkState:
    if target not in _CHUNK_TRANSITIONS[current]:
        raise InvalidTransitionError(f"chunk cannot transition {current.value} -> {target.value}")
    return target


@dataclass(frozen=True)
class CropRegion:
    """Normalized crop region (W6): x/y are the top-left corner, width/height
    are the extents, all expressed as fractions of the frame in [0,1].

    A validated instance is guaranteed to lie entirely inside the unit
    square, so downstream consumers can convert it to pixel coordinates
    without re-validating. `None` (no crop) and the full frame
    ``(0, 0, 1, 1)`` both mean "leave the frame untouched".
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "width", "height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"crop {name} must be a number")
        if not (0.0 <= self.x <= 1.0) or not (0.0 <= self.y <= 1.0):
            raise ValidationError("crop x and y must be within [0,1]")
        if not (0.0 < self.width <= 1.0) or not (0.0 < self.height <= 1.0):
            raise ValidationError("crop width and height must be within (0,1]")
        if self.x + self.width > 1.0 + 1e-9 or self.y + self.height > 1.0 + 1e-9:
            raise ValidationError("crop region must fit inside the normalized frame")

    @property
    def is_full_frame(self) -> bool:
        """True when the region covers the entire frame (a no-op crop)."""
        return self.x == 0.0 and self.y == 0.0 and self.width == 1.0 and self.height == 1.0

    def to_manifest(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_manifest(cls, data: object) -> CropRegion | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValidationError("crop metadata must be a mapping")
        try:
            return cls(
                x=float(data["x"]),
                y=float(data["y"]),
                width=float(data["width"]),
                height=float(data["height"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("crop metadata is malformed") from exc


@dataclass(frozen=True)
class Chunk:
    index: int
    state: ChunkState
    created_at: str
    recorded_at: str | None = None
    finalized_at: str | None = None
    audio_availability: AudioAvailability = AudioAvailability.UNKNOWN
    transcript_available: bool = False
    transcript_required: bool = False
    media_extension: str | None = None
    media_size_bytes: int | None = None
    media_sha256: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise ValidationError("chunk index must be a nonnegative integer")

    @property
    def chunk_id(self) -> str:
        return chunk_id(self.index)

    @property
    def playable(self) -> bool:
        """Model-level playability: finalized-or-later state with known media.

        The store additionally verifies the media file exists on disk before
        exposing a chunk as playable; this is the state-machine invariant.
        """
        return (
            self.state in (ChunkState.FINALIZED, ChunkState.PROCESSING, ChunkState.PROCESSED)
            and self.media_size_bytes is not None
            and self.media_size_bytes >= 0
        )

    def transition_to(self, target: ChunkState) -> Chunk:
        validate_chunk_transition(self.state, target)
        return replace(self, state=target)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "chunkId": self.chunk_id,
            "state": self.state.value,
            "createdAt": self.created_at,
            "recordedAt": self.recorded_at,
            "finalizedAt": self.finalized_at,
            "audioAvailability": self.audio_availability.value,
            "transcriptAvailable": self.transcript_available,
            "transcriptRequired": self.transcript_required,
            "mediaExtension": self.media_extension,
            "mediaSizeBytes": self.media_size_bytes,
            "mediaSha256": self.media_sha256,
        }

    @classmethod
    def from_manifest(cls, data: object) -> Chunk:
        if not isinstance(data, dict):
            raise ValidationError("chunk manifest must be a mapping")
        index = data.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValidationError("chunk index must be a nonnegative integer")
        try:
            return cls(
                index=index,
                state=ChunkState(str(data["state"])),
                created_at=_require_nonempty_str(data, "createdAt"),
                recorded_at=_optional_nonempty_str(data.get("recordedAt")),
                finalized_at=_optional_nonempty_str(data.get("finalizedAt")),
                audio_availability=AudioAvailability(str(data.get("audioAvailability") or "UNKNOWN")),
                transcript_available=bool(data.get("transcriptAvailable", False)),
                transcript_required=bool(data.get("transcriptRequired", False)),
                media_extension=_optional_nonempty_str(data.get("mediaExtension")),
                media_size_bytes=_optional_nonnegative_int(data.get("mediaSizeBytes")),
                media_sha256=_optional_nonempty_str(data.get("mediaSha256")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("chunk manifest is malformed") from exc


@dataclass(frozen=True)
class Transcript:
    """A late-supplied transcript associated with a whole session (W8).

    Deliberately not timestamped per segment: the text is one opaque block
    with only its arrival time (`supplied_at`) and optional language. The
    `alignment` marker is a fixed constant (`TRANSCRIPT_ALIGNMENT_LOOSE`) —
    it can never be fabricated into second-level sync because no start/end
    fields exist on this model.
    """

    text: str
    supplied_at: str
    language: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValidationError("transcript text must be a non-empty string")
        if not isinstance(self.supplied_at, str) or not self.supplied_at.strip():
            raise ValidationError("transcript suppliedAt must be a non-empty string")
        if self.language is not None and (not isinstance(self.language, str) or not self.language.strip()):
            raise ValidationError("transcript language must be a non-empty string or null")

    @property
    def alignment(self) -> str:
        return TRANSCRIPT_ALIGNMENT_LOOSE

    def to_manifest(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "suppliedAt": self.supplied_at,
            "language": self.language,
            "alignment": self.alignment,
        }

    @classmethod
    def from_manifest(cls, data: object) -> Transcript:
        if not isinstance(data, dict):
            raise ValidationError("transcript manifest must be a mapping")
        try:
            return cls(
                text=_require_nonempty_str(data, "text"),
                supplied_at=_require_nonempty_str(data, "suppliedAt"),
                language=_optional_nonempty_str(data.get("language")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("transcript manifest is malformed") from exc


@dataclass(frozen=True)
class Session:
    session_id: str
    title: str
    status: SessionStatus
    created_at: str
    chunk_duration_sec: int
    recorded_at: str | None = None
    ended_at: str | None = None
    audio_availability: AudioAvailability = AudioAvailability.UNKNOWN
    crop: CropRegion | None = None
    transcript: Transcript | None = None
    chunks: tuple[Chunk, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        validate_session_id(self.session_id)
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("session title must be a non-empty string")
        if (
            isinstance(self.chunk_duration_sec, bool)
            or not isinstance(self.chunk_duration_sec, int)
            or self.chunk_duration_sec <= 0
        ):
            raise ValidationError("chunkDurationSec must be a positive integer")

    @property
    def next_chunk_index(self) -> int:
        return self.chunks[-1].index + 1 if self.chunks else 0

    @property
    def transcript_required(self) -> bool:
        """Derived, durable read: any chunk still awaiting a transcript.

        Never persisted on the session manifest directly — it is recomputed
        from each chunk's own persisted `transcript_required` flag on every
        load, so it cannot drift from the chunks. Included in `to_manifest`
        only so the dashboard API/UI can surface TRANSCRIPT_REQUIRED without
        an extra derivation step.
        """
        return any(chunk.transcript_required for chunk in self.chunks)

    @property
    def transcript_available(self) -> bool:
        """Derived, durable read: a session-level transcript exists, or any
        chunk already carries one.

        Like `transcript_required`, this is never persisted directly — it is
        recomputed from `self.transcript` and each chunk's own
        `transcript_available` flag on every load. Included in `to_manifest`
        only so the dashboard API/UI can surface availability without an
        extra derivation step.
        """
        return self.transcript is not None or any(chunk.transcript_available for chunk in self.chunks)

    def transition_to(self, target: SessionStatus) -> Session:
        validate_session_transition(self.status, target)
        return replace(self, status=target)

    def with_chunk(self, chunk: Chunk) -> Session:
        """Replace the chunk at `chunk.index`, keeping indexes unique and ordered."""
        chunks = [c for c in self.chunks if c.index != chunk.index]
        chunks.append(chunk)
        chunks.sort(key=lambda c: c.index)
        return replace(self, chunks=tuple(chunks))

    def get_chunk(self, index: int) -> Chunk:
        for chunk in self.chunks:
            if chunk.index == index:
                return chunk
        raise ChunkNotFoundError(f"chunk {chunk_id(index)} not found in session {self.session_id}")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "sessionId": self.session_id,
            "title": self.title,
            "status": self.status.value,
            "createdAt": self.created_at,
            "recordedAt": self.recorded_at,
            "endedAt": self.ended_at,
            "chunkDurationSec": self.chunk_duration_sec,
            "audioAvailability": self.audio_availability.value,
            "transcriptRequired": self.transcript_required,
            "transcriptAvailable": self.transcript_available,
            "transcript": self.transcript.to_manifest() if self.transcript else None,
            "crop": self.crop.to_manifest() if self.crop else None,
            "chunks": [c.to_manifest() for c in self.chunks],
            "reason": self.reason,
        }

    @classmethod
    def from_manifest(cls, data: object) -> Session:
        if not isinstance(data, dict):
            raise ValidationError("session manifest must be a mapping")
        if data.get("schemaVersion") != SCHEMA_VERSION:
            raise ValidationError(f"unsupported schemaVersion {data.get('schemaVersion')!r}")
        chunks_raw = data.get("chunks", [])
        if not isinstance(chunks_raw, list):
            raise ValidationError("chunks must be a list")
        chunks = tuple(Chunk.from_manifest(c) for c in chunks_raw)
        transcript_raw = data.get("transcript")
        transcript = Transcript.from_manifest(transcript_raw) if transcript_raw is not None else None
        try:
            return cls(
                session_id=str(data["sessionId"]),
                title=str(data["title"]),
                status=SessionStatus(str(data["status"])),
                created_at=_require_nonempty_str(data, "createdAt"),
                chunk_duration_sec=int(data["chunkDurationSec"]),
                recorded_at=_optional_nonempty_str(data.get("recordedAt")),
                ended_at=_optional_nonempty_str(data.get("endedAt")),
                audio_availability=AudioAvailability(str(data.get("audioAvailability") or "UNKNOWN")),
                crop=CropRegion.from_manifest(data.get("crop")),
                transcript=transcript,
                chunks=chunks,
                reason=_optional_nonempty_str(data.get("reason")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("session manifest is malformed") from exc


def _require_nonempty_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string")
    return value


def _optional_nonempty_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("optional string field must be a non-empty string or null")
    return value


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError("optional integer field must be a nonnegative integer or null")
    return value
