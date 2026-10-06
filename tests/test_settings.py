import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from transcript_pipeline.config import load_env
from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Settings.from_env() calls load_env(), which would otherwise pull in
    # the real scan_config.env from the repo root and leak real values
    # (including API keys) into these tests.
    monkeypatch.setattr("transcript_pipeline.settings.load_env", lambda: None)
    for key in list(os.environ):
        if key in {
            "WHISPER_MODEL", "WORD_TIMESTAMPS", "CLEAN_TRANSCRIPTION",
            "KEYFRAMES_REQUIRED", "KEYFRAME_METHOD", "FILE_TRACKER_HASH_MODE", "VIDEO_COMPRESS_CRF",
            "TESSERACT_CMD", "MEETING_FRAME_INTERVAL", "MEETING_MAX_SCREEN_ANALYSES",
            "MEETING_KEEP_FRAMES", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL",
            "LLM_PROVIDER_TYPE", "ALLOW_EXTERNAL_LLM", "FRAME_DESCRIPTIONS",
            "FRAME_DESCRIPTION_MAX", "ALLOW_IMAGE_UPLOAD", "ALLOW_FRAME_UPLOAD",
            "RETENTION_DAYS", "DASHBOARD_HOST", "DASHBOARD_PORT", "UPLOAD_MAX_MB",
            "ICECREAM_MUSIC", "ICECREAM_VIDEOS", "ZMI_DATA_ROOT", "ZMI_CONFIG_ENV",
            "ZMI_CONTAINER_MODE", "ZMI_ALLOWED_EXPORT_ROOTS",
        }:
            monkeypatch.delenv(key, raising=False)


def test_defaults_are_privacy_conservative():
    s = Settings.from_env()
    assert s.dashboard_host == "127.0.0.1"
    assert s.allow_external_llm is False
    assert s.frame_descriptions is False
    assert s.allow_image_upload is False
    assert s.retention_days == 0


def test_llm_provider_type_inferred_local_from_base_url(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    s = Settings.from_env()
    assert s.llm_provider_type == "local"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://localhost:11434/v1", "local"),
        ("http://127.0.0.1:1234/v1", "local"),
        ("http://[::1]:1234/v1", "local"),
        ("https://localhost.example.com/v1", "remote"),
        ("https://127.0.0.1.example.com/v1", "remote"),
        ("https://example.com/v1", "remote"),
    ],
)
def test_llm_provider_type_hostname_parsing_not_substring(monkeypatch, base_url, expected):
    monkeypatch.setenv("LLM_BASE_URL", base_url)
    assert Settings.from_env().llm_provider_type == expected


def test_llm_provider_type_inferred_remote_by_default():
    s = Settings.from_env()
    assert s.llm_provider_type == "remote"


def test_llm_provider_type_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LLM_PROVIDER_TYPE", "remote")
    s = Settings.from_env()
    assert s.llm_provider_type == "remote"


def test_invalid_crf_rejected(monkeypatch):
    monkeypatch.setenv("VIDEO_COMPRESS_CRF", "999")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_invalid_dashboard_port_rejected(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PORT", "80")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_file_tracker_hash_mode_defaults_to_fast():
    assert Settings.from_env().file_tracker_hash_mode == "fast"


def test_invalid_file_tracker_hash_mode_rejected(monkeypatch):
    monkeypatch.setenv("FILE_TRACKER_HASH_MODE", "ultra")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_file_tracker_hash_mode_full_accepted(monkeypatch):
    monkeypatch.setenv("FILE_TRACKER_HASH_MODE", "full")
    assert Settings.from_env().file_tracker_hash_mode == "full"


def test_missing_icecream_paths_are_none():
    s = Settings.from_env()
    assert s.icecream_music is None
    assert s.icecream_videos is None


def test_bool_parsing_accepts_common_falsy_strings(monkeypatch):
    monkeypatch.setenv("ALLOW_EXTERNAL_LLM", "0")
    assert Settings.from_env().allow_external_llm is False
    monkeypatch.setenv("ALLOW_EXTERNAL_LLM", "true")
    assert Settings.from_env().allow_external_llm is True


def test_allow_image_upload_reads_legacy_frame_upload_alias(monkeypatch):
    """ALLOW_FRAME_UPLOAD was renamed to ALLOW_IMAGE_UPLOAD (its scope grew
    beyond video frames to any outbound image bytes) — existing configs
    using the old name must keep working."""
    monkeypatch.setenv("ALLOW_FRAME_UPLOAD", "true")
    assert Settings.from_env().allow_image_upload is True


def test_allow_image_upload_new_name_takes_priority_over_legacy(monkeypatch):
    monkeypatch.setenv("ALLOW_FRAME_UPLOAD", "true")
    monkeypatch.setenv("ALLOW_IMAGE_UPLOAD", "false")
    assert Settings.from_env().allow_image_upload is False


# ── WP-01: runtime path constants (DATA_ROOT / ZMI_DATA_ROOT / ZMI_CONFIG_ENV) ──
# config.py reads these env vars at import time and is already imported by
# the pytest session, so each assertion runs the probe in a fresh subprocess.

_CONSTANTS_PROBE = (
    "from transcript_pipeline.config import (AUDIO_DIR, DATA_ROOT, FRAMES_DIR, LOG_DIR, "
    "PROCESSED_FILES_DB, PROJECTS_CONFIG_PATH, PROJECT_ROOT, SCAN_CONFIG_ENV, "
    "TRANSCRIPTIONS_DIR, VIDEO_COMPRESS_DIR, VIDEOS_DIR); "
    "import json, pathlib; "
    "print(json.dumps({k: str(v) for k, v in dict("
    "PROJECT_ROOT=PROJECT_ROOT, DATA_ROOT=DATA_ROOT, AUDIO_DIR=AUDIO_DIR, VIDEOS_DIR=VIDEOS_DIR, "
    "VIDEO_COMPRESS_DIR=VIDEO_COMPRESS_DIR, TRANSCRIPTIONS_DIR=TRANSCRIPTIONS_DIR, FRAMES_DIR=FRAMES_DIR, "
    "LOG_DIR=LOG_DIR, PROJECTS_CONFIG_PATH=PROJECTS_CONFIG_PATH, PROCESSED_FILES_DB=PROCESSED_FILES_DB, "
    "SCAN_CONFIG_ENV=SCAN_CONFIG_ENV).items()}))"
)


def _config_paths(env_extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("ZMI_DATA_ROOT", "ZMI_CONFIG_ENV")
    }
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    if env_extra:
        env.update(env_extra)
    out = subprocess.run(
        [sys.executable, "-c", _CONSTANTS_PROBE],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_default_host_paths_unchanged():
    paths = _config_paths()
    root = paths["PROJECT_ROOT"]
    assert paths["DATA_ROOT"] == root
    assert paths["AUDIO_DIR"] == str(Path(root) / "audio")
    assert paths["VIDEOS_DIR"] == str(Path(root) / "Videos")
    assert paths["TRANSCRIPTIONS_DIR"] == str(Path(root) / "CarpetaTranscripciones")
    assert paths["FRAMES_DIR"] == str(Path(root) / "Frames")
    assert paths["VIDEO_COMPRESS_DIR"] == str(Path(root) / "Video_compress")
    assert paths["LOG_DIR"] == str(Path(root) / "logs")
    assert paths["PROJECTS_CONFIG_PATH"] == str(Path(root) / "projects.json")
    assert paths["PROCESSED_FILES_DB"] == str(Path(root) / "processed_files.json")
    assert paths["SCAN_CONFIG_ENV"] == str(Path(root) / "scan_config.env")


def test_zmi_data_root_moves_all_runtime_paths(tmp_path):
    paths = _config_paths({"ZMI_DATA_ROOT": str(tmp_path)})
    runtime_keys = (
        "AUDIO_DIR", "VIDEOS_DIR", "VIDEO_COMPRESS_DIR", "TRANSCRIPTIONS_DIR",
        "FRAMES_DIR", "LOG_DIR", "PROJECTS_CONFIG_PATH", "PROCESSED_FILES_DB",
    )
    for key in runtime_keys:
        assert Path(paths[key]).is_relative_to(tmp_path.resolve()), f"{key} not under tmp root"

    # Code-root concerns are untouched by the data-root override.
    defaults = _config_paths()
    assert paths["PROJECT_ROOT"] == defaults["PROJECT_ROOT"]
    assert paths["SCAN_CONFIG_ENV"] == defaults["SCAN_CONFIG_ENV"]


def test_zmi_config_env_supported(tmp_path):
    custom = tmp_path / "custom.env"
    paths = _config_paths({"ZMI_CONFIG_ENV": str(custom)})
    assert Path(paths["SCAN_CONFIG_ENV"]) == custom


def test_load_env_tolerates_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("transcript_pipeline.config.SCAN_CONFIG_ENV", tmp_path / "nope.env")
    load_env()  # must not raise


# ── WP-02: container mode (ZMI_CONTAINER_MODE) + allowed export roots ──
# Container mode is the Docker trust flag: it must default OFF and, when
# ON, widen the bind policy by exactly one value (0.0.0.0) and nothing else.


def test_container_mode_defaults_to_false():
    assert Settings.from_env().container_mode is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE"])
def test_container_mode_parsed_true(monkeypatch, value):
    monkeypatch.setenv("ZMI_CONTAINER_MODE", value)
    assert Settings.from_env().container_mode is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "FALSE"])
def test_container_mode_falsy_strings_parsed_false(monkeypatch, value):
    monkeypatch.setenv("ZMI_CONTAINER_MODE", value)
    assert Settings.from_env().container_mode is False


def test_container_mode_allows_0000_bind(monkeypatch):
    monkeypatch.setenv("ZMI_CONTAINER_MODE", "true")
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    assert Settings.from_env().dashboard_host == "0.0.0.0"


def test_container_mode_still_rejects_lan_ip(monkeypatch):
    monkeypatch.setenv("ZMI_CONTAINER_MODE", "true")
    monkeypatch.setenv("DASHBOARD_HOST", "192.168.1.10")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_container_mode_still_accepts_loopback(monkeypatch):
    monkeypatch.setenv("ZMI_CONTAINER_MODE", "true")
    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    assert Settings.from_env().dashboard_host == "127.0.0.1"


def test_host_mode_still_rejects_0000(monkeypatch):
    # The container-mode widening must not leak into the default host mode.
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_allowed_export_roots_default_empty():
    assert Settings.from_env().allowed_export_roots == ()


def test_allowed_export_roots_single_absolute(monkeypatch, tmp_path):
    root = tmp_path / "exports"
    monkeypatch.setenv("ZMI_ALLOWED_EXPORT_ROOTS", str(root))
    assert Settings.from_env().allowed_export_roots == (root,)


def test_allowed_export_roots_multiple_pathsep_separated(monkeypatch, tmp_path):
    a, b = tmp_path / "exports", tmp_path / "mnt" / "client"
    monkeypatch.setenv("ZMI_ALLOWED_EXPORT_ROOTS", f"{a}{os.pathsep} {b}")
    assert Settings.from_env().allowed_export_roots == (a, b)


def test_allowed_export_roots_relative_rejected(monkeypatch):
    monkeypatch.setenv("ZMI_ALLOWED_EXPORT_ROOTS", "relative/exports")
    with pytest.raises(ConfigurationError):
        Settings.from_env()
