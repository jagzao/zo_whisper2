# 0003 — External LLM calls require explicit, layered opt-in

## Status
Accepted

## Context
`generate_summary` (meeting/interview summaries) had no feature flag at
all — any handler with an API key configured would call the remote
endpoint. `describe_frame`/`describe_frames_for_tutorial` already had a
`FRAME_DESCRIPTIONS` flag, but nothing distinguished a `local` provider
(Ollama on localhost — no privacy concern) from a `remote` one (OpenAI,
DeepSeek — real privacy concern), and nothing let a specific project
override the global setting.

## Decision
Layer the opt-in at three levels, all enforced in `PrivacyGuard.check()`
(`src/transcript_pipeline/llm/guard.py`), called before every outbound
request in every handler:

1. **Provider type.** `LLMProviderType.LOCAL` providers are never blocked —
   there's no meaningful privacy boundary for a request that stays on
   `localhost`. `REMOTE` providers are what the rest of this ADR gates.
2. **Global flag.** `ALLOW_EXTERNAL_LLM` (default `false`) gates all remote
   calls, project-agnostic.
3. **Per-project classification.** `data_classification: confidential` on a
   project blocks remote calls for that project specifically, overriding
   the global flag — a way to keep one client's data local while allowing
   LLM enrichment for less sensitive work.

`generate_summary` now goes through the same guard as frame descriptions —
there's exactly one enforcement point (`PrivacyGuard`), not two flags with
different coverage.

## Consequences
- Three handlers (`client_meeting_handler.py`, `zo_handler.py`,
  `meeting_dev_handler.py`) all call `_privacy_guard.check(_llm_provider,
  project_config)` before their respective LLM calls, and catch
  `ExternalLLMBlockedError` to fall back to an empty template — enrichment
  degrades gracefully instead of failing the whole handler.
- `meeting_dev_handler.py`'s vision-frame analysis and MarkItDown
  document-scanning (which can also invoke a vision LLM for images) go
  through the same guard, closing two previously-unguarded outbound paths.
- Blocked calls are logged at `info` level with the reason, not silently
  swallowed — visible in `dashboard.log`/`simple_scan.log` without exposing
  the content that was blocked.
