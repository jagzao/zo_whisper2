# Privacy

This project processes audio/video that can contain voices, names, meeting
content, and on-screen code or documents. This document explains what stays
on your machine, what can leave it, and how to control that.

> **Use only recordings and materials you are authorized to process.** Obtain
> consent where required by applicable law, contract, employer policy, or
> confidentiality agreement. This is not legal advice — check your own
> obligations before recording or processing other people's conversations
> or work.

## What always stays local

- **Transcription** — `faster-whisper` runs on your CPU. Audio never leaves
  the machine for transcription.
- **Media processing** — compression (ffmpeg), keyframe extraction, OCR
  (Tesseract), timestamp formatting, and file routing all run locally.
- **Storage** — transcripts, metadata, and frames are written to
  `CarpetaTranscripciones/` and the project's configured `output_path`, both
  on local/mapped disk you control.
- **Dashboard** — `DASHBOARD_HOST` must be a loopback address (enforced at
  startup, `ConfigurationError` otherwise — no remote mode). Mutating
  requests additionally require a matching Host/Origin and a per-process
  token; see [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for what that
  boundary does and doesn't protect against.

## What can leave the machine — and only on opt-in

The only outbound path is the **LLM enrichment layer** (meeting summaries,
frame/screenshot descriptions, document analysis via MarkItDown), and it is
blocked by default:

| Flag | Default | Effect |
|---|---|---|
| `ALLOW_EXTERNAL_LLM` | `false` | Must be `true` for any call to a remote (`provider_type=remote`) LLM to go through. A `local` provider (Ollama, LM Studio, llama.cpp on `localhost`/`127.0.0.1`) is never blocked by this flag. |
| `data_classification` (per-project, in `projects.json`) | `internal` | Setting a project to `confidential` blocks remote LLM calls for that project **even if `ALLOW_EXTERNAL_LLM=true` globally**. |
| `FRAME_DESCRIPTIONS` | `false` | Must be `true` for extracted video frames (screenshots) to be sent to a vision model at all. Still subject to `ALLOW_EXTERNAL_LLM`/`data_classification` above. |
| `ALLOW_FRAME_UPLOAD` | `false` | Must be `true` for frame/screenshot **image bytes** to reach a remote provider — separate from `ALLOW_EXTERNAL_LLM`, which gates text. A remote call with `ALLOW_EXTERNAL_LLM=true` but `ALLOW_FRAME_UPLOAD=false` can still generate text summaries; it just won't upload images. |

`provider_type` (`local`/`remote`) is derived from `LLM_BASE_URL` by parsing
its actual hostname (`urllib.parse.urlparse`, with an `ipaddress.is_loopback`
fallback) and comparing it against `localhost`/`127.0.0.1`/`::1` exactly —
not a substring check, so `https://localhost.example.com` correctly
classifies as `remote`, not `local`. `LLM_PROVIDER_TYPE` overrides this
explicitly when set. Provider type is **never** inferred from the model
name, so pointing a "local-sounding" model name at a remote API doesn't
bypass the guard.

`src/transcript_pipeline/llm/enrichment.py` (`AIEnrichmentService`) is the
single call point every handler uses — it wraps `PrivacyGuard.check()`,
`redact_secrets()`, and the `FRAME_DESCRIPTIONS`/`ALLOW_FRAME_UPLOAD` frame
policy behind one small API, so no caller has to remember which combination
of checks to run. `src/transcript_pipeline/llm/guard.py` (`PrivacyGuard`) is
the underlying enforcement primitive it wraps, and
`src/transcript_pipeline/llm/openai_compatible.py` is the HTTP client.

## Secret redaction (best-effort, not a guarantee)

Before any text is sent to a remote LLM, `src/transcript_pipeline/llm/redaction.py`
runs `redact_secrets()` over it, matching common credential shapes: OpenAI-style
keys, GitHub tokens, AWS access keys, JWTs, `Bearer` tokens, connection
strings (`user:pass@host`), and `password`/`api_key`/`token` assignments.

**Limitations, stated plainly:**
- This is regex pattern-matching, not a DLP system. Secrets in an
  unrecognized format will not be caught.
- It only redacts the **text** sent to the LLM — screenshots/frames are sent
  as images, and redaction does not (and cannot, with this implementation)
  black out sensitive content visible *inside* an image.
- The transcript/document saved to disk (`transcript.md`, `context.md`, etc.)
  is **not** redacted — redaction applies only to the outbound API call.
- Treat `ALLOW_EXTERNAL_LLM=false` and `data_classification: confidential`
  as your real privacy boundary; redaction is defense in depth on top of
  that, not a substitute for it.

## Retention

`RETENTION_DAYS` (default `0` = keep indefinitely) is read by `Settings`
but cleanup of local artifacts (temporary frames, transient uploads) is not
automatic — nothing in this codebase silently deletes your source
recordings. If you implement a retention job, scope it to generated
intermediates (frames, temp audio), never to the user's original media.

## Data classification

Add `"data_classification": "public" | "internal" | "confidential"` to any
project entry in `projects.json` (default `internal` if omitted). See
`projects.json.example` for a worked example. `confidential` is enforced by
`PrivacyGuard` at the point of every outbound call — summaries, frame
descriptions, and document scanning all route through
`AIEnrichmentService`, which threads the real matched project's
classification through, not just documented — see
`tests/test_llm_guard_and_redaction.py` and `tests/test_llm_enrichment.py`
for the regression coverage.

## Where things are stored

- `CarpetaTranscripciones/` — transcripts, metadata, segments, keyframes.
- `projects.json` — your project routing config (gitignored; copy from
  `projects.json.example`, which uses synthetic names).
- `processed_files.json` — idempotency tracker (file hashes + status), not
  file content.
- `scan_config.env` — your local configuration (gitignored; copy from
  `scan_config.env.example`).

None of these are committed to the repository (see `.gitignore`).

## Related docs

- [`SECURITY.md`](SECURITY.md) — vulnerability reporting, trust model.
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — assets, actors, STRIDE-style analysis.
- [`docs/DATA_FLOW.md`](docs/DATA_FLOW.md) — diagram of what can leave the machine and where.
