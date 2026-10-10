"""Regression: a confidential project's frame descriptions must never reach
a remote LLM, even with ALLOW_EXTERNAL_LLM=true.

Before this fix, `_create_readable_mapping()` called
`_privacy_guard.check(_llm_provider, project_config=None)` with a literal
`None` — the real project (with its `data_classification`) was computed
earlier in `transcribe_file()` but silently dropped before reaching this
check, so a confidential project's classification was never actually
enforced on this path. It now goes through AIEnrichmentService (`_ai_service`),
the same centralized policy every other outbound AI call uses.
"""

import json
from unittest.mock import MagicMock

from transcript_pipeline.llm.enrichment import AIEnrichmentService
from transcript_pipeline.llm.guard import PrivacyGuard
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.settings import Settings
from transcript_pipeline.transcription import processor as processor_module


def _settings(**overrides) -> Settings:
    base = dict(
        whisper_model="large-v3", word_timestamps=False, clean_transcription=False,
        keyframes_required=True, keyframe_method="smart_scene", file_tracker_hash_mode="fast",
        video_compress_crf=25, video_compress_timeout=36000, video_compress_preset="medium",
        tesseract_cmd=None, meeting_frame_interval=15,
        meeting_max_screen_analyses=30, meeting_keep_frames=False, llm_api_key="test-key",
        llm_model="gpt-4o-mini", llm_base_url="https://api.example.com/v1", llm_provider_type="remote",
        allow_external_llm=True, frame_descriptions=True, frame_description_max=20,
        allow_image_upload=True, retention_days=0, dashboard_host="127.0.0.1",
        dashboard_port=5000, upload_max_mb=500, icecream_music=None, icecream_videos=None,
    )
    base.update(overrides)
    return Settings(**base)


def _make_instance():
    return processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)


def _ai_service_with_fake_provider(settings: Settings) -> tuple[AIEnrichmentService, MagicMock]:
    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    fake_provider.describe_frames_for_tutorial.return_value = {}
    service = AIEnrichmentService(fake_provider, PrivacyGuard(settings), settings)
    return service, fake_provider


def _write_frame_mapping(tmp_path) -> dict:
    frames_dir = tmp_path / "clip_Frames"
    frames_dir.mkdir()
    mapping_file = frames_dir / "frame_mapping.json"
    mapping_file.write_text(json.dumps({"frames": [], "video_info": {}}), encoding="utf-8")
    return {"frames_dir": str(frames_dir)}


def test_confidential_project_blocks_remote_frame_description(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    service, fake_provider = _ai_service_with_fake_provider(_settings())
    monkeypatch.setattr(processor_module, "_ai_service", service)

    frame_info = _write_frame_mapping(tmp_path)
    instance = _make_instance()
    transcription_result = {
        "text": "hello world", "segments": [], "language": "en",
        "project": {"data_classification": "confidential"},
    }

    instance._integrate_transcription_with_frames(transcription_result, frame_info)

    fake_provider.describe_frames_for_tutorial.assert_not_called()


def test_internal_project_allows_remote_frame_description(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    service, fake_provider = _ai_service_with_fake_provider(_settings())
    monkeypatch.setattr(processor_module, "_ai_service", service)

    frame_info = _write_frame_mapping(tmp_path)
    instance = _make_instance()
    transcription_result = {
        "text": "hello world", "segments": [], "language": "en",
        "project": {"data_classification": "internal"},
    }

    instance._integrate_transcription_with_frames(transcription_result, frame_info)

    fake_provider.describe_frames_for_tutorial.assert_called_once()


# ── always_tutorial: project-level tutorial override ──────────────────────


def _tutorial_instance(projects: list[dict]):
    instance = _make_instance()
    instance._projects_config = projects
    return instance


def test_always_tutorial_project_forces_tutorial_without_name_match(tmp_path, monkeypatch):
    """A P&G video whose filename never says "tutorial" must still get full
    tutorial treatment when the matched project sets always_tutorial: true."""
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    instance = _tutorial_instance([
        {"name": "P&G", "match": {"filename_contains": ["pg_"]}, "always_tutorial": True},
    ])

    assert instance._is_tutorial(tmp_path / "pg_quarterly_review.mp4") is True


def test_project_without_always_tutorial_keeps_name_only_heuristic(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    instance = _tutorial_instance([
        {"name": "P&G", "match": {"filename_contains": ["pg_"]}},
    ])

    assert instance._is_tutorial(tmp_path / "pg_quarterly_review.mp4") is False
    assert instance._is_tutorial(tmp_path / "pg_Tutorial_excel.mp4") is True


def test_always_tutorial_false_keeps_name_only_heuristic(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    instance = _tutorial_instance([
        {"name": "P&G", "match": {"filename_contains": ["pg_"]}, "always_tutorial": False},
    ])

    assert instance._is_tutorial(tmp_path / "pg_quarterly_review.mp4") is False


def test_always_tutorial_ignores_unmatched_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    instance = _tutorial_instance([
        {"name": "P&G", "match": {"filename_contains": ["pg_"]}, "always_tutorial": True},
    ])

    assert instance._is_tutorial(tmp_path / "other_meeting.mp4") is False


def test_tutorial_features_unavailable_disables_project_override_too(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", False)
    instance = _tutorial_instance([
        {"name": "P&G", "match": {"filename_contains": ["pg_"]}, "always_tutorial": True},
    ])

    assert instance._is_tutorial(tmp_path / "pg_tutorial.mp4") is False
