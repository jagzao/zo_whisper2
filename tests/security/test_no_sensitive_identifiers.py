"""Regression guard for docs/GIT_HISTORY_CLEANUP.md: it previously re-leaked
the exact real-world strings (client name, personal path, project codename)
it was meant to help redact from history. This test both verifies the real
repo is currently clean, and proves the checker actually catches a leak.
"""

from unittest.mock import patch

from scripts.security import check_no_denylisted_identifiers


def test_repo_has_no_denylisted_identifiers():
    report: list[dict] = []
    check_no_denylisted_identifiers(report)
    failures = [r for r in report if r["status"] == "FAIL"]
    assert not failures, failures


def test_checker_fails_on_a_denylisted_string(tmp_path):
    leaky = tmp_path / "leaky.md"
    leaky.write_text("Client codename: Valeris was our first customer.", encoding="utf-8")

    with patch("scripts.security._git_tracked_files", return_value=[leaky]):
        report: list[dict] = []
        check_no_denylisted_identifiers(report)

    assert any(r["status"] == "FAIL" for r in report)


def test_checker_allows_license_copyright_name(tmp_path):
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Copyright (c) 2026 Jagzao\n", encoding="utf-8")

    with patch("scripts.security._git_tracked_files", return_value=[license_file]):
        report: list[dict] = []
        check_no_denylisted_identifiers(report)

    assert all(r["status"] == "PASS" for r in report)


def test_checker_passes_on_clean_file(tmp_path):
    clean = tmp_path / "clean.md"
    clean.write_text("Client codename: Northwind is our synthetic example.", encoding="utf-8")

    with patch("scripts.security._git_tracked_files", return_value=[clean]):
        report: list[dict] = []
        check_no_denylisted_identifiers(report)

    assert all(r["status"] == "PASS" for r in report)
