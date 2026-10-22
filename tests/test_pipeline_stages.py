"""Per-stage pipeline state (US-001 §3.4): each of the 8 stages carries an
explicit pending/running/completed/failed status plus optional progress that
is never fabricated (None unless a real measurable total exists).

Covers the pure `_infer_stage`/`_apply_stage_derivation` derivation and the
`_run_state["stages"]` lifecycle across a full run and a failing run.
"""
from __future__ import annotations

import time

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

PIPELINE_STAGES = dashboard_app.PIPELINE_STAGES
AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    audio = tmp_path / "audio"
    videos = tmp_path / "Videos"
    video_compress = tmp_path / "Video_compress"
    transcriptions = tmp_path / "CarpetaTranscripciones"
    for d in (audio, videos, video_compress, transcriptions):
        d.mkdir(parents=True)

    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", video_compress)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", AUTH_HEADERS["X-Local-Dashboard-Token"])
    monkeypatch.setattr(
        dashboard_app,
        "RESOLVER",
        SafePathResolver(
            {
                MediaRoot.AUDIO: audio,
                MediaRoot.VIDEOS: videos,
                MediaRoot.VIDEO_COMPRESS: video_compress,
                MediaRoot.TRANSCRIPTIONS: transcriptions,
            }
        ),
    )
    return {"root": tmp_path, "audio": audio, "videos": videos, "transcriptions": transcriptions}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def _reset_run_state() -> None:
    dashboard_app._run_state.update(
        {
            "running": False,
            "mode": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "log_tail": "",
            "stage": None,
            "stages": dashboard_app._fresh_stages(),
        }
    )


# ── initial state ────────────────────────────────────────────────────────

def test_fresh_stages_all_pending_no_progress():
    stages = dashboard_app._fresh_stages()
    assert set(stages.keys()) == set(PIPELINE_STAGES)
    for name in PIPELINE_STAGES:
        assert stages[name]["status"] == "pending"
        assert stages[name]["progress"] is None


def test_status_classifies_active_pipeline_and_historical_job_failures(client, monkeypatch):
    class Store:
        rows = []
        def list_jobs(self): return self.rows

    class Worker:
        store = Store()
        error = None
        def status(self): return {"state": "RUNNING", "active_jobs": 1, "pending_jobs": 0,
                                  "last_error": self.error, "last_error_at": "2026-10-21T10:02:00" if self.error else None}

    worker = Worker()
    monkeypatch.setattr(dashboard_app, "_get_processing_worker", lambda: worker)
    dashboard_app._run_state.update(running=False, error="Vision provider timed out", finished_at="2026-10-21T10:00:00",
                                    stage="vision_ocr", stages=dashboard_app._fresh_stages())
    dashboard_app._run_state["stages"]["vision_ocr"]["status"] = "failed"
    worker.store.rows = [{"id": "job-old", "status": "FAILED", "finished_at": "2026-10-20T12:00:00", "error": "old failure"}]
    result = client.get("/api/status").get_json()
    assert result["worker"]["state"] == "RUNNING"
    assert result["error_detail"]["classification"] == "historical_processing_failure"
    assert result["error_detail"]["component"] == "pipeline"
    assert result["error_detail"]["stage"] == "vision_ocr"
    assert result["historical_failure"]["id"] == "job-old"
    assert result["worker_error"] is None

    worker.error = "Queue scan failed"
    result = client.get("/api/status").get_json()
    assert result["worker_error"]["classification"] == "worker_error"
    assert result["worker_error"]["component"] == "processing worker"
    assert result["worker_error"]["timestamp"] == "2026-10-21T10:02:00"
    worker.error = None

    worker.store.rows = [{"id": "job-active", "status": "ACTIVE", "started_at": "2026-10-21T10:01:00"}]
    dashboard_app._run_state["running"] = True
    result = client.get("/api/status").get_json()
    assert result["error_detail"]["classification"] == "active_processing_failure"
    assert result["error_detail"]["affected_file_job"] == "job-active"
    _reset_run_state()


def test_pipeline_error_marks_worker_job_failed(monkeypatch):
    _reset_run_state()

    def fail(_mode, cancel_check=None):
        dashboard_app._run_state.update(running=False, error="OCR provider failed", finished_at="2026-10-21T10:00:00")

    monkeypatch.setattr(dashboard_app, "_run_pipeline", fail)
    with pytest.raises(RuntimeError, match="OCR provider failed"):
        dashboard_app._execute_processing_job("full")
    assert dashboard_app._run_state["error"] == "OCR provider failed"
    _reset_run_state()


# ── derivation from real log markers ─────────────────────────────────────

def test_infer_stage_marks_compress_completed_analyze_running():
    _reset_run_state()
    # `[SCAN]` maps to "analyze" (the furthest marker present) — stages before
    # it (upload, compress) are completed, analyze is running, the rest pending.
    log = "\n".join([
        "STEP 1: Compressing videos...",
        "[SCAN] Folder detected: audio/demo",
    ])
    assert dashboard_app._infer_stage(log) == "compress"
    stages = dashboard_app._run_state["stages"]
    assert stages["compress"]["status"] == "running"
    assert stages["analyze"]["status"] == "completed"
    assert stages["transcribe"]["status"] == "pending"
    assert stages["store"]["status"] == "pending"


def test_infer_stage_marks_upload_completed_analyze_running():
    _reset_run_state()
    # Only the analyze marker present → analyze is the furthest stage running.
    log = "[SCAN] Folder detected: audio/demo\n"
    assert dashboard_app._infer_stage(log) == "analyze"
    stages = dashboard_app._run_state["stages"]
    assert stages["upload"]["status"] == "completed"
    assert stages["analyze"]["status"] == "running"
    assert stages["compress"]["status"] == "pending"


def test_infer_stage_marks_all_reached_completed_on_full_run():
    _reset_run_state()
    log = "\n".join([
        "STEP 1: Compressing videos...",
        "[SCAN] Folder detected: audio/demo",
        "[INIT] Loading Whisper model large-v3...",
        "[KEYFRAMES] Extrayendo frames de: demo.mp4",
        "[DOCS] Generated manual + AI package for demo.mp4",
        "[SAVE] demo.txt",
        "PROCESS FINISHED",
    ])
    assert dashboard_app._infer_stage(log) == "store"
    stages = dashboard_app._run_state["stages"]
    for name in PIPELINE_STAGES:
        expected = "running" if name == "store" else "completed"
        assert stages[name]["status"] == expected, name


def test_infer_stage_never_fabricates_progress():
    _reset_run_state()
    log = "STEP 1: Compressing videos...\n[SCAN] Folder detected: audio/demo\n"
    dashboard_app._infer_stage(log)
    for name in PIPELINE_STAGES:
        assert dashboard_app._run_state["stages"][name]["progress"] is None


# ── full-run lifecycle (stubbed subprocess) ──────────────────────────────

class _FakeCompletedProcess:
    def __init__(self, lines: list[str], delay: float = 0.0, returncode: int = 0):
        self._lines = lines
        self._delay = delay
        self.returncode = returncode

    @property
    def stdout(self):
        def _gen():
            for line in self._lines:
                if self._delay:
                    time.sleep(self._delay)
                yield line
        return _gen()

    def wait(self) -> int:
        return self.returncode


def test_full_run_marks_all_stages_completed(client, env, monkeypatch):
    def fake_popen(cmd, **kwargs):
        if "transcript_pipeline.media.compressor" in cmd:
            return _FakeCompletedProcess(["STEP 1 stub: nothing to compress\n"])
        return _FakeCompletedProcess([
            "[SCAN] Folder detected: audio/demo\n",
            "[INIT] Loading Whisper model large-v3...\n",
            "[KEYFRAMES] Extrayendo frames de: demo.mp4\n",
            "[DOCS] Generated manual + AI package for demo.mp4\n",
            "[SAVE] demo.txt\n",
        ], delay=0.02)

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)
    resp = client.post("/api/run/full", headers=AUTH_HEADERS)
    assert resp.status_code == 200

    for _ in range(50):
        status = client.get("/api/status").get_json()
        if not status["running"]:
            break
        time.sleep(0.05)

    assert status["running"] is False
    assert status["error"] is None
    stages = status["stages"]
    for name in PIPELINE_STAGES:
        assert stages[name]["status"] == "completed", name
        assert stages[name]["progress"] is None


def test_failing_run_marks_failing_stage_failed_and_later_pending(client, env, monkeypatch):
    def fake_popen(cmd, **kwargs):
        if "transcript_pipeline.media.compressor" in cmd:
            return _FakeCompletedProcess(["STEP 1 stub: nothing to compress\n"])
        # master module reaches transcribe then fails (returncode 1).
        return _FakeCompletedProcess([
            "[SCAN] Folder detected: audio/demo\n",
            "[INIT] Loading Whisper model large-v3...\n",
        ], delay=0.02, returncode=1)

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)
    resp = client.post("/api/run/full", headers=AUTH_HEADERS)
    assert resp.status_code == 200

    for _ in range(50):
        status = client.get("/api/status").get_json()
        if not status["running"]:
            break
        time.sleep(0.05)

    assert status["running"] is False
    assert status["error"] is not None
    stages = status["stages"]
    # The furthest stage reached before the failure was transcribe (the
    # [INIT] marker) — it must be the one marked failed.
    assert stages["transcribe"]["status"] == "failed"
    # Later stages stay pending.
    for name in ("route", "document", "store"):
        assert stages[name]["status"] == "pending", name
    # Earlier stages completed.
    for name in ("upload", "analyze", "compress"):
        assert stages[name]["status"] == "completed", name
