"""Local-first Live Capture domain (W3): durable session/chunk manifest store.

Provides the capture session/chunk model, validated state transitions, an
atomic manifest/media store under the Videos root, and the `CaptureService`
API that W4 (browser UI) and W5 (chunking/upload) call.
"""

from transcript_pipeline.live_capture.errors import (
    ChunkNotFoundError,
    ChunkTooLargeError,
    InvalidTransitionError,
    LiveCaptureError,
    ManifestCorruptError,
    SessionConflictError,
    SessionNotFoundError,
    ValidationError,
)
from transcript_pipeline.live_capture.audio import (
    audio_availability_from_track_count,
    resolve_audio_availability,
    transcript_required,
)
from transcript_pipeline.live_capture.crop import apply_crop_to_frames, crop_frame, to_pixel_box
from transcript_pipeline.live_capture.models import (
    AudioAvailability,
    Chunk,
    ChunkState,
    CropRegion,
    Session,
    SessionStatus,
    TRANSCRIPT_ALIGNMENT_LOOSE,
    Transcript,
)
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.live_capture.store import ManifestStore

__all__ = [
    "AudioAvailability",
    "CaptureService",
    "Chunk",
    "ChunkNotFoundError",
    "ChunkState",
    "ChunkTooLargeError",
    "CropRegion",
    "InvalidTransitionError",
    "LiveCaptureError",
    "ManifestCorruptError",
    "ManifestStore",
    "Session",
    "SessionConflictError",
    "SessionNotFoundError",
    "SessionStatus",
    "TRANSCRIPT_ALIGNMENT_LOOSE",
    "Transcript",
    "ValidationError",
    "apply_crop_to_frames",
    "audio_availability_from_track_count",
    "crop_frame",
    "resolve_audio_availability",
    "to_pixel_box",
    "transcript_required",
]
