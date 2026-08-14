# Threat Model

Pragmatic STRIDE pass over a local-first tool. The goal isn't exhaustive
enterprise threat modeling — it's naming the assets that matter, who could
realistically threaten them on a single-user local machine, and what's
actually mitigated today vs. still open.

## Assets

| Asset | Where it lives |
|---|---|
| Media (audio/video recordings) | `audio/`, `Videos/`, `Video_compress/` |
| Transcripts (may contain names, business content, secrets spoken aloud) | `CarpetaTranscripciones/`, project `output_path` |
| Source code / screen content visible in extracted frames | `CarpetaTranscripciones/*/_Frames/` |
| LLM API keys | `scan_config.env` (gitignored) |
| Project routing config (client names, prompts) | `projects.json` (gitignored) |
| Filesystem (arbitrary read/write via the dashboard, if unguarded) | Whatever the Flask process user can access |
| Outbound LLM requests (transcript/frame content) | Network, only when `ALLOW_EXTERNAL_LLM=true` |

## Actors

| Actor | Realistic capability |
|---|---|
| Local user (you) | Full access — this is the intended user |
| Malicious/compromised process on the same machine | Could reach `127.0.0.1:5000` if the dashboard is running |
| Malicious LAN user | Not reachable — `DASHBOARD_HOST` must be a loopback address; `Settings.from_env()` raises `ConfigurationError` for anything else, no remote-mode override exists |
| Malicious uploaded file (crafted media) | Reaches ffmpeg/ffprobe, faster-whisper, PIL, Tesseract, MarkItDown |
| Compromised/malicious external LLM provider | Sees whatever redacted text/frames are sent when `ALLOW_EXTERNAL_LLM=true` |
| Accidental repo contributor | Could commit real client data/secrets to a public fork |
| Malicious dependency (supply chain) | Same blast radius as the process itself — see `pip-audit`/Dependabot mitigations |

## Trust boundaries

```
Browser  ──HTTP (localhost only, no auth)──▶  Flask dashboard
Flask    ──filesystem──▶  audio/ Videos/ Video_compress/ CarpetaTranscripciones/
Pipeline ──subprocess──▶  ffmpeg / ffprobe
Pipeline ──in-process──▶  faster-whisper (CPU)
Handlers ──HTTPS, opt-in──▶  External LLM provider (OpenAI-compatible)
Git repo ──push──▶  Public GitHub
```

## Threats (STRIDE, pragmatic)

### Spoofing
- **No user authentication on the dashboard** (by design — single-user,
  local tool, not a multi-tenant auth system). What *is* mitigated: (1)
  `DASHBOARD_HOST` can only be a loopback address — a non-loopback value
  raises `ConfigurationError` at startup, no escape hatch; (2) a
  `before_request` hook rejects any request whose Host header isn't
  loopback; (3) mutating requests (POST/PUT/PATCH/DELETE) additionally
  require a matching Origin (when present) and a per-process
  `X-Local-Dashboard-Token` (`secrets.token_urlsafe(32)`, generated at
  startup, compared via `secrets.compare_digest()`) — so a page in another
  browser tab, or an unrelated local process, can't drive the dashboard's
  mutating endpoints just by knowing the port. This is a same-machine
  boundary, not a login system — anyone with a shell on this machine can
  read the token from the running process either way. See `SECURITY.md`.

### Tampering
- **Path traversal → arbitrary file read/write.** Was the P0 finding this
  hardening pass fixed: `/api/transcription` GET/POST had no filesystem
  guard at all, and four other endpoints used a bypassable
  `str.startswith()` check. Mitigated by `SafePathResolver`
  (`src/transcript_pipeline/security/path_resolver.py`), covered by
  `tests/security/test_path_resolver.py` and `test_dashboard_endpoints.py`.
- **`projects.json` accepting arbitrary structure from the browser.**
  Mitigated by `validate_project()` (`src/transcript_pipeline/projects.py`),
  enforced on `POST /api/projects`.
- **Concurrent writes corrupting `projects.json`/transcripts.** Mitigated by
  atomic writes (temp file + `os.replace`) in `dashboard/app.py`.
- **Race condition double-triggering the pipeline.** Mitigated by
  `threading.Lock` around `/api/run/<mode>`'s check-then-act.

### Repudiation
- Out of scope for a single-user local tool — no multi-user audit log is
  maintained. Pipeline runs are logged to `dashboard.log`,
  `master_process.log`, `simple_scan.log`.

### Information Disclosure
- **Absolute filesystem paths returned to the frontend** (`/api/folders`,
  `/api/files`). Mitigated — every endpoint returns opaque `media_id`s or
  repo-relative strings; `/api/folders` returns only `{name, count}`. No
  endpoint returns or accepts a raw absolute path.
- **Transcript/frame content sent to a remote LLM.** Mitigated by
  `PrivacyGuard` (off by default, `data_classification: confidential`
  override) and best-effort `redact_secrets()`, both enforced through the
  single `AIEnrichmentService` call point — including the frame-description
  path (`transcription/processor.py`), which previously called the guard
  with a hardcoded `project_config=None` instead of the real project's
  classification (fixed; see regression test in `tests/test_processor.py`).
  See `PRIVACY.md` for the documented limits of redaction.
- **Frame/screenshot images reaching a remote provider.** Mitigated by
  `ALLOW_FRAME_UPLOAD` (default `false`), enforced in
  `AIEnrichmentService._check_frame_policy` — previously this flag was
  declared in `Settings` but never actually read anywhere.
- **Error messages leaking resolved paths or exception internals.**
  Mitigated by the `SecurityError` errorhandler, plus the 4
  previously-leaking endpoints (`api_transcription` GET/POST,
  `api_delete_file`, `api_upload`) now log full detail server-side via
  `logger.exception()` and return a generic client-facing message instead
  of `str(exception)`.

### Denial of Service
- **Unbounded upload size.** Mitigated by `MAX_CONTENT_LENGTH`
  (`UPLOAD_MAX_MB`, default 500MB).
- **A renamed non-media file accepted by upload.** Mitigated — after
  saving, `/api/upload` runs `ffprobe` against the file and deletes it
  (400) if no audio/video stream is recognized, instead of trusting the
  claimed extension alone. Never trusts the client-sent MIME type.
- **Hung subprocesses.** Mitigated — every ffmpeg/ffprobe call site has a
  timeout (`media/compressor.py`, `media/keyframe_extractor.py`,
  `handlers/meeting_dev_handler.py`): per-file probe/extract calls get a
  bounded timeout (30-600s depending on the operation), while the two
  intentionally long-running batch calls (`master_processor.py`,
  `compress_and_move.py`, invoked from the dashboard's run button) are not
  given an aggressive timeout by design — they're meant to run for as long
  as the daily batch takes.
- Single-process, single-user tool — not designed to survive intentional
  resource-exhaustion attacks from an untrusted network. Don't expose it to one.

### Elevation of Privilege
- The Flask process runs with whatever OS permissions the user has. There's
  no privilege separation between "dashboard user" and "pipeline batch" —
  by design, for a local single-user tool. Remote binding isn't possible
  (see Spoofing above), so this no longer extends to "anyone on the LAN" —
  it's scoped to whoever has access to this machine, same as running any
  other local tool.

## Remaining risks (not hidden, tracked explicitly)

- No CSRF-token rotation or session concept — the per-process dashboard
  token is a single static value for the process lifetime. Sufficient for
  the same-machine trust boundary this tool operates under, not a
  multi-user auth system.
- `redact_secrets()` is regex-based and will miss secrets in unrecognized
  formats, and never applies to image bytes (frame/screenshot uploads) —
  documented, not silently claimed as complete, in `PRIVACY.md`.
- MarkItDown's internal HTTP calls (document/image-to-markdown conversion,
  `handlers/meeting_dev_handler.py::_scan_documents`) go through a raw
  `openai.OpenAI` client when vision enrichment is allowed — gated by the
  same `AIEnrichmentService.allow_document_llm()` check as everything else,
  but the document content itself isn't passed through `redact_secrets()`
  the way handler-generated summary text is, since MarkItDown owns that
  HTTP call internally.
