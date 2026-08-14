import pytest

from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Settings.from_env() calls load_env(), which would otherwise pull in
    # the real scan_config.env from the repo root and leak real values
    # (including API keys) into these tests.
    monkeypatch.setattr("transcript_pipeline.settings.load_env", lambda: None)
    for key in list(__import__("os").environ):
        if key in {
            "WHISPER_MODEL", "WORD_TIMESTAMPS", "CLEAN_TRANSCRIPTION",
            "KEYFRAMES_REQUIRED", "KEYFRAME_METHOD", "FILE_TRACKER_HASH_MODE", "VIDEO_COMPRESS_CRF",
            "TESSERACT_CMD", "MEETING_FRAME_INTERVAL", "MEETING_MAX_SCREEN_ANALYSES",
            "MEETING_KEEP_FRAMES", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL",
            "LLM_PROVIDER_TYPE", "ALLOW_EXTERNAL_LLM", "FRAME_DESCRIPTIONS",
            "FRAME_DESCRIPTION_MAX", "PRIVACY_MODE", "ALLOW_FRAME_UPLOAD",
            "RETENTION_DAYS", "DASHBOARD_HOST", "DASHBOARD_PORT", "UPLOAD_MAX_MB",
            "ICECREAM_MUSIC", "ICECREAM_VIDEOS",
        }:
            monkeypatch.delenv(key, raising=False)


def test_defaults_are_privacy_conservative():
    s = Settings.from_env()
    assert s.dashboard_host == "127.0.0.1"
    assert s.allow_external_llm is False
    assert s.frame_descriptions is False
    assert s.allow_frame_upload is False
    assert s.privacy_mode == "local"
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


def test_invalid_privacy_mode_rejected(monkeypatch):
    monkeypatch.setenv("PRIVACY_MODE", "not-a-real-mode")
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
