"""K'ab Local Ingest V1 — secure local segmented media ingest.

Receiver (`server`), worker (`worker`) and cert/token provisioning (`certs`)
run as separate processes from `transcript-kab-ingest`,
`transcript-kab-ingest-worker` and `transcript-kab-ingest-cert`.

Disabled by default (`KAB_INGEST_ENABLED=false`); TLS 1.2+ mandatory;
constant-time bearer auth on every endpoint; loopback/RFC1918/ULA binds only.
See docs/KAB_INGEST.md.
"""

from transcript_pipeline.kab_ingest.errors import (
    KabIngestConflict,
    KabIngestError,
    KabIngestNotFound,
    KabIngestPayloadTooLarge,
    KabIngestRequestTimeout,
    KabIngestUnauthorized,
    KabIngestValidationError,
)
from transcript_pipeline.kab_ingest.settings import KabIngestSettings

__all__ = [
    "KabIngestConflict",
    "KabIngestError",
    "KabIngestNotFound",
    "KabIngestPayloadTooLarge",
    "KabIngestRequestTimeout",
    "KabIngestSettings",
    "KabIngestUnauthorized",
    "KabIngestValidationError",
]
