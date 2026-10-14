"""Run bounded, deterministic Documentation V2 implementation gates."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "gates"

TESTS = {
    "A": ["tests/test_documentation_v2_modes_evidence.py", "tests/test_documentation_v2_compaction.py"],
    "B": ["tests/test_documentation_v2_synthesis_grounding.py"],
    "C": ["tests/test_documentation_v2_screenshots.py", "tests/test_documentation_v2_manual_package.py"],
    "D": ["tests/test_documentation_v2_knowledge_bridge.py"],
    "E": ["tests/test_documentation_v2_regenerate_review.py", "tests/test_documentation_v2_fixtures.py"],
}
SOURCE = [
    "src/transcript_pipeline/documentation",
    "src/transcript_pipeline/knowledge/package_builder.py",
    "src/transcript_pipeline/projects.py",
    "src/transcript_pipeline/dashboard/app.py",
    "src/transcript_pipeline/llm/openai_compatible.py",
    "scripts/docs_v2_fast_ci.py",
]


def run_check(name: str, command: list[str], log_dir: Path) -> dict:
    started = time.monotonic()
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        output = f"$ {' '.join(command)}\n{result.stdout or ''}\n{result.stderr or ''}"
        code = result.returncode
    except OSError as exc:
        output, code = f"{type(exc).__name__}: {exc}", 1
    log_path = log_dir / f"{name}.log"
    log_path.write_text(output, encoding="utf-8")
    return {
        "check": name,
        "status": "PASS" if code == 0 else "FAIL",
        "exit_code": code,
        "duration_seconds": round(time.monotonic() - started, 2),
        "log": log_path.relative_to(ROOT).as_posix(),
        "signature": "" if code == 0 else next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "failed"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slice", choices=TESTS)
    group.add_argument("--all-light", action="store_true")
    args = parser.parse_args(argv)

    selected = list(TESTS) if args.all_light else [args.slice]
    missing = [path for path in SOURCE if not (ROOT / path).exists()]
    missing += [path for letter in selected for path in TESTS[letter] if not (ROOT / path).is_file()]
    if missing:
        print(json.dumps({"status": "CONFIG_ERROR", "missing": missing}))
        return 2

    label = "all-light" if args.all_light else f"slice-{args.slice}"
    log_dir = ARTIFACTS / "docs-v2" / label
    log_dir.mkdir(parents=True, exist_ok=True)
    tests = [path for letter in selected for path in TESTS[letter]]
    if args.all_light:
        tests += ["tests/test_projects.py", "tests/test_documentation_engine.py"]
    checks = {
        "pytest": [sys.executable, "-m", "pytest", *tests, "-q"],
        "compile": [sys.executable, "-m", "compileall", "-q", *SOURCE],
        "ruff": [sys.executable, "-m", "ruff", "check", *SOURCE],
        "pyright": [sys.executable, "-m", "pyright", "--project", "pyproject.toml", *SOURCE],
    }
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(checks)))) as pool:
        results = list(pool.map(lambda item: run_check(item[0], item[1], log_dir), checks.items()))
    summary = {
        "status": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL",
        "slice": label,
        "checks": results,
        "duration_seconds": round(time.monotonic() - started, 2),
        "workers": min(4, len(checks)),
        "llm": False,
        "real_media": False,
    }
    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "slice": label, "duration_seconds": summary["duration_seconds"], "checks": [{"check": item["check"], "status": item["status"], "signature": item["signature"]} for item in results], "summary": summary_path.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
