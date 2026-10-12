"""Domain exceptions for the K'ab ingest receiver.

Every error carries the HTTP status and stable machine code the API returns,
so the Flask layer maps them one-to-one and never improvises a status.
"""

from __future__ import annotations


class KabIngestError(Exception):
    """Base class: maps to a uniform JSON error response."""

    status = 500
    code = "internal_error"

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code

    @property
    def message(self) -> str:
        return str(self)


class KabIngestValidationError(KabIngestError):
    status = 400
    code = "invalid_request"


class KabIngestUnauthorized(KabIngestError):
    status = 401
    code = "unauthorized"


class KabIngestNotFound(KabIngestError):
    status = 404
    code = "not_found"


class KabIngestRequestTimeout(KabIngestError):
    status = 408
    code = "request_timeout"


class KabIngestConflict(KabIngestError):
    status = 409
    code = "conflict"


class KabIngestPayloadTooLarge(KabIngestError):
    status = 413
    code = "payload_too_large"


class KabIngestUnavailable(KabIngestError):
    status = 503
    code = "unavailable"
