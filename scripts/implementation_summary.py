"""PLV5 implementation summary writer.

Deterministic writer for the compact delivery summary required at the end of
each implementation run:

- artifacts/delivery/implementation/SUMMARY.json
- artifacts/delivery/implementation/SUMMARY.md

Required fields (frozen):
contract id, branch, start SHA, end SHA, changed files, selected cheap model,
targeted unit result, lint result, typecheck/build result, blockers, terminal
state.

Raw logs are never embedded: any value that looks like a log dump is redacted
to a compact marker before writing (PLV5-T05).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "delivery" / "implementation"

REQUIRED_FIELDS: tuple[str, ...] = (
    "contract_id",
    "branch",
    "start_sha",
    "end_sha",
    "changed_files",
    "selected_model",
    "unit_result",
    "lint_result",
    "typecheck_result",
    "blockers",
    "terminal_state",
)

_LOG_MARKERS: tuple[str, ...] = (
    "Traceback (most recent call last)",
    "============================= failures =============================",
    "-----------------------------",
    "<stdout>",
    "<stderr>",
)
_MAX_VALUE_CHARS = 280
_REDACTED = "<redacted:raw-log>"


def sanitize(value: object) -> object:
    """Compact values only: truncate long strings, redact raw-log-looking text."""
    if isinstance(value, str):
        if any(marker in value for marker in _LOG_MARKERS):
            return _REDACTED
        if len(value) > _MAX_VALUE_CHARS:
            return value[:_MAX_VALUE_CHARS] + "...<truncated>"
        return value
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def build_summary(
    *,
    contract_id: str,
    branch: str,
    start_sha: str,
    end_sha: str,
    changed_files: list[str],
    selected_model: str,
    unit_result: str,
    lint_result: str,
    typecheck_result: str,
    blockers: list[str] | None = None,
    terminal_state: str,
) -> dict:
    payload = {
        "contract_id": contract_id,
        "branch": branch,
        "start_sha": start_sha,
        "end_sha": end_sha,
        "changed_files": changed_files,
        "selected_model": selected_model,
        "unit_result": unit_result,
        "lint_result": lint_result,
        "typecheck_result": typecheck_result,
        "blockers": blockers or [],
        "terminal_state": terminal_state,
    }
    return {key: sanitize(val) for key, val in payload.items()}


def write_summary(payload: dict, output_dir: Path | None = None) -> tuple[Path, Path]:
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "SUMMARY.json"
    md_path = out_dir / "SUMMARY.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Implementation Summary — {payload.get('contract_id', '')}", ""]
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        if isinstance(value, list):
            rendered = ", ".join(str(v) for v in value) if value else "none"
        else:
            rendered = str(value)
        lines.append(f"- **{field}**: {rendered}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="PLV5 implementation summary writer")
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--start-sha", required=True)
    parser.add_argument("--end-sha", required=True)
    parser.add_argument("--changed", action="append", default=[], help="changed file (repeatable)")
    parser.add_argument("--model", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--lint", required=True)
    parser.add_argument("--typecheck", required=True)
    parser.add_argument("--blocker", action="append", default=[])
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)

    payload = build_summary(
        contract_id=args.contract_id,
        branch=args.branch,
        start_sha=args.start_sha,
        end_sha=args.end_sha,
        changed_files=args.changed,
        selected_model=args.model,
        unit_result=args.unit,
        lint_result=args.lint,
        typecheck_result=args.typecheck,
        blockers=args.blocker,
        terminal_state=args.state,
    )
    json_path, _ = write_summary(payload)
    print(json.dumps({"written": str(json_path.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
