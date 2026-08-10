"""Project root resolution and shared configuration.

The whole pipeline assumes `audio/`, `Videos/`, `CarpetaTranscripciones/`,
`projects.json`, and `scan_config.env` live at the repo root. Instead of
repeating `Path(__file__).parent` (fragile once the code lives inside
`src/transcript_pipeline/...`) or depending on the cwd the script was
launched from, it searches upward for the `pyproject.toml` marker once.
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
    """Loads scan_config.env from the project root, regardless of cwd."""
    load_dotenv(SCAN_CONFIG_ENV)
