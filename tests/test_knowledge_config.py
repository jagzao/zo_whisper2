"""ZK-01..ZK-06 — second_brain project configuration validation."""
from __future__ import annotations

from transcript_pipeline.projects import validate_project


def _project(**overrides):
    base = {"name": "P&G", "match": {"prefix": ["pg_"]}}
    base.update(overrides)
    return base


def _sb(**overrides):
    base = {
        "enabled": True,
        "project_id": "p-g",
        "domain": "second-brain/p-g",
        "scope": "PROJECT",
        "default_artifact_type": "KT",
        "default_actionability": "REFERENCE",
        "publish_assets": False,
    }
    base.update(overrides)
    return base


def test_zk01_legacy_project_without_second_brain_is_valid_and_disabled():
    errors = validate_project(_project())
    assert errors == []
    from transcript_pipeline.knowledge.package_builder import resolve_second_brain

    assert resolve_second_brain(_project()) is None


def test_zk02_project_scope_with_id_and_domain_is_valid():
    errors = validate_project(_project(second_brain=_sb()))
    assert errors == []


def test_zk03_project_scope_missing_project_id_is_rejected():
    sb = _sb()
    del sb["project_id"]
    errors = validate_project(_project(second_brain=sb))
    assert any("project_id" in e for e in errors)


def test_zk04_global_public_tutorial_config_is_valid():
    errors = validate_project(
        _project(
            data_classification="public",
            second_brain=_sb(scope="GLOBAL", project_id=None),
        )
    )
    assert errors == []
    sb = _sb(scope="GLOBAL")
    del sb["project_id"]
    assert validate_project(_project(data_classification="public", second_brain=sb)) == []


def test_zk05_confidential_global_is_rejected():
    sb = _sb(scope="GLOBAL")
    errors = validate_project(_project(data_classification="confidential", second_brain=sb))
    assert any("GLOBAL" in e for e in errors)


def test_zk06_unknown_scope_actionability_type_are_rejected():
    errors = validate_project(_project(second_brain=_sb(scope="SOLAR")))
    assert any("scope" in e for e in errors)
    errors = validate_project(_project(second_brain=_sb(default_actionability="MAGIC")))
    assert any("default_actionability" in e for e in errors)
    errors = validate_project(_project(second_brain=_sb(default_artifact_type="NOVEL")))
    assert any("default_artifact_type" in e for e in errors)


def test_disabled_second_brain_skips_deep_validation():
    # enabled=false -> no project_id requirement; still enum-checked.
    errors = validate_project(_project(second_brain=_sb(enabled=False, project_id=None)))
    assert errors == []


def test_second_brain_must_be_object():
    errors = validate_project(_project(second_brain="yes"))
    assert any("second_brain" in e for e in errors)
