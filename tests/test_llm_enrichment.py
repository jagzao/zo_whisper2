"""AIEnrichmentService: the single place frame/upload/redaction/privacy
policy is assembled. Covers the invariants, not the full combinatorial
matrix (provider x FRAME_DESCRIPTIONS x ALLOW_FRAME_UPLOAD x
ALLOW_EXTERNAL_LLM x classification) — each test isolates one gate.
"""

from unittest.mock import MagicMock

import pytest

from transcript_pipeline.llm.enrichment import AIEnrichmentService
from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.settings import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        whisper_model="large-v3", word_timestamps=False, clean_transcription=False,
        keyframes_required=True, keyframe_method="smart_scene", file_tracker_hash_mode="fast",
        video_compress_crf=25, tesseract_cmd=None, meeting_frame_interval=15,
        meeting_max_screen_analyses=30, meeting_keep_frames=False, llm_api_key="test-key",
        llm_model="gpt-4o-mini", llm_base_url="https://api.example.com/v1", llm_provider_type="remote",
        allow_external_llm=False, frame_descriptions=False, frame_description_max=20,
        allow_image_upload=False, retention_days=0, dashboard_host="127.0.0.1",
        dashboard_port=5000, upload_max_mb=500, icecream_music=None, icecream_videos=None,
    )
    base.update(overrides)
    return Settings(**base)


def _provider(provider_type: LLMProviderType) -> MagicMock:
    provider = MagicMock()
    provider.provider_type = provider_type
    provider.generate_summary.return_value = "summary"
    provider.describe_frame_with_prompt.return_value = "description"
    provider.describe_frames_for_tutorial.return_value = {"frame_0001.png": "description"}
    return provider


def _service(settings: Settings, provider_type: LLMProviderType) -> tuple[AIEnrichmentService, MagicMock]:
    provider = _provider(provider_type)
    guard = PrivacyGuard(settings)
    return AIEnrichmentService(provider, guard, settings), provider


# ── frame policy invariants ──────────────────────────────────────────────

def test_local_provider_blocked_when_frame_descriptions_off():
    service, provider = _service(_settings(frame_descriptions=False), LLMProviderType.LOCAL)
    with pytest.raises(ExternalLLMBlockedError):
        service.describe_frame_with_prompt("frame.png", "describe", None)
    provider.describe_frame_with_prompt.assert_not_called()


def test_local_provider_allowed_when_frame_descriptions_on_regardless_of_upload_and_external():
    settings = _settings(frame_descriptions=True, allow_image_upload=False, allow_external_llm=False)
    service, provider = _service(settings, LLMProviderType.LOCAL)
    result = service.describe_frame_with_prompt("frame.png", "describe", None)
    assert result == "description"
    provider.describe_frame_with_prompt.assert_called_once()


def test_remote_provider_blocked_when_external_llm_off():
    settings = _settings(frame_descriptions=True, allow_external_llm=False)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    with pytest.raises(ExternalLLMBlockedError):
        service.describe_frame_with_prompt("frame.png", "describe", None)
    provider.describe_frame_with_prompt.assert_not_called()


def test_remote_provider_blocked_when_frame_upload_off_even_if_external_allowed():
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=False)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    with pytest.raises(ExternalLLMBlockedError):
        service.describe_frame_with_prompt("frame.png", "describe", None)
    provider.describe_frame_with_prompt.assert_not_called()


def test_remote_provider_blocked_for_confidential_project_even_if_everything_else_allowed():
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=True)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    with pytest.raises(ExternalLLMBlockedError):
        service.describe_frame_with_prompt("frame.png", "describe", {"data_classification": "confidential"})
    provider.describe_frame_with_prompt.assert_not_called()


def test_remote_provider_allowed_when_all_flags_permissive_and_internal():
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=True)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    result = service.describe_frame_with_prompt("frame.png", "describe", {"data_classification": "internal"})
    assert result == "description"
    provider.describe_frame_with_prompt.assert_called_once()


def test_describe_frames_for_tutorial_uses_same_frame_policy():
    settings = _settings(frame_descriptions=False)
    service, provider = _service(settings, LLMProviderType.LOCAL)
    with pytest.raises(ExternalLLMBlockedError):
        service.describe_frames_for_tutorial("frames_dir", {}, None)
    provider.describe_frames_for_tutorial.assert_not_called()


# ── summarize() ───────────────────────────────────────────────────────────

def test_summarize_applies_redaction_before_sending_remote():
    settings = _settings(allow_external_llm=True)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    service.summarize("my key is sk-abcdefghijklmnopqrstuvwxyz123456", {"data_classification": "internal"})
    sent_text = provider.generate_summary.call_args.args[0]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in sent_text


def test_summarize_preserves_original_text_for_local():
    """Local providers never leave the machine — nothing to redact against."""
    settings = _settings()
    service, provider = _service(settings, LLMProviderType.LOCAL)
    original = "my key is sk-abcdefghijklmnopqrstuvwxyz123456"
    service.summarize(original, None)
    sent_text = provider.generate_summary.call_args.args[0]
    assert sent_text == original


def test_summarize_blocked_for_confidential_remote():
    settings = _settings(allow_external_llm=True)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    with pytest.raises(ExternalLLMBlockedError):
        service.summarize("text", {"data_classification": "confidential"})
    provider.generate_summary.assert_not_called()


# ── redaction on the frame/document paths ──────────────────────────────────

def test_describe_frame_with_prompt_redacts_for_remote():
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=True)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    secret_prompt = 'describe this, token=sk-abcdefghijklmnopqrstuvwxyz123456'
    service.describe_frame_with_prompt("frame.png", secret_prompt, {"data_classification": "internal"})
    sent_prompt = provider.describe_frame_with_prompt.call_args.args[1]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in sent_prompt


def test_describe_frame_with_prompt_preserves_original_for_local():
    settings = _settings(frame_descriptions=True)
    service, provider = _service(settings, LLMProviderType.LOCAL)
    original_prompt = "describe this, token=sk-abcdefghijklmnopqrstuvwxyz123456"
    service.describe_frame_with_prompt("frame.png", original_prompt, None)
    sent_prompt = provider.describe_frame_with_prompt.call_args.args[1]
    assert sent_prompt == original_prompt


def test_describe_frames_for_tutorial_redacts_mapping_for_remote_without_mutating_original():
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=True)
    service, provider = _service(settings, LLMProviderType.REMOTE)
    mapping = {"frame_0001.png": {"full_text": "token=sk-abcdefghijklmnopqrstuvwxyz123456"}}
    service.describe_frames_for_tutorial("frames_dir", mapping, {"data_classification": "internal"})

    sent_mapping = provider.describe_frames_for_tutorial.call_args.args[1]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in sent_mapping["frame_0001.png"]["full_text"]
    # Original caller's mapping must be untouched.
    assert mapping["frame_0001.png"]["full_text"] == "token=sk-abcdefghijklmnopqrstuvwxyz123456"


def test_describe_frames_for_tutorial_preserves_original_mapping_for_local():
    settings = _settings(frame_descriptions=True)
    service, provider = _service(settings, LLMProviderType.LOCAL)
    mapping = {"frame_0001.png": {"full_text": "token=sk-abcdefghijklmnopqrstuvwxyz123456"}}
    service.describe_frames_for_tutorial("frames_dir", mapping, None)

    sent_mapping = provider.describe_frames_for_tutorial.call_args.args[1]
    assert sent_mapping is mapping
    assert sent_mapping["frame_0001.png"]["full_text"] == "token=sk-abcdefghijklmnopqrstuvwxyz123456"


# ── allow_document_llm() — shares _check_frame_policy with the video-frame
# path (a document's embedded images are the same outbound-image risk) ────

def test_allow_document_llm_returns_false_without_raising_when_blocked():
    settings = _settings(frame_descriptions=True, allow_external_llm=False)
    service, _ = _service(settings, LLMProviderType.REMOTE)
    assert service.allow_document_llm(None) is False


def test_allow_document_llm_returns_true_when_allowed():
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=True)
    service, _ = _service(settings, LLMProviderType.REMOTE)
    assert service.allow_document_llm({"data_classification": "internal"}) is True


def test_allow_document_llm_true_for_local_when_frame_descriptions_on():
    settings = _settings(frame_descriptions=True, allow_external_llm=False)
    service, _ = _service(settings, LLMProviderType.LOCAL)
    assert service.allow_document_llm(None) is True


def test_allow_document_llm_blocked_local_when_frame_descriptions_off():
    """Regression: previously allow_document_llm() only checked
    PrivacyGuard, so a local provider could describe document images even
    with FRAME_DESCRIPTIONS=false — the "do we do this at all" switch was
    never consulted for the document path."""
    settings = _settings(frame_descriptions=False)
    service, _ = _service(settings, LLMProviderType.LOCAL)
    assert service.allow_document_llm(None) is False


def test_allow_document_llm_blocked_remote_when_image_upload_off():
    """Regression: previously allow_document_llm() would return True here
    (only PrivacyGuard was checked), letting document images reach a
    remote provider even with the image-upload flag off."""
    settings = _settings(frame_descriptions=True, allow_external_llm=True, allow_image_upload=False)
    service, _ = _service(settings, LLMProviderType.REMOTE)
    assert service.allow_document_llm({"data_classification": "internal"}) is False
