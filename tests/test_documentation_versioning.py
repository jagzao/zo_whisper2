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


def test_explicit_regeneration_forces_new_version_for_unchanged_evidence(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_mapping.json").write_text('{"frames": []}', encoding="utf-8")

    def generate(root, **kwargs):
        manual = root / "manual"
        manual.mkdir(exist_ok=True)
        (manual / "MANUAL.md").write_text("Synthetic manual", encoding="utf-8")
        return {"status": "MANUAL_READY"}

    first = regenerate_versioned(frames, "videos:sample.mp4", generate)
    second = regenerate_versioned(frames, "videos:sample.mp4", generate, force_new=True)

    assert first["version"]["documentation_version"] == 1
    assert second["version"]["documentation_version"] == 2
    assert second["version"]["previous_version"] == 1
    assert [v["documentation_version"] for v in list_versions(frames)] == [2, 1]


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


def test_invalid_synthesis_is_retried_for_same_evidence(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_mapping.json").write_text('{"frames": []}', encoding="utf-8")
    calls = []

    def generate(root, **kwargs):
        calls.append(1)
        manual = root / "manual"
        manual.mkdir(exist_ok=True)
        if len(calls) == 1:
            return {"status": "SYNTHESIS_INVALID"}
        (manual / "MANUAL.md").write_text("valid synthesis", encoding="utf-8")
        return {"status": "SYNTHESIS_READY"}

    failed = regenerate_versioned(frames, "videos:sample.mp4", generate)
    retried = regenerate_versioned(frames, "videos:sample.mp4", generate)

    assert failed["version"]["generation_status"] == "SYNTHESIS_INVALID"
    assert retried["version"]["documentation_version"] == 2
    assert retried["version"]["generation_status"] == "SYNTHESIS_READY"
    assert calls == [1, 1]


def test_changed_evidence_creates_linked_version_and_preserves_previous(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    mapping = frames / "frame_mapping.json"
    mapping.write_text('{"frames": []}', encoding="utf-8")

    def generate(root, **kwargs):
        manual = root / "manual"
        manual.mkdir(exist_ok=True)
        (manual / "MANUAL.md").write_text(mapping.read_text(encoding="utf-8"), encoding="utf-8")
        return {"status": "MANUAL_READY"}

    first = regenerate_versioned(frames, "videos:sample.mp4", generate)["version"]
    mapping.write_text('{"frames": [{"id": 1}]}', encoding="utf-8")
    second = regenerate_versioned(frames, "videos:sample.mp4", generate)["version"]
    versions = list_versions(frames)
    assert second["documentation_version"] == 2
    assert second["previous_version"] == first["documentation_version"]
    assert len(versions) == 2
    assert (frames / "documentation_versions" / "000001" / "manual" / "MANUAL.md").read_text() == '{"frames": []}'
