"""Contract that per-project handlers must satisfy.

`MasterProcessor` doesn't know about any specific project: it only knows
that, given a `ProjectHandler`, it can call `.process(...)`. Which handler
to use for which file is decided by `projects.json` (see
`transcript_pipeline.projects.match_project`). Adding a new project means
adding a JSON entry + optionally a new handler, not touching the pipeline.

`process()` returns a `HandlerResult`, not a bare `bool`: a handler that
raises or returns `False` used to still let the caller mark the file
`completed_routed` because the return value was silently discarded (see
`pipeline.master.MasterProcessor.run_transcription_and_routing`). The
distinction between `FAILED` and `RETRYABLE_FAILED` lets the caller decide
whether to leave the file unmarked so the next `RUN_MAX_QUALITY.bat` picks
it up again, instead of retrying forever or losing the failure silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class HandlerStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"  # permanent error (bug, bad data) — do not retry automatically
    RETRYABLE_FAILED = "retryable"  # transient error (IO, network) — retry next run


@dataclass(frozen=True)
class HandlerResult:
    status: HandlerStatus
    detail: str = ""
    output_paths: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status is HandlerStatus.COMPLETED

    @classmethod
    def completed(cls, *output_paths: Path, detail: str = "") -> HandlerResult:
        return cls(HandlerStatus.COMPLETED, detail, output_paths)

    @classmethod
    def failed(cls, detail: str, *, retryable: bool = False) -> HandlerResult:
        status = HandlerStatus.RETRYABLE_FAILED if retryable else HandlerStatus.FAILED
        return cls(status, detail)


class ProjectHandler(Protocol):
    def __init__(self, base_path: str) -> None: ...

    def process(
        self,
        transcription_data: dict[str, Any],
        original_file_path: Path,
        project_config: dict[str, Any] | None = None,
    ) -> HandlerResult: ...
