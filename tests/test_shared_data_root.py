"""Desktop/LAN shared data-root parity (AC-08).

Proves every mutable runtime path derives from one configurable DATA_ROOT, so
the localhost backend and the LAN HTTPS origin cannot diverge into two data or
media roots when they run the same code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from transcript_pipeline import config


def test_all_derived_paths_live_under_data_root():
    root = config.DATA_ROOT
    for path in (
        config.AUDIO_DIR,
        config.VIDEOS_DIR,
        config.TRANSCRIPTIONS_DIR,
        config.FRAMES_DIR,
        config.VIDEO_COMPRESS_DIR,
        config.LOG_DIR,
        config.PROJECTS_CONFIG_PATH,
        config.PROCESSED_FILES_DB,
    ):
        assert Path(path) == root or root in Path(path).parents, f"{path} escapes DATA_ROOT"


def test_zmi_data_root_relocates_every_derived_path(tmp_path):
    """A subprocess proves the derivation with a fresh interpreter/env."""
    script = (
        "import json; from transcript_pipeline import config as c; "
        "print(json.dumps([str(p) for p in (c.DATA_ROOT, c.AUDIO_DIR, c.VIDEOS_DIR, "
        "c.TRANSCRIPTIONS_DIR, c.VIDEO_COMPRESS_DIR, c.LOG_DIR, c.PROJECTS_CONFIG_PATH, "
        "c.PROCESSED_FILES_DB)]))"
    )
    env = {**os.environ, "ZMI_DATA_ROOT": str(tmp_path)}
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    paths = [Path(value) for value in json.loads(completed.stdout)]
    data_root = paths[0]
    assert data_root == tmp_path.resolve()
    for path in paths[1:]:
        assert data_root in path.parents, f"{path} escapes relocatable DATA_ROOT"
