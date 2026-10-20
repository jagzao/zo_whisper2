"""Project root resolution and shared configuration.

Two roots are distinguished here:

- `PROJECT_ROOT` — the immutable code root (the repo, found by searching
  upward for the `pyproject.toml` marker). Code and templates always
  resolve against this one.
- `DATA_ROOT` — the runtime data root every mutable path derives from
  (media folders, state files, logs). Defaults to `PROJECT_ROOT`, so
  default host behavior is unchanged; a container layout moves it to a
  mounted volume via `ZMI_DATA_ROOT`.

`scan_config.env` stays a code-root concern by default (`PROJECT_ROOT /
"scan_config.env"`, overriding via `ZMI_CONFIG_ENV`) because it configures
the code, not the data — containers that need it elsewhere pass an
absolute path through `ZMI_CONFIG_ENV`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_MARKER = "pyproject.toml"


def _find_project_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / _MARKER).exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())

# Runtime data root: everything below derives from it. The `or` pattern
# makes an unset/blank ZMI_DATA_ROOT fall back to the code root.
DATA_ROOT = Path(os.getenv("ZMI_DATA_ROOT", "") or PROJECT_ROOT).resolve()

AUDIO_DIR = DATA_ROOT / "audio"
VIDEOS_DIR = DATA_ROOT / "Videos"
TRANSCRIPTIONS_DIR = DATA_ROOT / "CarpetaTranscripciones"
FRAMES_DIR = DATA_ROOT / "Frames"
VIDEO_COMPRESS_DIR = DATA_ROOT / "Video_compress"
LOG_DIR = DATA_ROOT / "logs"
PROJECTS_CONFIG_PATH = DATA_ROOT / "projects.json"
PROCESSED_FILES_DB = DATA_ROOT / "processed_files.json"
# NOT resolved against DATA_ROOT: the default lives in the code root.
# A relative ZMI_CONFIG_ENV value is kept as-is (containers use absolute).
SCAN_CONFIG_ENV = Path(os.getenv("ZMI_CONFIG_ENV", "") or (PROJECT_ROOT / "scan_config.env"))


def load_env() -> None:
    """Loads scan_config.env (path overridable via ZMI_CONFIG_ENV), regardless of cwd."""
    if not SCAN_CONFIG_ENV.exists():
        return
    load_dotenv(SCAN_CONFIG_ENV)
