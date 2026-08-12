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
| Malicious LAN user | Only reachable if `DASHBOARD_HOST` is deliberately rebound off `127.0.0.1` |
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
- **No authentication on the dashboard.** Anything that can reach the bound
  address is treated as the local user. Mitigated by defaulting to
  `127.0.0.1` (`DASHBOARD_HOST`); **not mitigated** if you rebind to
  `0.0.0.0`/a LAN IP without adding your own auth layer. See `SECURITY.md`.

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
  `/api/files`). Low severity on a local-only tool, but still disclosure of
  local machine layout. **Not yet mitigated** — tracked as a known
  remaining item (see "Remaining risks" below); the intended fix is
  migrating the frontend from absolute paths to opaque `media_id`s (see
  `docs/adr/0002-safe-filesystem-boundary.md`).
- **Transcript/frame content sent to a remote LLM.** Mitigated by
  `PrivacyGuard` (off by default, `data_classification: confidential`
  override) and best-effort `redact_secrets()`. See `PRIVACY.md` for the
  documented limits of redaction.
- **Error messages leaking resolved paths.** Mitigated by the
  `SecurityError` errorhandler in `dashboard/app.py`, which returns a
  generic message instead of the exception string.

### Denial of Service
- **Unbounded upload size.** Mitigated by `MAX_CONTENT_LENGTH`
  (`UPLOAD_MAX_MB`, default 500MB).
- **Hung subprocesses** (ffmpeg without a timeout in a few call sites).
  **Not yet mitigated** everywhere — noted as a remaining risk; the batch
  subprocess calls (`master_processor.py`, `compress_and_move.py`) are
  intentionally long-running and shouldn't get an aggressive timeout, but
  per-file ffmpeg/ffprobe calls could reasonably get one.
- Single-process, single-user tool — not designed to survive intentional
  resource-exhaustion attacks from an untrusted network. Don't expose it to one.

### Elevation of Privilege
- The Flask process runs with whatever OS permissions the user has. There's
  no privilege separation between "dashboard user" and "pipeline batch" —
  by design, for a local single-user tool. If you rebind the dashboard
  beyond localhost, anyone who reaches it effectively gets local-user-level
  filesystem access within the allowed roots (and, before this hardening
  pass, arbitrary read/write anywhere the process could reach).

## Remaining risks (not hidden, tracked explicitly)

- Absolute paths still exposed to the frontend (see Information Disclosure
  above) — functional, not a live vulnerability post-`SafePathResolver`, but
  more disclosure than necessary.
- `subprocess` calls to ffmpeg/ffprobe in `media/compressor.py` and
  `handlers/meeting_dev_handler.py` lack a timeout in a few spots — a
  malformed/adversarial media file could hang a worker.
- No CSRF protection on mutating dashboard endpoints — acceptable for a
  same-origin, localhost-only, no-auth tool, but would need addressing if
  the trust model ever changes (see "Optional remote mode" in `SECURITY.md`
  and `docs/adr/`).
- `redact_secrets()` is regex-based and will miss secrets in unrecognized
  formats — documented, not silently claimed as complete, in `PRIVACY.md`.
