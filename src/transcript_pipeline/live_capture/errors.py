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


class ManifestCorruptError(LiveCaptureError):
    """A persisted manifest is malformed and cannot be trusted as playable."""
