"""Configuration-level regression tests for the deterministic delivery toolchain."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_jenkinsfile_contains_required_deterministic_stages():
    text = _read("Jenkinsfile")
    for stage in ("Targeted", "Quality", "Security", "Playwright", "SonarQube", "Full E2E"):
        assert f"stage('{stage}')" in text
    assert "scripts/gate_runner.py" in text
    assert "SONAR_STATUS=NOT_CONFIGURED" in text
    assert "archiveArtifacts" in text


def test_sonar_configuration_has_no_committed_credentials_or_fake_coverage():
    text = _read("sonar-project.properties")
    assert "sonar.sources=src/transcript_pipeline" in text
    assert "sonar.tests=tests" in text
    assert "sonar.token=" not in text
    assert "sonar.login=" not in text
    assert "coverageReportPaths" not in text
    assert "coverage.reportPaths" not in text


def test_public_pr_ci_uses_pull_request_not_pull_request_target():
    text = _read(".github/workflows/dashboard-ci.yml")
    assert "pull_request:" in text
    assert "pull_request_target:" not in text
    for job in ("quality:", "security:", "unit-tests:", "smoke:", "e2e:", "fresh-install:"):
        assert job in text


def test_secret_scan_fetches_full_history():
    text = _read(".github/workflows/secret-scan.yml")
    assert "gitleaks/gitleaks-action@v2" in text
    assert "fetch-depth: 0" in text


def test_web_product_does_not_gain_electron_dependency():
    pyproject = _read("pyproject.toml").lower()
    assert "electron" not in pyproject
