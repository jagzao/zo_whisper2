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
    assert seen[0][1]["owner_content_uat"] == "PENDING"


def test_ready_documents_v3_generation_submits_with_owner_approval_pending(monkeypatch, tmp_path):
    from transcript_pipeline.documentation import production
    from transcript_pipeline.knowledge import service_client

    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "dashboard-test")
    target = tmp_path / "pg_media.mp4"
    frames_parent = tmp_path / "frames"
    evidence = frames_parent / "evidence" / "media-evidence-bundle.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "_from_media_id", lambda *_args: target)
    monkeypatch.setattr(dashboard_app, "_documentation_dirs", lambda _target: frames_parent)
    monkeypatch.setattr(dashboard_app, "_to_media_id", lambda *_args: "pg_media.mp4")
    monkeypatch.setattr(dashboard_app, "_effective_project", lambda *_args: ({"name": "P&G"}, "auto"))
    pack = {
        "quality_state": "READY", "quality_gates": {"QUALITY_GATE": "PASS"},
        "media_id": "pg_media.mp4", "canonical_facts": [], "applications": [],
    }
    monkeypatch.setattr(production, "run_session_pack", lambda *_args: {
        "status": "READY", "generation_state": "READY", "gates": {}, "paths": {}, "pack": pack,
    })
    sent = []
    monkeypatch.setattr(service_client, "submit_documents_v3", lambda pack, **kwargs:
                      sent.append((pack, kwargs)) or {"submitted": 1, "excluded": 0})

    with dashboard_app.app.test_client() as client:
        response = client.post("/api/documentation/v3/generate?id=synthetic",
                               headers={"X-Local-Dashboard-Token": "dashboard-test"})
    assert response.status_code == 200
    assert response.json["knowledge_submission"]["state"] == "SUBMITTED"
    assert sent[0][1]["project_id"] == "P&G"
    assert sent[0][1]["owner_content_uat"] == "PENDING"
    assert sent[0][1]["second_brain_ready"] == "PENDING"
