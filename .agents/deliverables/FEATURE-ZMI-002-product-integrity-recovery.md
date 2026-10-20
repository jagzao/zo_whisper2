# FEATURE-ZMI-002 — Product Integrity and Recovery

## Outcome

User-visible edits and Project lifecycle operations cannot report success with half-persisted state, and dashboard restart behavior is proven outside a pure in-memory unit test.

## Scope

- Atomic Edit File transaction across transcription, segment text and Project override.
- Atomic Project rename/delete plus override migration/cleanup.
- Safe override cleanup when deleting media.
- Regression/failure-injection tests.
- Isolated process-level dashboard stop/start recovery smoke.
