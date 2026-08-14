"""Regression: a confidential project's frame descriptions must never reach
a remote LLM, even with ALLOW_EXTERNAL_LLM=true.

Before this fix, `_create_readable_mapping()` called
`_privacy_guard.check(_llm_provider, project_config=None)` with a literal
`None` — the real project (with its `data_classification`) was computed
earlier in `transcribe_file()` but silently dropped before reaching this
check, so a confidential project's classification was never actually
enforced on this path.
"""

import json
from unittest.mock import MagicMock

from transcript_pipeline.llm.guard import PrivacyGuard
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.settings import Settings
from transcript_pipeline.transcription import processor as processor_module


def _settings(**overrides) -> Settings:
    base = dict(
        whisper_model="large-v3", word_timestamps=False, clean_transcription=False,
        keyframes_required=True, keyframe_method="smart_scene", file_tracker_hash_mode="fast",
        video_compress_crf=25, tesseract_cmd=None, meeting_frame_interval=15,
        meeting_max_screen_analyses=30, meeting_keep_frames=False, llm_api_key="test-key",
        llm_model="gpt-4o-mini", llm_base_url="https://api.example.com/v1", llm_provider_type="remote",
        allow_external_llm=True, frame_descriptions=True, frame_description_max=20,
        privacy_mode="cloud", allow_frame_upload=True, retention_days=0, dashboard_host="127.0.0.1",
        dashboard_port=5000, upload_max_mb=500, icecream_music=None, icecream_videos=None,
    )
    base.update(overrides)
    return Settings(**base)


def _make_instance():
    return processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)


def test_confidential_project_blocks_remote_frame_description(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    monkeypatch.setattr(processor_module, "_privacy_guard", PrivacyGuard(_settings()))

    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    monkeypatch.setattr(processor_module, "_llm_provider", fake_provider)

    frames_dir = tmp_path / "clip_Frames"
    frames_dir.mkdir()
    mapping_file = frames_dir / "frame_mapping.json"
    mapping_file.write_text(json.dumps({"frames": [], "video_info": {}}), encoding="utf-8")

    instance = _make_instance()
    transcription_result = {
        "text": "hello world", "segments": [], "language": "en",
        "project": {"data_classification": "confidential"},
    }
    frame_info = {"frames_dir": str(frames_dir)}

    instance._integrate_transcription_with_frames(transcription_result, frame_info)

    fake_provider.describe_frames_for_tutorial.assert_not_called()


def test_internal_project_allows_remote_frame_description(tmp_path, monkeypatch):
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    monkeypatch.setattr(processor_module, "_privacy_guard", PrivacyGuard(_settings()))

    fake_provider = MagicMock()
    fake_provider.provider_type = LLMProviderType.REMOTE
    fake_provider.describe_frames_for_tutorial.return_value = {}
    monkeypatch.setattr(processor_module, "_llm_provider", fake_provider)

    frames_dir = tmp_path / "clip_Frames"
    frames_dir.mkdir()
    mapping_file = frames_dir / "frame_mapping.json"
    mapping_file.write_text(json.dumps({"frames": [], "video_info": {}}), encoding="utf-8")

    instance = _make_instance()
    transcription_result = {
        "text": "hello world", "segments": [], "language": "en",
        "project": {"data_classification": "internal"},
    }
    frame_info = {"frames_dir": str(frames_dir)}

    instance._integrate_transcription_with_frames(transcription_result, frame_info)

    fake_provider.describe_frames_for_tutorial.assert_called_once()
