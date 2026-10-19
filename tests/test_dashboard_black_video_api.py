"""API coverage for review-first temporal trimming and separate border cropping."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.test_black_video import _border_clip, _clip, requires_ffmpeg
from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    audio, videos, compressed, transcriptions = (tmp_path / name for name in ("audio", "Videos", "Video_compress", "CarpetaTranscripciones"))
    for folder in (audio, videos, compressed, transcriptions):
        folder.mkdir()
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", compressed)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", AUTH_HEADERS["X-Local-Dashboard-Token"])
    monkeypatch.setattr(dashboard_app, "RESOLVER", SafePathResolver({
        MediaRoot.AUDIO: audio,
        MediaRoot.VIDEOS: videos,
        MediaRoot.VIDEO_COMPRESS: compressed,
        MediaRoot.TRANSCRIPTIONS: transcriptions,
    }))
    return videos


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@requires_ffmpeg
def test_scan_and_trim_api_returns_ranges_and_keeps_original(client, env):
    source = env / "source.mp4"
    _clip(source, [("blue", 2), ("black", 3), ("red", 2)])
    media_id = dashboard_app._to_media_id(MediaRoot.VIDEOS, source)
    scan = client.post("/api/video/black-intervals", headers=AUTH_HEADERS, json={
        "id": media_id, "darkness_threshold": 0.05, "minimum_duration_seconds": 2,
    }).get_json()
    assert scan["status"] == "READY"
    assert len(scan["intervals"]) == 1
    assert scan["removed_seconds"] == pytest.approx(3, abs=0.3)
    source_hash = _sha(source)
    response = client.post("/api/video/remove-black", headers=AUTH_HEADERS, json={
        "id": media_id, "intervals": scan["intervals"], "auto": False,
    })
    assert response.status_code == 200
    assert source.exists() and _sha(source) == source_hash
    assert (env / response.get_json()["name"]).exists()


@requires_ffmpeg
def test_auto_trim_rejects_low_confidence(client, env):
    source = env / "sensitive.mp4"
    _clip(source, [("blue", 2), ("black", 3), ("red", 2)])
    media_id = dashboard_app._to_media_id(MediaRoot.VIDEOS, source)
    scan = client.post("/api/video/black-intervals", headers=AUTH_HEADERS, json={
        "id": media_id, "darkness_threshold": 0.16,
    }).get_json()
    response = client.post("/api/video/remove-black", headers=AUTH_HEADERS, json={
        "id": media_id, "intervals": scan["intervals"], "auto": True, "confidence": "low",
    })
    assert response.status_code == 409
    assert response.get_json()["status"] == "NEEDS_REVIEW"
    assert not (env / "sensitive_trimmed.mp4").exists()


@requires_ffmpeg
def test_border_crop_endpoint_is_separate_from_temporal_scan(client, env):
    source = env / "letterbox.mp4"
    _border_clip(source, kind="letterbox")
    media_id = dashboard_app._to_media_id(MediaRoot.VIDEOS, source)
    border = client.post("/api/video/black-borders", headers=AUTH_HEADERS, json={"id": media_id}).get_json()
    assert border["status"] == "READY"
    assert border["crop"] is not None
    response = client.post("/api/video/crop-black-borders", headers=AUTH_HEADERS, json={
        "id": media_id, "crop": border["crop"], "auto": False,
    })
    assert response.status_code == 200
    assert (env / response.get_json()["name"]).exists()
    temporal = client.post("/api/video/black-intervals", headers=AUTH_HEADERS, json={"id": media_id}).get_json()
    assert temporal["intervals"] == []
