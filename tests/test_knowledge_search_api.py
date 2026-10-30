from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.knowledge.second_brain import search_knowledge


def test_search_api_requires_service_token_and_keeps_provider_details_private(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setenv("ZAVI_KNOWLEDGE_INTAKE_TOKEN", "service-test")
    dashboard_app.app.config.update(TESTING=True)
    from transcript_pipeline.knowledge import second_brain

    monkeypatch.setattr(second_brain, "search_knowledge", lambda *args, **kwargs: {
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
        response = client.post("/api/knowledge/search", headers={"Authorization": "Bearer service-test"}, json=body)
        assert response.status_code == 200
        result = response.json["results"][0]
        assert result["applicationId"] == "app1"
        assert result["provenanceRefs"] == [{"id": "e1"}]
        assert result["currentLiveValidationRequired"] is True
        assert "gemini" not in str(response.json).lower()


def test_search_api_rejects_invalid_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setenv("ZAVI_KNOWLEDGE_INTAKE_TOKEN", "service-test")
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        response = client.post("/api/knowledge/search", headers={"Authorization": "Bearer service-test"},
                               json={"projectId": "p1", "question": "What?", "topK": 500})
        assert response.status_code == 400


def test_search_service_embeds_query_and_applies_application_topic_scope():
    class Store:
        def register_embedding_space(self):
            return "space-id"

        def search_vectors(self, **kwargs):
            assert kwargs["project_id"] == "p1"
            assert kwargs["top_k"] == 100
            return [{"id": "c1", "score": 0.94}, {"id": "c2", "score": 0.91}]

        def list_project_chunks(self, project_id):
            return [
                {"id": "c1", "project_id": project_id, "content": "Uses SSO.", "topic": "authentication",
                 "metadata": {"applicationId": "app1", "application": "Synthetic App", "knowledgeId": "k1",
                              "verificationStatus": "HUMAN_REVIEWED", "provenanceRefs": [{"id": "e1"}]}},
                {"id": "c2", "project_id": project_id, "content": "Uses LDAP.", "topic": "authentication",
                 "metadata": {"applicationId": "app2", "application": "Other App", "knowledgeId": "k2"}},
            ]

    class Provider:
        def embed(self, inputs):
            assert inputs == ["task: question answering | query: who authenticates?"]
            import math

            from transcript_pipeline.knowledge.second_brain import DIMENSIONS
            return [[1 / math.sqrt(DIMENSIONS)] * DIMENSIONS]

    result = search_knowledge("p1", "who authenticates?", application_id="app1",
                              topic="authentication", store=Store(), provider=Provider())
    assert result["semantic"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["knowledgeId"] == "k1"
    assert result["results"][0]["provenanceRefs"] == [{"id": "e1"}]
