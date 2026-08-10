"""Contrato que deben cumplir los handlers por proyecto.

`MasterProcessor` no conoce Valeris, Zo ni ningún proyecto específico:
solo sabe que, dado un `ProjectHandler`, puede llamar `.process(...)`.
Qué handler usar para qué archivo lo decide `projects.json` (ver
`transcript_pipeline.projects.match_project`). Agregar un proyecto nuevo
es agregar una entrada en el JSON + opcionalmente un handler nuevo, no
tocar el pipeline.
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
