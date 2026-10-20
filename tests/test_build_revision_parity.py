"""Served revision marker parity (AC-08).

Both HTTP origins are served by the same Flask app and must advertise the same
build revision in the HTML meta tag and the response header, so a LAN client can
never be silently served a different revision than localhost.
"""

from __future__ import annotations

import re

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver


@pytest.fixture
def env(tmp_path, monkeypatch):
    audio = tmp_path / "audio"
    videos = tmp_path / "Videos"
    video_compress = tmp_path / "Video_compress"
    transcriptions = tmp_path / "CarpetaTranscripciones"
    for d in (audio, videos, video_compress, transcriptions):
        d.mkdir(parents=True)
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "LOG_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", video_compress)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    monkeypatch.setattr(dashboard_app, "RESOLVER", SafePathResolver({
        MediaRoot.AUDIO: audio, MediaRoot.VIDEOS: videos,
        MediaRoot.VIDEO_COMPRESS: video_compress, MediaRoot.TRANSCRIPTIONS: transcriptions,
    }))
    return tmp_path


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def test_index_and_header_advertise_same_revision(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "BUILD_REVISION", "deadbeefcafe")
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    match = re.search(r'<meta name="whisper-build" content="([^"]+)">', body)
    assert match is not None
    assert match.group(1) == "deadbeefcafe"
    assert response.headers["X-Whisper-Build"] == "deadbeefcafe"
