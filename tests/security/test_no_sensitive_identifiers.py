"""Regression guard for the private-denylist check in
`scripts/security.py::check_no_denylisted_identifiers`.

The real denylist (client names, personal paths, project codenames) never
lives in this repo — see `_load_private_denylist`'s docstring. These tests
never use a real value, only synthetic sentinels, so this file itself can
never become the leak it exists to prevent.
"""

import json

from scripts.security import check_denylisted_identifiers_in_history, check_no_denylisted_identifiers


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


def _fake_git_subprocess(log_diff: str = "", log_messages: str = ""):
    """Returns a stub for `scripts.security.subprocess.run` that answers the
    three git invocations used by `check_denylisted_identifiers_in_history`
    (shallow check, `git log -p`, and commit-message log), dispatching on the
    command args so the real history is never touched."""

    def _run(args, **kwargs):
        if args[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
            return type("R", (), {"returncode": 0, "stdout": "false\n"})()
        if args[:3] == ["git", "log", "--all"]:
            if "--format=%s%n%b" in args:
                return type("R", (), {"returncode": 0, "stdout": log_messages})()
            return type("R", (), {"returncode": 0, "stdout": log_diff})()
        raise AssertionError(f"unexpected git invocation: {args}")

    return _run


def test_history_check_detects_token_in_commit_message(monkeypatch):
    monkeypatch.setattr("scripts.security._load_private_denylist", lambda: ({"test_client_secret"}, {}))
    monkeypatch.setattr(
        "scripts.security.subprocess.run",
        _fake_git_subprocess(
            log_diff="diff --git a/clean.md b/clean.md\nclean content\n",
            log_messages="Some subject mentioning TEST_CLIENT_SECRET\n",
        ),
    )

    report: list[dict] = []
    check_denylisted_identifiers_in_history(report)

    assert any(r["status"] == "FAIL" for r in report)
    assert any("commit message" in r.get("detail", "") for r in report)


def test_history_check_passes_when_token_in_neither_diff_nor_message(monkeypatch):
    monkeypatch.setattr("scripts.security._load_private_denylist", lambda: ({"test_client_secret"}, {}))
    monkeypatch.setattr(
        "scripts.security.subprocess.run",
        _fake_git_subprocess(
            log_diff="diff --git a/clean.md b/clean.md\nclean content\n",
            log_messages="Some clean subject\n",
        ),
    )

    report: list[dict] = []
    check_denylisted_identifiers_in_history(report)

    assert all(r["status"] == "PASS" for r in report)


def test_history_check_detects_token_in_diff(monkeypatch):
    monkeypatch.setattr("scripts.security._load_private_denylist", lambda: ({"test_client_secret"}, {}))
    monkeypatch.setattr(
        "scripts.security.subprocess.run",
        _fake_git_subprocess(
            log_diff="diff --git a/leaky.md b/leaky.md\n+added TEST_CLIENT_SECRET line\n",
            log_messages="Some clean subject\n",
        ),
    )

    report: list[dict] = []
    check_denylisted_identifiers_in_history(report)

    assert any(r["status"] == "FAIL" for r in report)


def test_history_check_skipped_cleanly_when_no_private_denylist(monkeypatch):
    """A public clone/fork with no .sensitive-identifiers and no
    SENSITIVE_IDENTIFIERS secret must not fail the history check."""
    monkeypatch.setattr("scripts.security._load_private_denylist", lambda: None)

    report: list[dict] = []
    check_denylisted_identifiers_in_history(report)

    assert len(report) == 1
    assert report[0]["status"] == "PASS"
    assert "SKIPPED" in report[0]["detail"]
