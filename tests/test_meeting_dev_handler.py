"""Regression: _analyze_frame_vision previously sent frames to the vision
LLM checking only PrivacyGuard + a local API-key truthiness check — it never
consulted FRAME_DESCRIPTIONS or ALLOW_FRAME_UPLOAD at all. Now that it goes
through AIEnrichmentService, both flags are enforced.
"""

from unittest.mock import MagicMock

from transcript_pipeline.handlers import meeting_dev_handler as handler_module
from transcript_pipeline.llm.enrichment import AIEnrichmentService
from transcript_pipeline.llm.guard import PrivacyGuard
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.settings import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        whisper_model="large-v3", word_timestamps=False, clean_transcription=False,
        keyframes_required=True, keyframe_method="smart_scene", file_tracker_hash_mode="fast",
        video_compress_crf=25, tesseract_cmd=None, meeting_frame_interval=15,
        meeting_max_screen_analyses=30, meeting_keep_frames=False, llm_api_key="test-key",
        llm_model="gpt-4o-mini", llm_base_url="https://api.example.com/v1", llm_provider_type="remote",
        allow_external_llm=True, frame_descriptions=False, frame_description_max=20,
        privacy_mode="cloud", allow_frame_upload=True, retention_days=0, dashboard_host="127.0.0.1",
        dashboard_port=5000, upload_max_mb=500, icecream_music=None, icecream_videos=None,
    )
    base.update(overrides)
    return Settings(**base)


def _handler(tmp_path):
    handler = handler_module.MeetingDevHandler(str(tmp_path))
    handler.llm_api_key = "test-key"
    return handler


def test_frame_vision_blocked_when_frame_descriptions_off(tmp_path, monkeypatch):
    settings = _settings(frame_descriptions=False)
    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    service = AIEnrichmentService(fake_provider, PrivacyGuard(settings), settings)
    monkeypatch.setattr(handler_module, "_ai_service", service)

    frame_path = tmp_path / "frame_0001.jpg"
    frame_path.write_bytes(b"fake image bytes")

    handler = _handler(tmp_path)
    result = handler._analyze_frame_vision(frame_path, "", None)

    assert result is None
    fake_provider.describe_frame_with_prompt.assert_not_called()


def test_frame_vision_blocked_when_frame_upload_off_for_remote(tmp_path, monkeypatch):
    settings = _settings(frame_descriptions=True, allow_frame_upload=False)
    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    service = AIEnrichmentService(fake_provider, PrivacyGuard(settings), settings)
    monkeypatch.setattr(handler_module, "_ai_service", service)

    frame_path = tmp_path / "frame_0001.jpg"
    frame_path.write_bytes(b"fake image bytes")

    handler = _handler(tmp_path)
    result = handler._analyze_frame_vision(frame_path, "", None)

    assert result is None
    fake_provider.describe_frame_with_prompt.assert_not_called()


def test_frame_vision_allowed_when_all_flags_permissive(tmp_path, monkeypatch):
    settings = _settings(frame_descriptions=True, allow_frame_upload=True, allow_external_llm=True)
    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    fake_provider.describe_frame_with_prompt.return_value = '{"summary": "ok"}'
    service = AIEnrichmentService(fake_provider, PrivacyGuard(settings), settings)
    monkeypatch.setattr(handler_module, "_ai_service", service)

    frame_path = tmp_path / "frame_0001.jpg"
    frame_path.write_bytes(b"fake image bytes")

    handler = _handler(tmp_path)
    result = handler._analyze_frame_vision(frame_path, "", {"data_classification": "internal"})

    assert result == {"summary": "ok"}
    fake_provider.describe_frame_with_prompt.assert_called_once()


def test_scan_documents_blocks_vision_client_for_confidential_project(tmp_path, monkeypatch):
    settings = _settings(allow_external_llm=False)
    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    service = AIEnrichmentService(fake_provider, PrivacyGuard(settings), settings)
    monkeypatch.setattr(handler_module, "_ai_service", service)

    fake_markitdown_cls = MagicMock()
    monkeypatch.setattr(handler_module, "MarkItDown", fake_markitdown_cls)

    handler = _handler(tmp_path)
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    target_folder = tmp_path / "target"

    handler._scan_documents(source_folder, target_folder, {"data_classification": "confidential"})

    # No llm_client kwarg — the guard correctly saw the real (confidential)
    # classification, not a hardcoded/None project_config.
    fake_markitdown_cls.assert_called_once_with()


def test_scan_documents_allows_vision_client_for_internal_project(tmp_path, monkeypatch):
    settings = _settings(allow_external_llm=True)
    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    service = AIEnrichmentService(fake_provider, PrivacyGuard(settings), settings)
    monkeypatch.setattr(handler_module, "_ai_service", service)

    fake_markitdown_cls = MagicMock()
    monkeypatch.setattr(handler_module, "MarkItDown", fake_markitdown_cls)

    handler = _handler(tmp_path)
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    target_folder = tmp_path / "target"

    handler._scan_documents(source_folder, target_folder, {"data_classification": "internal"})

    assert fake_markitdown_cls.call_args.kwargs.get("llm_client") is not None
