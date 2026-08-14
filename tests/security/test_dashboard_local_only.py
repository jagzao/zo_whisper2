"""Dashboard is explicitly localhost-only: no Host/Origin/token checks
existed before this — any origin that could reach the bound port could
call any endpoint, including uploads/deletes/pipeline-run. Covers the
Host header check, Origin check for mutating methods, the per-process
token, and the fail-closed non-loopback DASHBOARD_HOST rejection at
Settings.from_env() time.
"""

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.settings import Settings

TOKEN = "test-dashboard-token"
AUTH_HEADERS = {"X-Local-Dashboard-Token": TOKEN}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", TOKEN)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


# ── Host header ───────────────────────────────────────────────────────────

def test_localhost_host_allowed(client):
    resp = client.get("/api/status", headers={"Host": "localhost"})
    assert resp.status_code == 200


def test_loopback_ip_host_allowed(client):
    resp = client.get("/api/status", headers={"Host": "127.0.0.1"})
    assert resp.status_code == 200


def test_non_local_host_rejected(client):
    resp = client.get("/api/status", headers={"Host": "evil.com"})
    assert resp.status_code == 403


def test_get_endpoints_unaffected_by_missing_token(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200


# ── Origin (mutating methods only) ───────────────────────────────────────

def test_external_origin_on_mutating_request_rejected(client):
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "X"}},
        headers={**AUTH_HEADERS, "Origin": "https://evil.com"},
    )
    assert resp.status_code == 403


def test_local_origin_on_mutating_request_allowed(client):
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "X"}},
        headers={**AUTH_HEADERS, "Origin": "http://127.0.0.1:5000"},
    )
    assert resp.status_code == 200


def test_no_origin_header_does_not_block_mutating_request(client):
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "Y"}},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200


# ── Per-process token ─────────────────────────────────────────────────────

def test_missing_token_on_mutating_request_rejected(client):
    resp = client.post("/api/projects", json={"action": "create", "project": {"name": "Z"}})
    assert resp.status_code == 403


def test_invalid_token_on_mutating_request_rejected(client):
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "Z"}},
        headers={"X-Local-Dashboard-Token": "wrong-token"},
    )
    assert resp.status_code == 403


def test_valid_token_on_mutating_request_allowed(client):
    resp = client.post(
        "/api/projects",
        json={"action": "create", "project": {"name": "Valid"}},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200


# ── Sanitized error responses ────────────────────────────────────────────

def test_transcription_read_error_does_not_leak_exception_text(client, monkeypatch, tmp_path):
    sensitive_path = tmp_path / "C_Dev_Zo_whisper_internal" / "secret_stem.txt"
    monkeypatch.setattr(dashboard_app, "_from_media_id", lambda *a, **k: sensitive_path)

    resp = client.get("/api/transcription?id=transcriptions:x.txt")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 500
    assert "secret_stem" not in body
    assert str(tmp_path) not in body
    assert resp.get_json()["error"] == "Could not read transcription"


# ── Fail-closed non-loopback bind ────────────────────────────────────────

def test_non_loopback_dashboard_host_rejected(monkeypatch):
    monkeypatch.setattr("transcript_pipeline.settings.load_env", lambda: None)
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_loopback_dashboard_host_accepted(monkeypatch):
    monkeypatch.setattr("transcript_pipeline.settings.load_env", lambda: None)
    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    assert Settings.from_env().dashboard_host == "127.0.0.1"
