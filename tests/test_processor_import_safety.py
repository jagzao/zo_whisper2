"""Regression: importing/using the transcription module without an optional
ML dependency installed must never terminate the interpreter.

Before this fix, `transcription/processor.py` called `sys.exit(1)` at
*module import time* if `faster-whisper` wasn't installed — importing this
module from an unrelated process (e.g. a test runner, or another script
that just wants `transcript_pipeline.language`) would kill it.
"""

import subprocess
import sys

import pytest

from transcript_pipeline.errors import TranscriptionDependencyUnavailable
from transcript_pipeline.transcription import processor as processor_module


def test_ensure_model_raises_domain_exception_when_whisper_missing(monkeypatch):
    monkeypatch.setattr(processor_module, "WHISPER_AVAILABLE", False)
    instance = processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)
    instance.model = None
    instance._model_name = "large-v3"
    with pytest.raises(TranscriptionDependencyUnavailable):
        instance._ensure_model()


def test_import_without_faster_whisper_does_not_exit_process():
    # Fresh interpreter: sys.modules['faster_whisper'] = None makes the
    # `from faster_whisper import WhisperModel` in processor.py raise
    # ImportError, simulating the package not being installed at all.
    script = (
        "import sys; sys.modules['faster_whisper'] = None\n"
        "import transcript_pipeline.transcription.processor as m\n"
        "assert m.WHISPER_AVAILABLE is False\n"
        "print('IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "IMPORT_OK" in result.stdout
