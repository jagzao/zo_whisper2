import json

from transcript_pipeline import pipeline_metrics


def test_metrics_persist_stage_durations_and_total(tmp_path, monkeypatch):
    path = tmp_path / "metrics.json"
    monkeypatch.setattr(pipeline_metrics, "_PATH", path)
    pipeline_metrics.record_stage("Demo", "sample.mp4", "upload", 1.25)
    pipeline_metrics.record_stage("Demo", "sample.mp4", "processing_media", 3.5)
    metrics = pipeline_metrics.get_metrics("Demo", "sample.mp4")
    assert metrics["stages"]["upload"]["duration_seconds"] == 1.25
    assert metrics["stages"]["processing_media"]["duration_seconds"] == 3.5
    assert 3.5 <= metrics["total_seconds"] <= 4.75
    assert json.loads(path.read_text(encoding="utf-8"))["demo/sample.mp4"]["filename"] == "sample.mp4"
    pipeline_metrics.remove_metrics("Demo", "sample.mp4")
    assert pipeline_metrics.get_metrics("Demo", "sample.mp4")["stages"] == {}
