# S46 final validation ? 2026-10-27

- Focused docs suite: 220 passed, 3 failed, 428.95s.
- Failed: `test_process_file_wires_capture_chunk_into_existing_docs_flow` (compatibility ai-package directory absent under incomplete source gate); `test_regenerate_capture_documentation_uses_late_transcript_once_and_is_idempotent` (fixture saved timestamped sidecar takes precedence over loose session transcript); `test_full_video_to_documentation_pipeline` (manual file withheld by mandatory source/visual gate).
- Golden overfit tests passed within the focused suite; production documentation modules contain no S46-specific literals.
- Ruff: `src/transcript_pipeline/documentation` PASS. Ruff across focused tests reports 8 existing test-file findings; no lint auto-fixes applied.
- Syntax: `compileall -q src/transcript_pipeline/documentation tests` PASS.
- `git diff --check` PASS.
- Source, visual, claim gates: PASS (visual 7/7); speech gate: NEEDS_REVIEW (5.730s low-confidence); Golden 2: not generated.
- Session 10 targeted pass: 3/3 VAD windows compared with neighbors; 588.361s tail ASR run and VAD-audited (one 0.992s speech region without supported ASR); no canonical sidecar changed; source remains queued with 547.508s aggregate uncovered speech.
- Documents corpus remains frozen. No merge or deployment.
