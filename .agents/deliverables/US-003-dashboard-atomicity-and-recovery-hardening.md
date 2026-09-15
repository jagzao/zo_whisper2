# US-003 — Dashboard atomicity and real restart/recovery hardening

## Status
`SPEC`

## Context
Verified against current code (2026-09-15), not assumed from any stale report:
- `src/transcript_pipeline/dashboard/app.py:850-909` (`api_transcription_save`, the combined Edit File endpoint) already writes the transcription first, then the project override; if the override write fails it sets `response["warning"]` but still returns `"ok": True` (line 899-908). Confirmed non-atomic.
- Project rename/delete override writes at `app.py:697, 893, 942` have the same shape: override persistence can fail after the primary change already landed, with no rollback.
- `tests/test_restart_recovery.py` has no `subprocess`/`Popen` usage — it simulates restart in-process via monkeypatch, not a real process lifecycle. Confirmed not a real restart test.

## Acceptance Criteria

1. [ ] AC-1 — Edit File (`/api/transcription` POST) is all-or-nothing: if either the transcription write or the project-override write fails, the other change is rolled back and the response is `"ok": False` with a real error, never `"ok": True` + warning. Verified by: failure-injection tests for both orders (transcription-write-fails-first, override-write-fails-second) in `tests/test_project_override.py` or a new `tests/test_edit_file_atomicity.py`.
2. [ ] AC-2 — Project rename/delete + override changes are transactional: snapshot projects+overrides, persist required changes, roll back the first change if the second fails, return 500 on incoherent state. Verified by: regression tests for rename-override-write-failure, delete-override-write-failure, and a rollback-result assertion.
3. [ ] AC-3 — Restart/recovery is validated with a real process lifecycle, not a simulation: start the dashboard/pipeline as an actual subprocess, terminate mid-processing, restart, and assert `running=false`, no stage falsely marked completed, media not marked processed unless the DB proves it, metadata JSON valid, no leftover atomic-write temp files, and a clean next run. Verified by: a new isolated integration test using `subprocess`/`Popen` (not monkeypatch simulation) in `tests/integration/`.
4. [ ] AC-4 — Full acceptance matrix executed and recorded with real results (not "(pendiente)") in `.agents/deliverables/DELIVERY-US-003-....md`: 3 fresh synthetic E2E runs, >=3 dashboard stop/start cycles, EN+ES, MP4+WEBM, docs generate/edit/remove/regenerate, controlled failure/recovery, concurrency, process hygiene (no orphan dashboard/master_processor/ffmpeg/ffprobe, ports clean), one real local pipeline run against `aligner_howTo.webm` in an isolated workspace, `ALLOW_EXTERNAL_LLM=false`, privacy-safe metrics only. Verified by: `pytest tests/ -q`, `python scripts/quality.py`, `python scripts/security.py`, `python scripts/smoke.py`, `python scripts/e2e.py`, plus the integration/soak scenarios, all green, with run output captured in the DELIVERY doc.

## Evidence (fill as each AC closes)
-

## Known limitations / deferred scope
-

## Next dependency
None — this closes out the release-candidate hardening for v1.1.0. No merge/tag/release action is part of this US; that stays a separate, explicit step.
