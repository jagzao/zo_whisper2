"""Domain exceptions for Live Capture.

Every error maps to a stable, machine-readable condition so the future
dashboard API (W4/W5) can translate it one-to-one without improvising.
"""

from __future__ import annotations


class LiveCaptureError(Exception):
    """Base class for all Live Capture domain errors."""


class ValidationError(LiveCaptureError):
    """Invalid identity, index, timestamp, extension, or crop input."""


class SessionNotFoundError(LiveCaptureError):
    """The requested session manifest does not exist."""


class SessionConflictError(LiveCaptureError):
    """A session with the same identity already exists."""


class ChunkNotFoundError(LiveCaptureError):
    """The requested chunk index does not exist in the session."""


class InvalidTransitionError(LiveCaptureError):
    """The requested state transition is not allowed by the state machine."""


class ChunkTooLargeError(LiveCaptureError):
    """Streamed chunk media exceeded the configured upload size limit."""


class FragmentTooLargeError(LiveCaptureError):
    """Streamed fragment media exceeded the configured upload size limit."""


class FragmentConflictError(LiveCaptureError):
    """A fragment ID was replayed with different bytes or identity."""


class UploadCancelledError(LiveCaptureError):
    """A streamed upload was cancelled before atomic finalization."""


class AssemblyError(LiveCaptureError):
    """Ordered ACKed fragments could not be assembled into playable media.

    Already-durable source fragments are never destroyed by a failed
    assembly; the processing chunk is left retryable so assembly can rerun
    without any re-upload.
    """


class ManifestCorruptError(LiveCaptureError):
    """A persisted manifest is malformed and cannot be trusted as playable."""
