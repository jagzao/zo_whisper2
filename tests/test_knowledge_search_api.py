from transcript_pipeline.dashboard import app as dashboard_app


def test_search_api_requires_service_token_and_keeps_provider_details_private(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "dashboard-test")
    monkeypatch.setenv("KNOWLEDGE_SERVICE_URL", "https://knowledge.example.test")
    monkeypatch.setenv("KNOWLEDGE_SERVICE_TOKEN", "service-test")
    dashboard_app.app.config.update(TESTING=True)
    from transcript_pipeline.knowledge import service_client

    monkeypatch.setattr(service_client, "search_knowledge", lambda *args, **kwargs: {
        "results": [{"knowledgeId": "k1", "chunkId": "c1", "projectId": "p1",
                     "applicationId": "app1", "applicationName": "Synthetic App", "topic": "auth",
                     "canonicalKnowledge": "Uses SSO.", "content": "Uses SSO.", "score": 0.9,
                     "verificationStatus": "HUMAN_REVIEWED", "observedAt": "2026-10-29T10:00:00Z",
                     "currentLiveValidationRequired": True, "provenanceRefs": [{"id": "e1"}],
                     "sourceSessionIds": ["s1"]}],
        "semantic": True, "degraded": False,
    })
    with dashboard_app.app.test_client() as client:
        body = {"projectId": "p1", "question": "Who uses SSO?", "applicationId": "app1", "topK": 5}
        assert client.post("/api/knowledge/search", json=body).status_code == 403
        response = client.post("/api/knowledge/search", headers={"X-Local-Dashboard-Token": "dashboard-test"}, json=body)
        assert response.status_code == 200
        result = response.json["results"][0]
        assert result["applicationId"] == "app1"
        assert result["provenanceRefs"] == [{"id": "e1"}]
        assert result["currentLiveValidationRequired"] is True
        assert "gemini" not in str(response.json).lower()


def test_search_api_rejects_invalid_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "dashboard-test")
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        response = client.post("/api/knowledge/search", headers={"X-Local-Dashboard-Token": "dashboard-test"},
                               json={"projectId": "p1", "question": "What?", "topK": 500})
        assert response.status_code == 400\n