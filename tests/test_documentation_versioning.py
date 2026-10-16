import pytest

from transcript_pipeline.documentation.versioning import list_versions, regenerate_versioned


def test_documentation_version_metadata_and_idempotency(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_mapping.json").write_text('{"frames": []}', encoding="utf-8")
    calls = []

    def generate(root, **kwargs):
        calls.append(root)
        manual = root / "manual"
        manual.mkdir(exist_ok=True)
        (manual / "MANUAL.md").write_text("Synthetic manual", encoding="utf-8")
        return {"status": "MANUAL_READY"}

    first = regenerate_versioned(frames, "videos:sample.mp4", generate)
    again = regenerate_versioned(frames, "videos:sample.mp4", generate)
    versions = list_versions(frames)
    assert first["version"]["documentation_version"] == 1
    assert first["version"]["pipeline_version"] == "documentation-v2"
    assert first["version"]["source_video_id"] == "videos:sample.mp4"
    assert first["version"]["previous_version"] is None
    assert again["status"] == "IDEMPOTENT"
    assert len(calls) == 1
    assert len(versions) == 1
    assert (frames / "documentation_versions" / "000001" / "manual" / "MANUAL.md").read_text() == "Synthetic manual"


def test_failed_generation_preserves_current_docs(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_mapping.json").write_text('{"frames": []}', encoding="utf-8")
    manual = frames / "manual"
    manual.mkdir()
    (manual / "MANUAL.md").write_text("last good", encoding="utf-8")

    def fail(root, **kwargs):
        (root / "manual" / "MANUAL.md").write_text("partial", encoding="utf-8")
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError):
        regenerate_versioned(frames, "videos:sample.mp4", fail)
    assert (manual / "MANUAL.md").read_text() == "last good"
    assert list_versions(frames) == []
