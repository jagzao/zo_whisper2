"""Local-first Live Capture domain (W3): durable session/chunk manifest store.

Provides the capture session/chunk model, validated state transitions, an
atomic manifest/media store under the Videos root, and the `CaptureService`
API that W4 (browser UI) and W5 (chunking/upload) call.
"""

from transcript_pipeline.live_capture.errors import (
    ChunkNotFoundError,
    InvalidTransitionError,
    LiveCaptureError,
    ManifestCorruptError,
    SessionConflictError,
    SessionNotFoundError,
    ValidationError,
)
from transcript_pipeline.live_capture.models import (
    AudioAvailability,
    Chunk,
    ChunkState,
    CropRegion,
    Session,
    SessionStatus,
)
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.live_capture.store import ManifestStore

__all__ = [
    "AudioAvailability",
    "CaptureService",
    "Chunk",
    "ChunkNotFoundError",
    "ChunkState",
    "CropRegion",
    "InvalidTransitionError",
    "LiveCaptureError",
    "ManifestCorruptError",
    "ManifestStore",
    "Session",
    "SessionConflictError",
    "SessionNotFoundError",
    "SessionStatus",
    "ValidationError",
]
