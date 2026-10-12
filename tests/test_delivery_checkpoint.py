"""PLV5 delivery checkpoint tests (TEST-MATRIX PLV5-P01, P02, P05)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import delivery_checkpoint as dcp  # noqa: E402


@pytest.fixture()
def checkpoint_file(tmp_path: Path) -> Path:
    return tmp_path / "delivery-checkpoint.json"


def test_p01_atomic_write_survives_interrupted_temp_write(checkpoint_file: Path):
    dcp.update(checkpoint_file, branch="feat/x", repo="zo_whisper2", terminal_state=None)
    good_state = dcp.load(checkpoint_file)
    assert good_state["branch"] == "feat/x"

    # Simulate a power loss during the NEXT update: a stale partial temp file
    # is left behind, but the committed checkpoint stays complete JSON.
    stale_tmp = checkpoint_file.with_name(checkpoint_file.name + ".tmp99999")
    stale_tmp.write_text('{"branch": "feat/x", "work_packages": [ {"id": "WP-A"', encoding="utf-8")

    reloaded = dcp.load(checkpoint_file)
    assert reloaded == good_state
    stale_tmp.unlink()


def test_p02_resume_returns_first_incomplete_mechanical_step(checkpoint_file: Path):
    dcp.update(
        checkpoint_file,
        work_packages=[
            {"id": "WP-A", "status": "done"},
            {"id": "WP-B", "status": "in_progress"},
            {"id": "WP-C", "status": "pending"},
        ],
    )
    step = dcp.first_incomplete_step(dcp.load(checkpoint_file))
    assert step == {"id": "WP-B", "status": "in_progress"}

    dcp.set_work_package("WP-B", "done", checkpoint_file)
    step = dcp.first_incomplete_step(dcp.load(checkpoint_file))
    assert step == {"id": "WP-C", "status": "pending"}

    dcp.set_work_package("WP-C", "done", checkpoint_file)
    assert dcp.first_incomplete_step(dcp.load(checkpoint_file)) is None


def test_p03_checkpoint_has_no_planning_field(checkpoint_file: Path):
    payload = dcp.update(checkpoint_file, branch="feat/x")
    assert "replan" not in payload
    assert "new_plan" not in payload
    # Resume only continues mechanical work; the frozen contract is referenced,
    # never regenerated locally.
    dcp.update(checkpoint_file, frozen_contract=".agents/deliverables/PLAN-PLV5-low-token-workflow.md")
    assert dcp.load(checkpoint_file)["frozen_contract"].startswith(".agents/deliverables/")


def test_p05_branch_mismatch_fails_closed_with_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(dcp, "_git", lambda args: {
        ("branch", "--show-current"): "feat/wrong-branch",
        ("rev-parse", "origin/feat/right-branch"): "abc123",
        ("rev-parse", "HEAD"): "abc123",
        ("merge-base", "HEAD", "origin/feat/right-branch"): "abc123",
        ("status", "--porcelain"): "",
    }.get(tuple(args), ""))
    ok, evidence = dcp.verify("feat/right-branch")
    assert ok is False
    assert evidence["branch_mismatch"] is True
    assert evidence["verified"] is False


def test_p05_missing_frozen_contract_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dcp, "_git", lambda args: {
        ("branch", "--show-current"): "feat/right-branch",
        ("rev-parse", "origin/feat/right-branch"): "abc123",
        ("rev-parse", "HEAD"): "abc123",
        ("merge-base", "HEAD", "origin/feat/right-branch"): "abc123",
        ("status", "--porcelain"): "",
    }.get(tuple(args), ""))
    ok, evidence = dcp.verify("feat/right-branch", frozen_contract=".agents/deliverables/DOES-NOT-EXIST.md")
    assert ok is False
    assert evidence["frozen_contract_missing"] is True


def test_p04_update_never_touches_git_state(checkpoint_file: Path, monkeypatch: pytest.MonkeyPatch):
    def _no_git(args):
        raise AssertionError("checkpoint writes must not run git mutations")

    monkeypatch.setattr(dcp, "_git", _no_git)
    dcp.update(checkpoint_file, branch="feat/x")
    dcp.record_gate("unit", "PASS", checkpoint_file)
    assert dcp.load(checkpoint_file)["gates"] == [{"gate": "unit", "result": "PASS"}]
