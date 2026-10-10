"""Aggregate compact build gate reports without reading raw logs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES_ROOT = ROOT / "artifacts" / "gates"
REQUIRED_GATES = (
    "targeted", "pytest", "quality", "security", "docker-config", "docker-build", "e2e",
    "docker-smoke", "docker-persistence", "docker-asr-smoke", "docker-e2e",
)


def current_build_dir() -> Path:
    build = (os.environ.get("BUILD_NUMBER") or "local").strip()
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in build)[:80] or "local"
    return GATES_ROOT / f"build-{safe}"


def summarize(directory: Path, email_status: str = "NOT_CONFIGURED") -> dict:
    reports = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "SUMMARY.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("gate"), str):
            continue
        reports.append({
            "gate": data["gate"],
            "status": data.get("status", "FAIL"),
            "check": data.get("check", data["gate"]),
            "error_signature": str(data.get("error_signature", ""))[:500],
            "command": str(data.get("command", ""))[:500],
            "artifact": data.get("artifact", ""),
            "duration_seconds": data.get("duration_seconds"),
        })
    reported = {item["gate"] for item in reports}
    for gate in REQUIRED_GATES:
        if gate not in reported:
            reports.append({
                "gate": gate,
                "status": "SKIPPED",
                "check": "required gate report missing",
                "error_signature": "gate did not emit a compact report",
                "command": "",
                "artifact": "",
                "duration_seconds": None,
            })
    reports.sort(key=lambda item: item["gate"])
    summary = {
        "build_number": os.environ.get("BUILD_NUMBER", "local"),
        "build_url": os.environ.get("BUILD_URL", ""),
        "status": "FAIL" if not reports or any(item["status"] == "FAIL" for item in reports) or any(
            item["check"] == "required gate report missing" for item in reports
        ) else "PASS",
        "email_status": email_status,
        "gates": reports,
    }
    return summary


def render_markdown(summary: dict) -> str:
    rows = ["# US-ZMI-DKR-001 gate summary", "", f"Build: {summary['build_number']}"]
    if summary["build_url"]:
        rows.append(f"URL: {summary['build_url']}")
    rows.extend([f"Status: **{summary['status']}**", f"Email: {summary['email_status']}", "", "| Gate | Status | Check | Error | Artifact |", "|---|---|---|---|---|"])
    for item in summary["gates"]:
        error = item["error_signature"].replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {item['gate']} | {item['status']} | {item['check']} | {error} | {item['artifact']} |")
    if not summary["gates"]:
        rows.append("| (none) | SKIPPED | no compact gate reports | | |")
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=current_build_dir())
    parser.add_argument("--email-status", default="NOT_CONFIGURED")
    args = parser.parse_args()
    directory = args.directory if args.directory.is_absolute() else ROOT / args.directory
    summary = summarize(directory, args.email_status)
    json_text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    markdown = render_markdown(summary)
    GATES_ROOT.mkdir(parents=True, exist_ok=True)
    directory.mkdir(parents=True, exist_ok=True)
    (GATES_ROOT / "SUMMARY.json").write_text(json_text, encoding="utf-8")
    (GATES_ROOT / "SUMMARY.md").write_text(markdown, encoding="utf-8")
    (directory / "SUMMARY.json").write_text(json_text, encoding="utf-8")
    (directory / "SUMMARY.md").write_text(markdown, encoding="utf-8")
    print(f"Summary: {GATES_ROOT / 'SUMMARY.md'}")
    return 1 if summary["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
