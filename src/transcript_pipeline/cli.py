"""Entry points exposed as `[project.scripts]` in pyproject.toml.

The root scripts (`master_processor.py`, `simple_scan.py`, etc.) remain
the primary way to invoke the pipeline from `RUN_MAX_QUALITY.bat`. These
commands are the "installed" equivalent — same code, without depending
on the cwd being the repo root.
"""

from __future__ import annotations


def run() -> None:
    from transcript_pipeline.pipeline.master import main
    main()


def scan() -> None:
    from transcript_pipeline.transcription.processor import main
    main()


def compress() -> None:
    from transcript_pipeline.media.compressor import main
    main()


def dashboard() -> None:
    from transcript_pipeline.dashboard.app import main
    main()
