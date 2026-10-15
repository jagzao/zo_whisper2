"""Unit tests: non-fatal ffprobe audio-stream detection (W7).

`media_has_audio_stream` must report audio presence, report video-only media,
and return `None` (never raise) when probing fails — so a missing audio track
can never fail a caller such as the documentation flow.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from transcript_pipeline.media import utils as media_utils


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["ffprobe"], returncode=0, stdout=stdout, stderr="")


def _streams(*types: str) -> str:
    return json.dumps({"streams": [{"codec_type": t} for t in types]})


def test_media_has_audio_stream_true(monkeypatch):
    monkeypatch.setattr(media_utils.subprocess, "run", lambda cmd, **kw: _completed(_streams("video", "audio")))
    assert media_utils.media_has_audio_stream("clip.webm") is True


def test_media_has_audio_stream_false_for_video_only(monkeypatch):
    monkeypatch.setattr(media_utils.subprocess, "run", lambda cmd, **kw: _completed(_streams("video")))
    assert media_utils.media_has_audio_stream("clip.webm") is False


@pytest.mark.parametrize("stdout", ["{}", '{"streams": []}'])
def test_media_has_audio_stream_unknown_for_no_streams(monkeypatch, stdout):
    monkeypatch.setattr(media_utils.subprocess, "run", lambda cmd, **kw: _completed(stdout))
    assert media_utils.media_has_audio_stream("clip.webm") is None


@pytest.mark.parametrize(
    "exc",
    [
        subprocess.CalledProcessError(1, ["ffprobe"]),
        subprocess.TimeoutExpired(["ffprobe"], 30),
        FileNotFoundError("ffprobe"),
    ],
)
def test_media_has_audio_stream_unknown_and_never_raises(monkeypatch, exc):
    def _boom(cmd, **kw):
        raise exc

    monkeypatch.setattr(media_utils.subprocess, "run", _boom)
    assert media_utils.media_has_audio_stream("clip.webm") is None


def test_media_has_audio_stream_unknown_on_bad_json(monkeypatch):
    monkeypatch.setattr(media_utils.subprocess, "run", lambda cmd, **kw: _completed("not json"))
    assert media_utils.media_has_audio_stream("clip.webm") is None
