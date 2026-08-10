"""Entry points expuestos como `[project.scripts]` en pyproject.toml.

Los scripts raíz (`master_processor.py`, `simple_scan.py`, etc.) siguen
siendo la forma principal de invocar el pipeline desde `RUN_MAX_QUALITY.bat`.
Estos comandos son el equivalente "instalado" — mismo código, sin depender
de que el cwd sea la raíz del repo.
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
