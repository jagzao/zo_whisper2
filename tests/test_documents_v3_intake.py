from transcript_pipeline.dashboard import app as dashboard_app


def test_documents_v3_routes_approved_candidate_pack_to_generic_learning_service(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "dashboard-test")
    dashboard_app.app.config.update(TESTING=True)
    from transcript_pipeline.knowledge import service_client

    seen = []
    monkeypatch.setattr(service_client, "submit_documents_v3", lambda pack, **kwargs: seen.append((pack, kwargs)) or {
        "eligible": 13, "excluded": 23, "result": {"status": "EVALUATED"}
    })
    payload = {
        "projectId": "synthetic-project",
        "sourceId": "session-41-adapter",
        "ownerContentUat": "PASS",
        "secondBrainReady": "PASS",
        "pack": {"canonical_facts": [{"canonical_fact": "Synthetic curated fact."}]},
    }
    with dashboard_app.app.test_client() as client:
        response = client.post(
            "/api/knowledge/documents-v3/intake",
            headers={"X-Local-Dashboard-Token": "dashboard-test"},
            json=payload,
        )
    assert response.status_code == 200
    assert response.json["eligible"] == 13
    assert response.json["excluded"] == 23
    assert seen[0][1]["project_id"] == "synthetic-project"
    assert seen[0][1]["owner_content_uat"] == "PASS"
