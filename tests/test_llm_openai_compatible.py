"""Mocked-HTTP tests for OpenAICompatibleProvider — no real network calls.

Covers the retry behavior added to _make_request(): bounded retries on
transient errors (connection issues, 429, 5xx), fail-fast on 4xx.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
from transcript_pipeline.settings import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        whisper_model="large-v3", word_timestamps=False, clean_transcription=False,
        keyframes_required=True, keyframe_method="smart_scene", file_tracker_hash_mode="fast", video_compress_crf=25,
        tesseract_cmd=None, meeting_frame_interval=15, meeting_max_screen_analyses=30,
        meeting_keep_frames=False, llm_api_key="test-key", llm_model="gpt-4o-mini",
        llm_base_url="https://api.example.com/v1", llm_provider_type="remote",
        allow_external_llm=True, frame_descriptions=False, frame_description_max=20,
        allow_frame_upload=False, retention_days=0,
        dashboard_host="127.0.0.1", dashboard_port=5000, upload_max_mb=500,
        icecream_music=None, icecream_videos=None,
    )
    base.update(overrides)
    return Settings(**base)


def _ok_response(content: str = "the summary") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def _error_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    error = requests.HTTPError(f"{status_code} error")
    error.response = resp
    resp.raise_for_status.side_effect = error
    return resp


@pytest.fixture
def provider():
    return OpenAICompatibleProvider(_settings(), max_retries=2, backoff_seconds=0)


def test_generate_summary_success_no_retry_needed(provider):
    with patch("transcript_pipeline.llm.openai_compatible.requests.post", return_value=_ok_response("hi")) as mock_post:
        result = provider.generate_summary("transcript text")
    assert result == "hi"
    assert mock_post.call_count == 1


def test_generate_summary_sends_bearer_token(provider):
    with patch("transcript_pipeline.llm.openai_compatible.requests.post", return_value=_ok_response()) as mock_post:
        provider.generate_summary("text")
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"


def test_retries_on_connection_error_then_succeeds(provider):
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        side_effect=[requests.ConnectionError("boom"), _ok_response("recovered")],
    ) as mock_post:
        result = provider.generate_summary("text")
    assert result == "recovered"
    assert mock_post.call_count == 2


def test_retries_on_503_then_succeeds(provider):
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        side_effect=[_error_response(503), _ok_response("recovered after 503")],
    ) as mock_post:
        result = provider.generate_summary("text")
    assert result == "recovered after 503"
    assert mock_post.call_count == 2


def test_retries_on_429_then_succeeds(provider):
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        side_effect=[_error_response(429), _ok_response("recovered after rate limit")],
    ) as mock_post:
        result = provider.generate_summary("text")
    assert result == "recovered after rate limit"
    assert mock_post.call_count == 2


def test_no_retry_on_400_bad_request(provider):
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        return_value=_error_response(400),
    ) as mock_post:
        with pytest.raises(requests.HTTPError):
            provider.generate_summary("text")
    assert mock_post.call_count == 1


def test_no_retry_on_401_unauthorized(provider):
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        return_value=_error_response(401),
    ) as mock_post:
        with pytest.raises(requests.HTTPError):
            provider.generate_summary("text")
    assert mock_post.call_count == 1


def test_exhausts_retries_and_raises(provider):
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        return_value=_error_response(503),
    ) as mock_post:
        with pytest.raises(requests.HTTPError):
            provider.generate_summary("text")
    # max_retries=2 -> 1 initial attempt + 2 retries = 3 total calls
    assert mock_post.call_count == 3


def test_zero_max_retries_fails_fast():
    provider = OpenAICompatibleProvider(_settings(), max_retries=0, backoff_seconds=0)
    with patch(
        "transcript_pipeline.llm.openai_compatible.requests.post",
        return_value=_error_response(503),
    ) as mock_post:
        with pytest.raises(requests.HTTPError):
            provider.generate_summary("text")
    assert mock_post.call_count == 1
