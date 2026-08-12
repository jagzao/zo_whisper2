# watcher/ — experimental, not part of the production pipeline

**Nothing in `src/transcript_pipeline/` imports from this directory.** The
daily workflow (`RUN_MAX_QUALITY.bat` → `master_processor.py` →
`transcript_pipeline.pipeline.master.MasterProcessor`) never touches code
here.

## What this directory actually is

An earlier, more ambitious architecture: a Docker-based microservice stack
(PostgreSQL, Redis, a separate Flask review UI, a watchdog service,
diarization/alignment/evaluation/glossary/monitoring/notifier modules under
`core/`). It predates the current `src/transcript_pipeline/` package and was
never wired into the `.bat`-driven daily workflow.

Four modules that *were* shared between this tree and the production
pipeline — `core/utils.py`, `core/video/keyframe_extractor.py`,
`core/postprocessing/timestamp_formatter.py`,
`core/integration/llm_client.py` — have been moved into the installable
package (`src/transcript_pipeline/media/`, `.../postprocessing/`,
`.../llm/`) as part of the security/architecture hardening pass. See
`docs/adr/0002-safe-filesystem-boundary.md` and the git history around that
change. `transcript_pipeline.bootstrap` (the `sys.path` shim that used to
bridge to this directory) has been removed — it's no longer needed.

A handful of files elsewhere in this tree (`core/transcription/safe_transcriber.py`,
`core/transcription/faster_whisper_enhanced.py`, `services/watcher_and_processor.py`)
still import from the old `core.postprocessing.timestamp_formatter` /
`core.utils` paths, which no longer exist here after the move above — they
were already unused by the production pipeline before this pass and remain
so; their imports are now stale as well. Fixing them is only worthwhile if
this stack is revived as an active project.

## One thing that *is* still used

`watcher/venv/` is the Python virtual environment `RUN_MAX_QUALITY.bat` and
the dashboard prefer when resolving which interpreter to run (see
`_python_exe()` in `src/transcript_pipeline/dashboard/app.py` and
`CLAUDE.md`). That's purely because it happens to be a working, pre-existing
venv on the development machine — it has no other relationship to the code
in this directory.

## If you want to revive this stack

Treat it as a separate project: its own `requirements.txt` already exists
here, independent of the root `pyproject.toml`. It would need its own CI,
its own security review, and its own decision about whether Postgres/Redis/
Docker are actually justified for what it does (see "What this project
deliberately doesn't do" in the root `README.md` for why the main pipeline
stayed single-process).
