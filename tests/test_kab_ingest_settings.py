"""T01-T03: K'ab ingest is disabled by default with the frozen safe posture."""

from __future__ import annotations

import os

import pytest

from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.kab_ingest.server import run_server
from transcript_pipeline.kab_ingest.settings import KabIngestSettings
from tests.kab_ingest_utils import make_settings

KAB_ENV_VARS = [k for k in os.environ if k.startswith("KAB_INGEST_")]


@pytest.fixture(autouse=True)
def _clean_kab_env(monkeypatch):
    for key in KAB_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


def test_t01_defaults_are_disabled_and_conservative():
    settings = KabIngestSettings.from_env()
    assert settings.enabled is False
    assert settings.host is None
    assert settings.port == 5443
    assert settings.token is None
    assert settings.cert_file is None
    assert settings.key_file is None
    assert settings.max_chunk_mb == 8
    assert settings.max_session_gb == 50


def test_t02_storage_root_defaults_to_data_root_kab_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ZMI_DATA_ROOT", str(tmp_path))
    import importlib

    import transcript_pipeline.config as config

    importlib.reload(config)
    try:
        settings = KabIngestSettings.from_env()
        assert settings.storage_root() == (tmp_path / "kab-inbox").resolve()
    finally:
        monkeypatch.delenv("ZMI_DATA_ROOT")
        importlib.reload(config)


def test_t03_disabled_receiver_refuses_to_start():
    settings = KabIngestSettings.from_env()
    with pytest.raises(ConfigurationError):
        settings.validate_for_server()
    with pytest.raises(ConfigurationError):
        run_server(settings)


def test_enabled_receiver_requires_every_credential(tmp_path):
    for kwargs in (
        {"enabled": False},
        {"host": None},
        {"token": None},
        {"cert_file": None},
        {"key_file": None},
    ):
        with pytest.raises(ConfigurationError):
            make_settings(tmp_path, **kwargs).validate_for_server()
