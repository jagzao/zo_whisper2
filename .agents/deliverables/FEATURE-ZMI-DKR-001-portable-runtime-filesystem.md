# FEATURE-ZMI-DKR-001 — Portable Runtime Filesystem

## Outcome

The installed application can run from immutable code while all mutable runtime data is located under an explicit data root.

## Required changes

- Add `DATA_ROOT` from `ZMI_DATA_ROOT`, default `PROJECT_ROOT`.
- Runtime directories use `DATA_ROOT`:
  - `audio/`
  - `Videos/`
  - `Video_compress/`
  - `CarpetaTranscripciones/`
  - `processed_files.json`
  - `project_overrides.json`
  - `projects.json`
  - `logs/`
- Add optional `ZMI_CONFIG_ENV` override for scan config.
- Update dashboard, master pipeline, file tracker, logging and synthetic-data helpers to consume shared config constants rather than reconstruct repo-root paths.
- Replace dashboard root-script subprocess calls with `sys.executable -m ...`.
- Use `sys.executable` as the subprocess interpreter.
- Make project example paths portable:
  - relative `output_path` resolves under `DATA_ROOT`;
  - existing absolute paths remain backward-compatible in host mode;
  - container mode rejects unsafe/unmounted absolute output paths rather than silently losing output.
- Existing non-Docker behavior is unchanged when `ZMI_DATA_ROOT` is unset.

## Primary risks

- path traversal/security regression;
- existing project routing output paths;
- processed-file idempotency after path relocation;
- tests monkeypatching old module constants.

All require regression coverage.
