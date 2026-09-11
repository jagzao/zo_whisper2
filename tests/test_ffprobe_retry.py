"""Coverage for the bounded ffprobe retry helper (AC15).

Windows ffprobe intermittently crashes (0xC0000409 STATUS_STACK_BUFFER_OVERRUN,
reported as exit code 3221225794) and that transient class must be retried,
while permanent errors (non-zero exit, missing binary) must not.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.media import compressor
from transcript_pipeline.media import utils as media_utils

CRASH_CODE = 3221225794


def _completed(stdout: str = "{}") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["ffprobe"], returncode=0, stdout=stdout, stderr="")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(media_utils.time, "sleep", lambda seconds: None)


def test_retries_on_crash_code(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise subprocess.CalledProcessError(CRASH_CODE, cmd, output="", stderr="")
        return _completed('{"streams": []}')

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    result = media_utils.run_ffprobe(["ffprobe"])
    assert result.returncode == 0
    assert calls["n"] == 3


def test_retries_on_timeout(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise subprocess.TimeoutExpired(cmd, 30)
        return _completed()

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    result = media_utils.run_ffprobe(["ffprobe"])
    assert result.returncode == 0
    assert calls["n"] == 3


def test_no_retry_on_timeout_when_disabled(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired):
        media_utils.run_ffprobe(["ffprobe"], retry_on_timeout=False)
    assert calls["n"] == 1


def test_no_retry_on_normal_error(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        media_utils.run_ffprobe(["ffprobe"])
    assert calls["n"] == 1


def test_no_retry_on_file_not_found(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    with pytest.raises(FileNotFoundError):
        media_utils.run_ffprobe(["ffprobe"])
    assert calls["n"] == 1


def test_is_valid_media_file_retries(monkeypatch, tmp_path):
    calls = {"n": 0}
    payload = json.dumps({"streams": [{"codec_type": "video"}]})

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.CalledProcessError(CRASH_CODE, cmd)
        return _completed(payload)

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    target = tmp_path / "clip.mp4"
    target.write_bytes(b"fake")
    assert dashboard_app._is_valid_media_file(target) is True
    assert calls["n"] == 2


def test_get_video_info_retries(monkeypatch, tmp_path):
    calls = {"n": 0}
    payload = json.dumps({"format": {"duration": "1.0"}, "streams": [{"codec_type": "video"}]})

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.CalledProcessError(CRASH_CODE, cmd)
        return _completed(payload)

    monkeypatch.setattr(media_utils.subprocess, "run", fake_run)

    info = compressor.get_video_info(tmp_path / "clip.mp4")
    assert info == {"format": {"duration": "1.0"}, "streams": [{"codec_type": "video"}]}
    assert calls["n"] == 2
