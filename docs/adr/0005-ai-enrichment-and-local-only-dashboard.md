# 0005 — Centralized AI enrichment policy + fail-closed localhost-only dashboard

## Status
Accepted

## Context
Two related gaps survived the first hardening pass (ADRs 0001-0004), both
found by re-auditing the codebase for real bugs rather than assuming the
first pass was exhaustive:

1. **Outbound AI policy was assembled per call site, not centrally.** Six
   call sites (three handlers, plus `transcription/processor.py`'s tutorial
   frame-description path) each called `PrivacyGuard.check()`,
   `redact_secrets()`, and the provider separately. One of them
   (`_create_readable_mapping` in `processor.py`) called the guard with a
   literal `project_config=None` — the real project (and its
   `data_classification`) was computed earlier in the same call chain but
   never threaded through, so a `confidential` project's frames could still
   reach a remote vision LLM whenever `ALLOW_EXTERNAL_LLM=true`. A second
   call site (`meeting_dev_handler.py::_analyze_frame_vision`) never
   checked `FRAME_DESCRIPTIONS` or `ALLOW_FRAME_UPLOAD` at all — the latter
   flag was declared in `Settings`, defaulted, and tested, but read nowhere
   in `src/`.
2. **The dashboard had zero request-origin validation.** No Host header
   check, no Origin check, no token — any process able to reach the bound
   port could call every endpoint, including upload/delete/run-pipeline. A
   non-loopback `DASHBOARD_HOST` was only a `logger.warning()`, never
   blocked, so a `.env` typo could silently expose the dashboard to a LAN.

Both gaps share a root cause: safety logic that exists, but isn't
structurally required at every point that needs it.

## Decision

**AIEnrichmentService** (`src/transcript_pipeline/llm/enrichment.py`) is
now the only code path allowed to call an LLM provider. It wraps
`PrivacyGuard`, `redact_secrets()`, and a frame/upload policy behind five
methods (`summarize`, `describe_frame_with_prompt`,
`describe_frames_for_tutorial`, `allow_document_llm`, plus the internal
`_check_frame_policy`). The frame policy enforces, most restrictive first:
`FRAME_DESCRIPTIONS=false` blocks any visual analysis regardless of
provider; `PrivacyGuard.check()` blocks a remote call when
`ALLOW_EXTERNAL_LLM` is off or the project is `confidential`;
`ALLOW_FRAME_UPLOAD=false` additionally blocks a remote call even when the
above two would otherwise allow it — text generation and image upload are
separate permissions for a remote provider. All six existing call sites
were migrated to go through this service instead of assembling the checks
themselves, and `transcribe_file()`'s `result` dict now includes the real
`project` so `_create_readable_mapping` receives the actual classification
instead of `None`.

**The dashboard is now explicitly localhost-only, fail-closed.**
`Settings._validate()` raises `ConfigurationError` for any
`DASHBOARD_HOST` that isn't a loopback address — no remote-mode flag, by
explicit decision (this tool stays single-machine). A `before_request`
hook rejects any request whose Host header doesn't resolve to a loopback
hostname. Mutating requests (`POST`/`PUT`/`PATCH`/`DELETE`) additionally
require: an `Origin` header (when present) that's also loopback, and a
per-process token (`secrets.token_urlsafe(32)`, generated once at startup,
never persisted or logged) sent as `X-Local-Dashboard-Token` and compared
via `secrets.compare_digest()`. The frontend reads the token from the page
Jinja renders it into and attaches it to all four mutating fetch call
sites.

## Consequences
- Every outbound AI call in the codebase now goes through one policy
  assembly point — a new call site added later can't accidentally skip a
  check just by calling the provider directly, the way the two gaps above
  did.
- `meeting_dev_handler.py::_scan_documents`'s MarkItDown vision-client gate
  now uses `AIEnrichmentService.allow_document_llm()` instead of a bare
  `try/except` around `PrivacyGuard.check()`. **Update**: `allow_document_llm()`
  was subsequently changed to call `_check_frame_policy()` (the same gate
  as the video-frame path) instead of `PrivacyGuard.check()` alone — a
  document's embedded images are the same outbound-image risk as a video
  frame, so `FRAME_DESCRIPTIONS`/`ALLOW_IMAGE_UPLOAD` now apply to it too,
  closing a gap where a local provider (or a remote one with image upload
  disabled) could still describe document images. MarkItDown's own internal
  HTTP calls for document content still aren't passed through
  `redact_secrets()` (that library owns the HTTP call, not
  `OpenAICompatibleProvider`) — an unchanged, documented limitation, not
  something this ADR claims to fix.
- The dashboard's 4 endpoints that returned raw `str(exception)` to the
  client (`api_transcription` GET/POST, `api_delete_file`, `api_upload`)
  were sanitized in the same pass — `logger.exception()` server-side, a
  generic message to the client — since fixing the request-origin boundary
  without also fixing what an attacker-adjacent error response could leak
  would have been an incomplete fix.
- No new dependency, no new framework: the dashboard hardening is plain
  Flask `before_request` plus stdlib `secrets`/`urllib.parse`; no
  Flask-Login, no CSRF library, no session store. Consistent with this
  project's local-first, single-user philosophy (see ADR 0001).
- Verified against the real running dashboard (not just the test client):
  browser-driven project create/delete succeeds with the token wired
  through the UI; a `curl` request without a token, or with a forged Host
  header, gets `403`.
