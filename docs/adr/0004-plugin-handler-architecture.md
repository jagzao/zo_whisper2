# 0004 — Declarative routing + typed handler contract

## Status
Accepted

## Context
Adding a new client/project used to mean a JSON entry in `projects.json`
plus, if custom post-processing was needed, a new `ProjectHandler`
implementation — that part was already good design (`MasterProcessor`
doesn't know about specific projects, only about the `ProjectHandler`
protocol). The gap was the contract itself: `process()` returned a bare
`bool`, and the caller (`pipeline/master.py`) discarded it — a handler
that raised an exception (caught internally, returning `False`) still
resulted in the file being marked `completed_routed` in `FileTracker`,
because `routed = True` was set unconditionally once a handler existed for
the matched project.

## Decision
- `ProjectHandler.process()` returns `HandlerResult`
  (`src/transcript_pipeline/handlers/base.py`), not `bool`: a
  `(status, detail, output_paths)` tuple with `status` one of `COMPLETED`,
  `FAILED` (permanent — don't retry automatically), `RETRYABLE_FAILED`
  (transient — leave unmarked so the next scan retries it).
- `pipeline/master.py` branches on `handler_result.status` explicitly:
  `COMPLETED` → `mark_as_processed(..., "completed_routed")`; `FAILED` →
  `mark_as_processed(..., "failed_routed")` (visible, not silently
  "completed"); `RETRYABLE_FAILED` → **no** `mark_as_processed` call at
  all, so `FileTracker.is_file_processed()` returns `False` next run and
  the file is retried.
- Handlers classify their own exceptions: `OSError` (disk/permission
  issues) maps to `retryable=True`; anything else (a bug, malformed data)
  maps to `retryable=False`, since retrying a logic bug on every batch run
  would loop forever without fixing anything.

Kept intentionally small: three states, not a larger state machine
(`discovered`/`processing`/`transcribed`/... from the original brief) —
the pipeline is a single-pass batch, not a long-running job queue, so the
extra states wouldn't correspond to anything observable.

## Consequences
- The anchor bug (`pipeline/master.py:133-145` pre-fix) is closed and has a
  dedicated regression suite (`tests/integration/test_handler_routing.py`)
  covering success, permanent failure, retryable failure, and handler
  exceptions.
- All three handlers changed in lockstep (single commit) rather than via a
  bool→HandlerResult compatibility shim — with exactly three
  implementations and one call site, a shim would have been pure overhead.
- Adding a fourth handler still means: one class implementing
  `ProjectHandler`, registered in `HANDLER_MAP`, one `projects.json` entry.
  Nothing about this ADR changes that story.
