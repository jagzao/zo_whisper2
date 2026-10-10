from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import summarize_gates


def test_summary_aggregates_pass_fail_and_skipped_compact_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_NUMBER", "42")
    monkeypatch.setenv("BUILD_URL", "https://jenkins.example/job/zmi/42/")
    reports = [
        {"gate": "targeted", "status": "PASS", "check": "targeted", "artifact": "logs/targeted.log"},
        {"gate": "docker-build", "status": "FAIL", "check": "image", "error_signature": "build failed", "command": "docker build"},
        {"gate": "docker-e2e", "status": "SKIPPED", "check": "docker service unavailable", "error_signature": ""},
    ]
    for report in reports:
        (tmp_path / f"{report['gate']}.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "verbose.log").write_text("must never be read", encoding="utf-8")

    summary = summarize_gates.summarize(tmp_path, email_status="NOT_CONFIGURED")

    assert summary["status"] == "FAIL"
    assert summary["build_number"] == "42"
    assert summary["build_url"] == "https://jenkins.example/job/zmi/42/"
    assert summary["email_status"] == "NOT_CONFIGURED"
    statuses = {item["gate"]: item["status"] for item in summary["gates"]}
    assert statuses["targeted"] == "PASS"
    assert statuses["docker-build"] == "FAIL"
    assert statuses["docker-e2e"] == "SKIPPED"
    assert statuses["security"] == "SKIPPED"
    markdown = summarize_gates.render_markdown(summary)
    assert "build failed" in markdown
    assert "docker service unavailable" in markdown


def test_summary_passes_when_gates_pass_or_skip(tmp_path):
    for gate in summarize_gates.REQUIRED_GATES:
        (tmp_path / f"{gate}.json").write_text(
            json.dumps({"gate": gate, "status": "PASS"}), encoding="utf-8"
        )
    for gate, status in (("sonarqube", "NOT_CONFIGURED"), ("docker-e2e-soak", "SKIPPED")):
        (tmp_path / f"{gate}.json").write_text(
            json.dumps({"gate": gate, "status": status}), encoding="utf-8"
        )

    summary = summarize_gates.summarize(tmp_path)

    assert summary["status"] == "PASS"
    assert len(summary["gates"]) == len(summarize_gates.REQUIRED_GATES) + 2


def test_summary_marks_missing_required_gates_as_skipped_and_failing(tmp_path):
    (tmp_path / "targeted.json").write_text(
        json.dumps({"gate": "targeted", "status": "PASS"}), encoding="utf-8"
    )
    summary = summarize_gates.summarize(tmp_path)

    assert summary["status"] == "FAIL"
    missing = next(item for item in summary["gates"] if item["gate"] == "docker-build")
    assert missing["status"] == "SKIPPED"
    assert missing["check"] == "required gate report missing"
