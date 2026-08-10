"""Quality harness: syntax, import sanity, and optional ruff lint.

Run:
    python scripts/quality.py
"""
from __future__ import annotations

import importlib
import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "transcript_pipeline"
TESTS = ROOT / "tests"
REPORT_PATH = ROOT / "quality_report.json"

# Core modules that must import cleanly without heavy deps.
SANITY_MODULES = [
    "transcript_pipeline.config",
    "transcript_pipeline.projects",
    "transcript_pipeline.language",
    "transcript_pipeline.file_tracker",
]


def _log(report: list[dict], name: str, ok: bool, detail: str = "") -> None:
    report.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}" if detail else f"[{'PASS' if ok else 'FAIL'}] {name}")


def check_syntax(report: list[dict]) -> None:
    files = list(SRC.rglob("*.py")) + list(TESTS.rglob("*.py")) + [ROOT / "dashboard.py"]
    failures: list[str] = []
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as e:
            failures.append(f"{path.relative_to(ROOT)}: {e}")
    _log(report, "python_syntax", not failures, f"{len(files) - len(failures)}/{len(files)} OK")
    for failure in failures:
        _log(report, f"syntax_{failure.split(':')[0]}", False, failure)


def check_import_sanity(report: list[dict]) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    failures: list[str] = []
    for mod in SANITY_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:
            failures.append(f"{mod}: {e}")
    _log(report, "import_sanity", not failures, f"{len(SANITY_MODULES) - len(failures)}/{len(SANITY_MODULES)} OK")
    for failure in failures:
        _log(report, f"import_{failure.split(':')[0]}", False, failure)


def check_ruff(report: list[dict]) -> None:
    try:
        result = subprocess.run(
            ["ruff", "check", str(SRC), str(TESTS)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
        detail = result.stdout.strip() or "ruff clean"
    except FileNotFoundError:
        ok = True
        detail = "ruff not installed; skipped"
    except Exception as e:
        ok = False
        detail = str(e)
    _log(report, "ruff_lint", ok, detail)


def main() -> int:
    report: list[dict] = []
    check_syntax(report)
    check_import_sanity(report)
    check_ruff(report)
    ok = all(r["status"] == "PASS" for r in report)
    REPORT_PATH.write_text(json.dumps({"checks": report, "ok": ok}, indent=2), encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
