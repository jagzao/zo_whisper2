"""Regression guard for the private-denylist check in
`scripts/security.py::check_no_denylisted_identifiers`.

The real denylist (client names, personal paths, project codenames) never
lives in this repo — see `_load_private_denylist`'s docstring. These tests
never use a real value, only synthetic sentinels, so this file itself can
never become the leak it exists to prevent.
"""

import json

from scripts.security import check_no_denylisted_identifiers


def test_detects_synthetic_denylisted_string(tmp_path, monkeypatch):
    leaky = tmp_path / "leaky.md"
    leaky.write_text("Client codename: TEST_CLIENT_SECRET was our first customer.", encoding="utf-8")

    monkeypatch.setattr("scripts.security._git_tracked_files", lambda: [leaky])
    monkeypatch.setattr(
        "scripts.security._load_private_denylist",
        lambda: ({"test_client_secret"}, {}),
    )

    report: list[dict] = []
    check_no_denylisted_identifiers(report)

    assert any(r["status"] == "FAIL" for r in report)


def test_passes_on_clean_synthetic_file(tmp_path, monkeypatch):
    clean = tmp_path / "clean.md"
    clean.write_text("Client codename: Northwind / Contoso synthetic data.", encoding="utf-8")

    monkeypatch.setattr("scripts.security._git_tracked_files", lambda: [clean])
    monkeypatch.setattr(
        "scripts.security._load_private_denylist",
        lambda: ({"test_client_secret"}, {}),
    )

    report: list[dict] = []
    check_no_denylisted_identifiers(report)

    assert all(r["status"] == "PASS" for r in report)


def test_skipped_cleanly_when_no_private_denylist_configured(monkeypatch):
    """A public clone/fork with no .sensitive-identifiers and no
    SENSITIVE_IDENTIFIERS secret must not fail this check."""
    monkeypatch.setattr("scripts.security._load_private_denylist", lambda: None)

    report: list[dict] = []
    check_no_denylisted_identifiers(report)

    assert len(report) == 1
    assert report[0]["status"] == "PASS"
    assert "SKIPPED" in report[0]["detail"]


def test_per_file_allow_exception(tmp_path, monkeypatch):
    allowed_file = tmp_path / "LICENSE"
    allowed_file.write_text("Copyright (c) 2026 TestOwnerSentinel\n", encoding="utf-8")

    monkeypatch.setattr("scripts.security._git_tracked_files", lambda: [allowed_file])
    monkeypatch.setattr(
        "scripts.security._load_private_denylist",
        lambda: ({"testownersentinel"}, {"testownersentinel": {"LICENSE"}}),
    )

    report: list[dict] = []
    check_no_denylisted_identifiers(report)

    assert all(r["status"] == "PASS" for r in report)


def test_report_never_contains_the_matched_value(tmp_path, monkeypatch):
    leaky = tmp_path / "leaky.md"
    leaky.write_text("contains TEST_CLIENT_SECRET right here", encoding="utf-8")

    monkeypatch.setattr("scripts.security._git_tracked_files", lambda: [leaky])
    monkeypatch.setattr(
        "scripts.security._load_private_denylist",
        lambda: ({"test_client_secret"}, {}),
    )

    report: list[dict] = []
    check_no_denylisted_identifiers(report)

    serialized = json.dumps(report)
    assert "TEST_CLIENT_SECRET" not in serialized
    assert "test_client_secret" not in serialized


def test_real_repo_denylist_check_runs_without_error():
    """Sanity check against the actual repo state — does not assert a fixed
    pass/fail outcome, since public CI has no private denylist configured
    (that case is covered explicitly above) while a maintainer's local run
    does. Only asserts the check executes and reports something coherent."""
    report: list[dict] = []
    check_no_denylisted_identifiers(report)
    assert report
    assert report[0]["name"] == "no_denylisted_identifiers"
