"""ZK-19, ZK-20 — K'ab explicit projectKey and safe project catalog."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.kab_ingest_utils import auth_headers, make_settings, make_store, session_payload
from transcript_pipeline.kab_ingest import validation
from transcript_pipeline.kab_ingest.errors import KabIngestValidationError
from transcript_pipeline.kab_ingest.server import (
    create_app,
    knowledge_project_catalog,
    resolve_project_config_by_key,
)


@pytest.fixture()
def client(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = make_store(tmp_path)
    app = create_app(settings, store=store, data_root=tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_zk19_explicit_project_key_persists_in_session(client):
    response = client.post(
        "/kab/v1/sessions",
        json=session_payload(projectKey="p-g"),
        headers=auth_headers(),
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["created"] is True
    assert body["session"]["projectKey"] == "p-g"

    # Idempotent re-create with the same projectKey.
    response = client.post(
        "/kab/v1/sessions",
        json=session_payload(projectKey="p-g"),
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.get_json()["session"]["projectKey"] == "p-g"


def test_zk19_legacy_session_without_project_key_still_works(client):
    response = client.post(
        "/kab/v1/sessions",
        json=session_payload(),
        headers=auth_headers(),
    )
    assert response.status_code == 201
    assert response.get_json()["session"]["projectKey"] is None


def test_zk19_conflicting_project_key_is_rejected(client):
    client.post("/kab/v1/sessions", json=session_payload(projectKey="p-g"), headers=auth_headers())
    response = client.post(
        "/kab/v1/sessions",
        json=session_payload(projectKey="other"),
        headers=auth_headers(),
    )
    assert response.status_code == 409


def test_project_key_validation_rules():
    assert validation.validate_project_key(None) is None
    assert validation.validate_project_key("p-g") == "p-g"
    assert validation.validate_project_key("  ") is None
    with pytest.raises(KabIngestValidationError):
        validation.validate_project_key("../etc/passwd")
    with pytest.raises(KabIngestValidationError):
        validation.validate_project_key("a" * 100)
    with pytest.raises(KabIngestValidationError):
        validation.validate_project_key(42)


def test_zk20_unresolvable_project_key_disables_publishing_only():
    # No projects.json in this environment context -> key resolves to nothing
    # and publishing is disabled, but processing metadata is unaffected.
    config = resolve_project_config_by_key("no-such-project")
    assert config is None
    config = resolve_project_config_by_key(None)
    assert config is None


def test_project_catalog_exposes_safe_fields_only(client, monkeypatch, tmp_path):
    catalog_projects = [
        {
            "name": "p-g",
            "output_path": "C:/secret/internal/path",
            "initial_prompt": "secret prompt",
            "second_brain": {
                "enabled": True,
                "project_id": "p-g",
                "domain": "second-brain/p-g",
                "scope": "PROJECT",
                "default_artifact_type": "KT",
                "default_actionability": "REFERENCE",
            },
        },
        {"name": "Legacy", "match": {}},  # no second_brain -> excluded
    ]
    monkeypatch.setattr(
        "transcript_pipeline.kab_ingest.server._load_knowledge_projects",
        lambda: catalog_projects,
    )

    response = client.get("/kab/v1/projects", headers=auth_headers())
    assert response.status_code == 200
    projects = response.get_json()["projects"]
    assert [p["key"] for p in projects] == ["p-g"]
    payload = str(projects)
    assert "secret prompt" not in payload
    assert "secret/internal" not in payload
    assert set(projects[0].keys()) == {"key", "displayName", "scopeDefault", "artifactTypeDefault"}


def test_project_catalog_requires_auth(client):
    response = client.get("/kab/v1/projects")
    assert response.status_code == 401


def test_knowledge_catalog_direct(monkeypatch):
    monkeypatch.setattr(
        "transcript_pipeline.kab_ingest.server._load_knowledge_projects",
        lambda: [
            {
                "name": "tutorials",
                "second_brain": {"enabled": True, "scope": "GLOBAL", "default_artifact_type": "TUTORIAL"},
            }
        ],
    )
    catalog = knowledge_project_catalog()
    assert catalog == [
        {
            "key": "tutorials",
            "displayName": "tutorials",
            "scopeDefault": "GLOBAL",
            "artifactTypeDefault": "TUTORIAL",
        }
    ]
    assert resolve_project_config_by_key("tutorials")["name"] == "tutorials"
