# 0001 — Local-first, privacy-by-default

## Status
Accepted

## Context
The pipeline processes audio/video that can contain names, business
content, and on-screen code. Optional LLM enrichment (summaries, frame
descriptions) can meaningfully improve output quality, but sending that
content to a third-party API is a privacy decision, not a technical default.

## Decision
Every feature that can send data off the machine is **off by default** and
requires explicit opt-in:
- `ALLOW_EXTERNAL_LLM=false` by default — no remote LLM call happens
  without the operator turning it on.
- `FRAME_DESCRIPTIONS=false` by default — screenshots aren't sent to a
  vision model unless explicitly enabled.
- Per-project `data_classification: confidential` overrides the global
  flag and blocks remote calls for that project specifically, so a
  confidential client's data can't leave even if the global default was
  relaxed for other work.
- `provider_type` (`local`/`remote`) is derived from `LLM_BASE_URL`
  (localhost = local) rather than inferred from the model name, so a
  misleadingly-named local proxy can't silently bypass the guard.

Core transcription (faster-whisper), media processing (ffmpeg), and OCR
(Tesseract) never touch the network at all — there's no flag for them
because there's no outbound path to gate.

## Consequences
- A first-time user gets useful transcripts with zero data leaving their
  machine, and has to make an active choice to enable enrichment.
- Handlers that call the LLM must go through `PrivacyGuard.check()` before
  every remote call — enforced in `client_meeting_handler.py`,
  `zo_handler.py`, `meeting_dev_handler.py`, and
  `transcription/processor.py`'s tutorial frame descriptions.
- Slightly more ceremony per LLM call site (guard + redact), justified by
  the alternative: a handler that "forgets" the check and leaks content.
