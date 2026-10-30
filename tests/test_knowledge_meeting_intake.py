from transcript_pipeline.dashboard import app as dashboard_app


def test_obsolete_whisper_meeting_learning_routes_are_retired(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "dashboard-test")
    dashboard_app.app.config.update(TESTING=True)
    headers = {"X-Local-Dashboard-Token": "dashboard-test"}
    with dashboard_app.app.test_client() as client:
        response = client.post("/api/knowledge/intake/meeting", headers=headers, json={})
        evaluation = client.post("/api/knowledge/intake/meeting/session-1/evaluate", headers=headers)
    assert response.status_code == 410
    assert evaluation.status_code == 410
    assert response.json["error"] == "meeting_learning_owned_by_knowledge_service"
