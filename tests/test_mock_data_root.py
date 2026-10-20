from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"


def _load(name: str, path: Path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_mock_data_generator_and_cleanup_honor_zmi_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZMI_DATA_ROOT", str(tmp_path))
    generator = _load("generate_mock_data", ASSETS / "generate_mock_data.py", monkeypatch)
    cleanup = _load("cleanup_mock_data", ASSETS / "cleanup_mock_data.py", monkeypatch)

    assert generator.DATA_ROOT == tmp_path.resolve()
    assert generator.AUDIO == tmp_path.resolve() / "audio"
    assert generator.VIDEOS == tmp_path.resolve() / "Videos"
    assert generator.TRANSCRIPTIONS == tmp_path.resolve() / "CarpetaTranscripciones"
    assert generator.PROCESSED_DB == tmp_path.resolve() / "processed_files.json"
    assert cleanup.DATA_ROOT == tmp_path.resolve()
    assert cleanup.PROCESSED_DB == generator.PROCESSED_DB
