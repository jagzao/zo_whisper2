import pytest

from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.llm.redaction import redact_secrets
from transcript_pipeline.settings import Settings


class _FakeProvider:
    def __init__(self, provider_type: LLMProviderType):
        self.provider_type = provider_type


def _settings(**overrides) -> Settings:
    base = dict(
        whisper_model="large-v3", word_timestamps=False, clean_transcription=False,
        keyframes_required=True, keyframe_method="smart_scene", video_compress_crf=25,
        tesseract_cmd=None, meeting_frame_interval=15, meeting_max_screen_analyses=30,
        meeting_keep_frames=False, llm_api_key=None, llm_model="gpt-4o-mini",
        llm_base_url="https://api.openai.com/v1", llm_provider_type="remote",
        allow_external_llm=False, frame_descriptions=False, frame_description_max=20,
        privacy_mode="local", allow_frame_upload=False, retention_days=0,
        dashboard_host="127.0.0.1", dashboard_port=5000, upload_max_mb=500,
        icecream_music=None, icecream_videos=None,
    )
    base.update(overrides)
    return Settings(**base)


# ── PrivacyGuard ──────────────────────────────────────────────────────────

def test_local_provider_never_blocked():
    guard = PrivacyGuard(_settings(allow_external_llm=False))
    provider = _FakeProvider(LLMProviderType.LOCAL)
    guard.check(provider, {"data_classification": "confidential"})  # must not raise


def test_remote_provider_blocked_when_external_llm_disabled():
    guard = PrivacyGuard(_settings(allow_external_llm=False))
    provider = _FakeProvider(LLMProviderType.REMOTE)
    with pytest.raises(ExternalLLMBlockedError):
        guard.check(provider, None)


def test_remote_provider_allowed_when_external_llm_enabled_and_not_confidential():
    guard = PrivacyGuard(_settings(allow_external_llm=True))
    provider = _FakeProvider(LLMProviderType.REMOTE)
    guard.check(provider, {"data_classification": "internal"})  # must not raise
    guard.check(provider, None)  # default classification is "internal"


def test_confidential_project_blocks_remote_even_if_allowed_globally():
    guard = PrivacyGuard(_settings(allow_external_llm=True))
    provider = _FakeProvider(LLMProviderType.REMOTE)
    with pytest.raises(ExternalLLMBlockedError):
        guard.check(provider, {"data_classification": "confidential"})


# ── redact_secrets ────────────────────────────────────────────────────────

def test_redacts_openai_style_key():
    text = "here is my key sk-abcdefghijklmnopqrstuvwxyz123456 use it"
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in redact_secrets(text)


def test_redacts_github_token():
    text = "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in redact_secrets(text)


def test_redacts_aws_access_key():
    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    assert "AKIAIOSFODNN7EXAMPLE" not in redact_secrets(text)


def test_redacts_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    assert jwt not in redact_secrets(f"auth header: {jwt}")


def test_redacts_bearer_token():
    text = "Authorization: Bearer abcdef0123456789ABCDEF"
    assert "abcdef0123456789ABCDEF" not in redact_secrets(text)


def test_redacts_connection_string():
    text = "connect to postgres://admin:sup3rSecret@db.internal:5432/prod"
    result = redact_secrets(text)
    assert "sup3rSecret" not in result


def test_redacts_assigned_password():
    text = 'password: "hunter2isreal"'
    assert "hunter2isreal" not in redact_secrets(text)


def test_leaves_normal_text_unchanged():
    text = "This meeting covered the Q3 roadmap and hiring plan."
    assert redact_secrets(text) == text


def test_empty_string_passthrough():
    assert redact_secrets("") == ""
