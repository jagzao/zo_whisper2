"""W25 dashboard tests: LAN opt-in Host/Origin allowlist, backend health, and
advertised LAN URLs.

Default (LAN off) behavior is asserted unchanged: loopback-only hostnames are
accepted and any LAN host is rejected. With LAN mode the configured/detected
hosts are accepted while the per-process token still gates mutating requests.
"""

from __future__ import annotations

import dataclasses
import time

import pytest

from transcript_pipeline import lan_access
from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver
from transcript_pipeline.settings import SETTINGS

TOKEN = "test-dashboard-token"
AUTH_HEADERS = {"X-Local-Dashboard-Token": TOKEN}


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
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", TOKEN)
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
    # LAN is off by default: the module allowlist must start empty.
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", set())
    return {"root": tmp_path}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


# ── Host allowlist ────────────────────────────────────────────────────────

def test_loopback_host_still_accepted(client):
    assert client.get("/api/status", headers={"Host": "127.0.0.1"}).status_code == 200


def test_lan_host_rejected_by_default(client):
    resp = client.get("/api/status", headers={"Host": "192.168.1.50"})
    assert resp.status_code == 403


def test_lan_host_accepted_with_lan_allowlist(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    assert client.get("/api/status", headers={"Host": "192.168.1.50"}).status_code == 200


def test_lan_hostname_accepted_with_lan_allowlist(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"whisper.local"})
    assert client.get("/api/status", headers={"Host": "whisper.local"}).status_code == 200


def test_lan_mode_rejects_public_remote_client(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "SETTINGS", dataclasses.replace(SETTINGS, lan_access=True))
    resp = client.get("/api/status", environ_overrides={"REMOTE_ADDR": "8.8.8.8"})
    assert resp.status_code == 403


def test_lan_mode_accepts_private_remote_client(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "SETTINGS", dataclasses.replace(SETTINGS, lan_access=True))
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    resp = client.get(
        "/api/status",
        headers={"Host": "192.168.1.50"},
        environ_overrides={"REMOTE_ADDR": "192.168.1.22"},
    )
    assert resp.status_code == 200


def test_authorized_lan_run_full_starts_pipeline(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_run_state", {
        "running": False, "mode": None, "started_at": None, "finished_at": None,
        "error": None, "log_tail": "", "stage": None, "stages": {},
    })
    monkeypatch.setattr(dashboard_app, "SETTINGS", dataclasses.replace(SETTINGS, lan_access=True))
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    import threading
    started = []
    done = threading.Event()
    def run(mode, **_kwargs):
        started.append(mode)
        done.set()
    monkeypatch.setattr(dashboard_app, "_run_pipeline", run)
    response = client.post(
        "/api/run/full",
        headers={**AUTH_HEADERS, "Host": "192.168.1.50", "Origin": "https://192.168.1.50:5001"},
        environ_overrides={"REMOTE_ADDR": "192.168.1.22"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert response.get_json()["mode"] == "full"
    assert done.wait(1)
    assert started == ["full"]
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and dashboard_app._run_state["running"]:
        time.sleep(0.005)
    assert dashboard_app._run_state["running"] is False


def test_lan_run_full_still_rejects_missing_token(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "SETTINGS", dataclasses.replace(SETTINGS, lan_access=True))
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    response = client.post(
        "/api/run/full",
        headers={"Host": "192.168.1.50", "Origin": "https://192.168.1.50:5001"},
        environ_overrides={"REMOTE_ADDR": "192.168.1.22"},
    )
    assert response.status_code == 403
    assert "Reload Whisper" in response.get_json()["error"]


def test_worker_status_and_cancel_endpoint(client, env):
    from transcript_pipeline.dashboard import app as dashboard_app

    status = client.get("/api/status").get_json()["worker"]
    assert status["state"] == "STOPPED"
    assert {"pending_jobs", "active_jobs", "concurrency_limit", "next_scan", "last_scan"} <= set(status)
    worker = dashboard_app._get_processing_worker()
    job = worker.store.enqueue("full")
    response = client.post(f"/api/worker/jobs/{job['id']}/cancel", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.get_json()["state"] == "CANCELLED"
    repeated = client.post(f"/api/worker/jobs/{job['id']}/cancel", headers=AUTH_HEADERS)
    assert repeated.status_code == 200
    assert repeated.get_json()["state"] == "CANCELLED"


def test_status_uses_shared_active_queue_for_running_and_cancel_requested(client, env, monkeypatch):
    from transcript_pipeline.dashboard import app as dashboard_app

    monkeypatch.setitem(dashboard_app._run_state, "running", False)
    monkeypatch.setitem(dashboard_app._run_state, "mode", None)
    monkeypatch.setitem(dashboard_app._run_state, "started_at", None)
    monkeypatch.setitem(dashboard_app._run_state, "stage", None)
    worker = dashboard_app._get_processing_worker()
    queued = worker.store.enqueue("full")
    claimed = worker.store.claim_next(1)
    assert claimed["id"] == queued["id"]

    active = client.get("/api/status").get_json()
    assert active["running"] is True
    assert active["mode"] == "full"
    assert active["started_at"] == claimed["started_at"]
    assert active["worker"]["active_jobs"] == 1

    assert worker.store.cancel(queued["id"])
    cancelling = client.get("/api/status").get_json()
    assert cancelling["running"] is True
    assert cancelling["worker"]["active_jobs"] == 1

    worker.store.finish(queued["id"], "CANCELLED")


def test_dashboard_token_is_shared_across_process_restarts(tmp_path):
    first = dashboard_app._load_dashboard_token(tmp_path)
    second = dashboard_app._load_dashboard_token(tmp_path)
    assert first == second
    assert len(first) >= 32


def test_unrelated_host_still_rejected_with_lan_allowlist(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    assert client.get("/api/status", headers={"Host": "evil.example.com"}).status_code == 403


# ── Origin allowlist (mutating methods) ───────────────────────────────────

def test_lan_origin_accepted_with_token(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "LAN"}},
        headers={**AUTH_HEADERS, "Origin": "http://192.168.1.50:5001"},
    )
    assert resp.status_code == 200, resp.get_json()


def test_lan_origin_rejected_without_allowlist(client):
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "LAN"}},
        headers={**AUTH_HEADERS, "Origin": "http://192.168.1.50:5001"},
    )
    assert resp.status_code == 403


def test_lan_host_still_requires_token_for_mutations(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "LAN"}},
        headers={"Host": "192.168.1.50"},
    )
    assert resp.status_code == 403


# ── Backend health ────────────────────────────────────────────────────────

def test_health_reports_online(client):
    data = client.get("/api/health").get_json()
    assert data["ok"] is True
    assert data["status"] == "ONLINE"


def test_health_available_from_lan_host(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_LAN_HOST_ALLOWLIST", {"192.168.1.50"})
    data = client.get("/api/health", headers={"Host": "192.168.1.50"}).get_json()
    assert data["status"] == "ONLINE"


# ── Advertised LAN URLs ───────────────────────────────────────────────────

def test_network_reports_disabled_by_default(client):
    data = client.get("/api/network").get_json()
    assert data["lan_access"] is False
    assert data["urls"] == []


def test_network_builds_lan_urls_without_loopback(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "SETTINGS",
        dataclasses.replace(SETTINGS, lan_access=True, lan_hosts=("whisper.local",), dashboard_port=5001),
    )
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: ["192.168.1.50"])
    data = client.get("/api/network").get_json()
    assert data["lan_access"] is True
    assert "https://whisper.local:5001/" in data["urls"] or "http://whisper.local:5001/" in data["urls"]
    assert "http://192.168.1.50:5001/" in data["urls"]
    for url in data["urls"]:
        assert "localhost" not in url and "127.0.0.1" not in url


# ── main(): bind + HTTPS wiring ───────────────────────────────────────────

def _capture_app_run(monkeypatch, settings):
    captured: dict = {}
    monkeypatch.setattr(dashboard_app, "SETTINGS", settings)
    monkeypatch.setattr(dashboard_app, "_ensure_folders", lambda: None)
    monkeypatch.setattr(dashboard_app.app, "run", lambda **kwargs: captured.update(kwargs))
    dashboard_app.main()
    return captured


def test_main_binds_loopback_when_lan_off(monkeypatch):
    captured = _capture_app_run(monkeypatch, dataclasses.replace(
        SETTINGS, lan_access=False, dashboard_cert_file=None, dashboard_key_file=None,
    ))
    assert captured["host"] == SETTINGS.dashboard_host
    assert captured["ssl_context"] is None


def test_main_binds_wildcard_when_lan_on(monkeypatch):
    captured = _capture_app_run(monkeypatch, dataclasses.replace(SETTINGS, lan_access=True))
    assert captured["host"] == "0.0.0.0"


def test_main_passes_ssl_context_when_cert_configured(monkeypatch, tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    settings = dataclasses.replace(
        SETTINGS, lan_access=True, dashboard_cert_file=cert, dashboard_key_file=key
    )
    captured = _capture_app_run(monkeypatch, settings)
    assert captured["ssl_context"] == (str(cert), str(key))
