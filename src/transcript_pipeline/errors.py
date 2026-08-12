"""Domain exceptions raised at first use of an optional dependency/feature.

A library module must never `sys.exit()` at import time (see
`transcription/processor.py`, which used to kill the whole interpreter if
`faster-whisper` wasn't installed) — importing an unrelated module in the
same process would take the process down with it. These are raised lazily,
when the feature is actually invoked.
"""

from __future__ import annotations


class TranscriptionDependencyUnavailable(RuntimeError):
    """`faster-whisper` (or another required transcription dependency) is not installed."""
