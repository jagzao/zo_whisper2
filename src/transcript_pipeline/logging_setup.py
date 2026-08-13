"""Centralized logging configuration.

Before this module, `dashboard/app.py`, `pipeline/master.py`, and
`transcription/processor.py` each called `logging.basicConfig()`
independently with a near-identical format string and their own log file.
Since `logging.basicConfig()` is a no-op once the root logger already has
handlers, whichever module happened to be imported first silently "won" —
e.g. running `master_processor.py` (which imports
`transcription.processor`) meant `master.py`'s own `basicConfig()` call
never took effect, and everything landed in `simple_scan.log` instead of
`master_process.log`, regardless of which entry point was actually run.

`configure_logging()` is the single place this now happens: idempotent
(first caller in a process wins, matching `basicConfig()`'s own contract,
but now on purpose instead of by import-order accident), and it tags every
record with a per-process `run_id` so log lines from one pipeline run can
be told apart from another in a shared log file.
"""

from __future__ import annotations

import logging
import sys
import uuid

from transcript_pipeline.config import PROJECT_ROOT

_FORMAT = "%(asctime)s - %(levelname)s - [run=%(run_id)s file=%(file_id)s] - %(message)s"


class _ContextFilter(logging.Filter):
    """Injects `run_id` into every record and defaults `file_id` to '-'
    when the caller didn't pass one via `extra={"file_id": ...}`."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        if not hasattr(record, "file_id"):
            record.file_id = "-"
        return True


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


def configure_logging(log_filename: str, *, run_id: str | None = None) -> str:
    """Configures the root logger once per process. Returns the run_id in
    effect (either the one just set, or the one an earlier caller in this
    process already established — later callers' `log_filename` is ignored
    in that case, same as `logging.basicConfig()`'s own idempotency).
    """
    root = logging.getLogger()
    if root.handlers:
        existing = next(
            (f.run_id for h in root.handlers for f in h.filters if isinstance(f, _ContextFilter)),
            None,
        )
        return existing or "-"

    run_id = run_id or new_run_id()
    handlers: list[logging.Handler] = [
        logging.FileHandler(PROJECT_ROOT / log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    context_filter = _ContextFilter(run_id)
    for handler in handlers:
        handler.addFilter(context_filter)

    logging.basicConfig(level=logging.INFO, format=_FORMAT, handlers=handlers)
    return run_id
