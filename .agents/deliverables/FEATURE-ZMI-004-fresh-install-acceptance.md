# FEATURE-ZMI-004 — Fresh Install Acceptance

## Outcome

A new contributor/user can install and boot the documented product path without relying on the maintainer's pre-existing environment.

## Scope

- Document/test clean `pip install -e ".[studio]"` path.
- Detect FFmpeg/ffprobe clearly.
- Treat Tesseract as optional unless OCR acceptance explicitly requires it.
- Boot dashboard on loopback.
- Seed synthetic data and run browser smoke.
- Keep external LLM disabled by default.
