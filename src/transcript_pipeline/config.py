"""Resolución del root del proyecto y configuración compartida.

Todo el pipeline asume que `audio/`, `Videos/`, `CarpetaTranscripciones/`,
`projects.json` y `scan_config.env` viven en la raíz del repo. En vez de
repetir `Path(__file__).parent` (frágil una vez que el código vive dentro
de `src/transcript_pipeline/...`) o depender del cwd desde el que se lanza
el script, se busca hacia arriba el marcador `pyproject.toml` una sola vez.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_MARKER = "pyproject.toml"


def _find_project_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / _MARKER).exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())

AUDIO_DIR = PROJECT_ROOT / "audio"
VIDEOS_DIR = PROJECT_ROOT / "Videos"
TRANSCRIPTIONS_DIR = PROJECT_ROOT / "CarpetaTranscripciones"
FRAMES_DIR = PROJECT_ROOT / "Frames"
PROJECTS_CONFIG_PATH = PROJECT_ROOT / "projects.json"
PROCESSED_FILES_DB = PROJECT_ROOT / "processed_files.json"
SCAN_CONFIG_ENV = PROJECT_ROOT / "scan_config.env"


def load_env() -> None:
    """Carga scan_config.env desde la raíz del proyecto, sin importar el cwd."""
    load_dotenv(SCAN_CONFIG_ENV)
