"""Contract that per-project handlers must satisfy.

`MasterProcessor` doesn't know about any specific project: it only knows
that, given a `ProjectHandler`, it can call `.process(...)`. Which handler
to use for which file is decided by `projects.json` (see
`transcript_pipeline.projects.match_project`). Adding a new project means
adding a JSON entry + optionally a new handler, not touching the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ProjectHandler(Protocol):
    def __init__(self, base_path: str) -> None: ...

    def process(
        self,
        transcription_data: dict[str, Any],
        original_file_path: Path,
        project_config: dict[str, Any] | None = None,
    ) -> bool: ...
