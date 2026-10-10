import json
from dataclasses import replace
from pathlib import Path

from transcript_pipeline.media.compressor import (
    compress_video_high_efficiency,
    get_target_folder,
    process_video_compress_folder,
)
from transcript_pipeline.settings import SETTINGS


def test_compressor_routes_by_configured_project_folder(tmp_path):
    (tmp_path / "projects.json").write_text(
        json.dumps({
            "projects": [
                {
                    "name": "P&G",
                    "match": {"prefix": ["pg_"]},
                    "videos_subfolder": "py_pg",
                }
            ]
        }),
        encoding="utf-8",
    )

    assert get_target_folder("pg_meeting.mp4", tmp_path) == tmp_path / "Videos" / "py_pg"


def test_compressor_honors_manual_project_assignment(tmp_path):
    (tmp_path / "projects.json").write_text(
        json.dumps({
            "projects": [
                {
                    "name": "P&G",
                    "match": {"prefix": ["pg_"]},
                    "videos_subfolder": "py_pg",
                }
            ]
        }),
        encoding="utf-8",
    )
    (tmp_path / "project_overrides.json").write_text(
        json.dumps({"overrides": {"video_compress:20261008_081433.mp4": "P&G"}}),
        encoding="utf-8",
    )

    assert get_target_folder("20261008_081433.mp4", tmp_path) == tmp_path / "Videos" / "py_pg"


def test_compressor_rejects_project_folder_escape(tmp_path):
    (tmp_path / "projects.json").write_text(
        json.dumps({
            "projects": [
                {
                    "name": "P&G",
                    "match": {"prefix": ["pg_"]},
                    "videos_subfolder": "../../outside",
                }
            ]
        }),
        encoding="utf-8",
    )

    assert get_target_folder("pg_meeting.mp4", tmp_path) == tmp_path / "Videos" / "general"


# ── Compression settings wiring + temp_* source exclusion ──────────────


def _fake_video_info() -> dict:
    return {
        "format": {"duration": "60.0", "size": str(10 * 1024 * 1024)},
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "30/1"}
        ],
    }


def test_ffmpeg_command_gets_preset_and_timeout_from_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.SETTINGS",
        replace(SETTINGS, video_compress_preset="fast", video_compress_timeout=1234),
    )
    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.get_video_info", lambda p: _fake_video_info()
    )

    captured = {}

    class FakeProcess:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"compressed")

        def communicate(self, timeout=None):
            captured["timeout"] = timeout
            return "", ""

    monkeypatch.setattr("transcript_pipeline.media.compressor.subprocess.Popen", FakeProcess)

    src = tmp_path / "source.mp4"
    src.write_bytes(b"video")

    assert compress_video_high_efficiency(src, tmp_path / "temp_source.mp4") is True
    cmd = captured["cmd"]
    assert cmd[cmd.index("-preset") + 1] == "fast"
    assert captured["timeout"] == 1234


def _capture_ffmpeg_cmd(monkeypatch, tmp_path, **settings_overrides):
    """Runs compress_video_high_efficiency against a fake ffmpeg and
    returns the command line it built."""
    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.SETTINGS",
        replace(SETTINGS, **settings_overrides),
    )
    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.get_video_info", lambda p: _fake_video_info()
    )

    captured = {}

    class FakeProcess:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"compressed")

        def communicate(self, timeout=None):
            return "", ""

    monkeypatch.setattr("transcript_pipeline.media.compressor.subprocess.Popen", FakeProcess)

    src = tmp_path / "source.mp4"
    src.write_bytes(b"video")
    assert compress_video_high_efficiency(src, tmp_path / "temp_source.mp4") is True
    return captured["cmd"]


def test_ffmpeg_command_uses_libx264_with_avc1_tag(monkeypatch, tmp_path):
    cmd = _capture_ffmpeg_cmd(monkeypatch, tmp_path, video_compress_codec="libx264")
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-tag:v") + 1] == "avc1"


def test_ffmpeg_command_uses_libx265_with_hvc1_tag(monkeypatch, tmp_path):
    cmd = _capture_ffmpeg_cmd(monkeypatch, tmp_path, video_compress_codec="libx265")
    assert cmd[cmd.index("-c:v") + 1] == "libx265"
    assert cmd[cmd.index("-tag:v") + 1] == "hvc1"


def test_temp_files_excluded_from_compression_listing(tmp_path, monkeypatch):
    compress_folder = tmp_path / "Video_compress"
    compress_folder.mkdir()
    (compress_folder / "real.mp4").write_bytes(b"video")
    (compress_folder / "temp_leftover.mp4").write_bytes(b"partial output from an aborted run")

    compressed = []

    def fake_compress(src, dst):
        # >10MB so the plausibility floor doesn't reject it as a partial
        # output from an aborted ffmpeg.
        Path(dst).write_bytes(b"x" * (11 * 1024 * 1024))
        compressed.append(src.name)
        return True

    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.compress_video_high_efficiency", fake_compress
    )

    count = process_video_compress_folder(tmp_path)

    assert compressed == ["real.mp4"]
    assert count == 1
    assert (compress_folder / "temp_leftover.mp4").exists()
    assert not (compress_folder / "real.mp4").exists()
    assert (tmp_path / "Videos" / "general" / "real.mp4").exists()


# ── Sanity check: an interrupted ffmpeg must not cost the original ─────


def _make_source(compress_folder, name, size_bytes):
    src = compress_folder / name
    with src.open("wb") as f:
        f.truncate(size_bytes)  # logical size without writing GBs of data
    return src


def test_implausibly_small_temp_keeps_original_and_skips_move(tmp_path, monkeypatch):
    compress_folder = tmp_path / "Video_compress"
    compress_folder.mkdir()
    src = _make_source(compress_folder, "big.mp4", 1024 ** 3)  # 1 GB source

    def fake_compress(src, dst):
        Path(dst).write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB partial output
        return True

    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.compress_video_high_efficiency", fake_compress
    )
    moves = []
    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.shutil.move", lambda s, d: moves.append((s, d))
    )

    count = process_video_compress_folder(tmp_path)

    assert moves == []
    assert src.exists()  # original kept — never traded for a partial output
    assert not (compress_folder / "temp_big.mp4").exists()
    assert not (tmp_path / "Videos" / "general" / "big.mp4").exists()
    assert count == 0


def test_plausibly_sized_temp_is_moved(tmp_path, monkeypatch):
    compress_folder = tmp_path / "Video_compress"
    compress_folder.mkdir()
    src = _make_source(compress_folder, "normal.mp4", 1024)  # floor of 10 MB applies

    def fake_compress(src, dst):
        Path(dst).write_bytes(b"x" * (11 * 1024 * 1024))
        return True

    monkeypatch.setattr(
        "transcript_pipeline.media.compressor.compress_video_high_efficiency", fake_compress
    )

    count = process_video_compress_folder(tmp_path)

    assert count == 1
    assert not src.exists()
    assert not (compress_folder / "temp_normal.mp4").exists()
    assert (tmp_path / "Videos" / "general" / "normal.mp4").exists()
