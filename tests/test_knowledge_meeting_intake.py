from transcript_pipeline.dashboard import app as dashboard_app


def _package(**changes):
    package = {
        "schemaVersion": 1,
        "sessionId": "synthetic-session-1",
        "projectId": "synthetic-project",
        "meetingType": "WORK_MEETING",
        "startedAt": "2026-10-29T10:00:00Z",
        "endedAt": "2026-10-29T10:30:00Z",
        "utterances": [{"id": "u1", "text": "Synthetic only: service uses SSO."}],
        "evidenceRefs": [{"id": "u1"}],
    }
    package.update(changes)
    return package


def test_meeting_intake_is_authenticated_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "dashboard-test")
    monkeypatch.setenv("ZAVI_KNOWLEDGE_INTAKE_TOKEN", "service-test")
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        headers = {"Authorization": "Bearer service-test"}
        first = client.post("/api/knowledge/intake/meeting", headers=headers, json=_package())
        duplicate = client.post("/api/knowledge/intake/meeting", headers=headers, json=_package())
        changed = client.post(
            "/api/knowledge/intake/meeting", headers=headers,
            json=_package(utterances=[{"id": "u2", "text": "Changed synthetic evidence."}]),
        )
        assert first.status_code == 200
        assert first.json["status"] == "RECEIVED_PENDING_EVALUATION"
        assert duplicate.json["status"] == "DUPLICATE"
        assert changed.status_code == 409


def test_meeting_intake_rejects_missing_fields_and_dashboard_token(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setenv("ZAVI_KNOWLEDGE_INTAKE_TOKEN", "service-test")
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        assert client.post(
            "/api/knowledge/intake/meeting", headers={"Authorization": "Bearer wrong"}, json=_package()
        ).status_code == 403
        invalid = _package()
        del invalid["projectId"]
        assert client.post(
            "/api/knowledge/intake/meeting", headers={"Authorization": "Bearer service-test"}, json=invalid
        ).status_code == 400
