"""Security harness: secret scan, path-traversal review, and dependency audit.

Run:
    python scripts/security.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "security_report.json"

# Patterns that strongly suggest committed secrets.
SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style key"),
    (r"ntn_[a-zA-Z0-9]{20,}", "Notion integration token"),
    (r"gh[pousr]_[A-Za-z0-9_]{20,}", "GitHub token"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "private key"),
    (r"\bpassword\s*=\s*['\"][^'\"]{8,}['\"]", "hardcoded password (assignment)"),
    (r"\bapi[_-]?key\s*=\s*['\"][a-zA-Z0-9_-]{16,}['\"]", "hardcoded API key"),
    (r"\bsecret\s*=\s*['\"][a-zA-Z0-9_-]{16,}['\"]", "hardcoded secret"),
]

EXCLUDE_GLOBS = {
    "*.env.example",
    "*.png",
    "*.jpg",
    "*.mp4",
    "*.mp3",
    "*.pyc",
    "*.bat",
    "projects.json.example",
    "quality_report.json",
    "security_report.json",
    "dashboard_report.json",
    "harness_report.json",
    "ut_report.json",
    "e2e_report.json",
    # Deliberately contains synthetic secret-shaped fixtures (fake OpenAI/GitHub/AWS
    # key formats, including AWS's own public example key) to test redact_secrets()
    # — not real secrets. Same exemption is expressed for gitleaks in .gitleaks.toml.
    "test_llm_guard_and_redaction.py",
    "test_llm_enrichment.py",
}


def _log(report: list[dict], name: str, ok: bool, detail: str = "") -> None:
    report.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}" if detail else f"[{'PASS' if ok else 'FAIL'}] {name}")


def _git_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return []
    files: list[Path] = []
    for line in result.stdout.splitlines():
        path = ROOT / line.strip()
        if path.is_file():
            files.append(path)
    return files


def _should_scan(path: Path) -> bool:
    name = path.name
    for glob in EXCLUDE_GLOBS:
        if glob.startswith("*") and name.endswith(glob[1:]):
            return False
        if name == glob:
            return False
    return True


def check_committed_secrets(report: list[dict]) -> None:
    files = _git_tracked_files()
    hits: list[str] = []
    for path in files:
        if not _should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, label in SECRET_PATTERNS:
            for match in re.finditer(pattern, text):
                snippet = text[max(0, match.start() - 15):match.end() + 15].replace("\n", " ")
                hits.append(f"{path.relative_to(ROOT)} ({label}): ...{snippet}...")
    _log(report, "committed_secrets", not hits, f"{len(hits)} suspicious patterns")
    for hit in hits[:10]:
        _log(report, "secret_hit", False, hit)


def check_env_gitignored(report: list[dict]) -> None:
    try:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    except Exception as e:
        _log(report, "env_gitignored", False, f"cannot read .gitignore: {e}")
        return
    ok = all(line in gitignore for line in (".env", "*.env"))
    detail = ".env patterns present" if ok else "missing .env ignore rules"
    _log(report, "env_gitignored", ok, detail)


def check_path_traversal(report: list[dict]) -> None:
    """Runs the real security regression suite instead of grepping app.py for
    magic strings — a previous version of this check only verified that the
    literal text "target.resolve()" / "startswith(str(root_resolved))"
    appeared somewhere in app.py, which passed even though two endpoints
    (`/api/transcription` GET and POST) had no path guard at all. The actual
    boundary is `SafePathResolver`, exercised by `tests/security/`."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(ROOT / "tests" / "security"), "-q"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
        detail = (result.stdout + result.stderr).strip()[-2000:]
    except Exception as e:
        ok = False
        detail = str(e)
    _log(report, "path_traversal", ok, detail)


# The actual list of real-world identifiers to guard against (client names,
# personal path fragments, project codenames) lives OUTSIDE this repo —
# never as a tracked file. A tracked denylist of real values is itself a
# leak (that mistake is exactly what this rewrite fixes: an earlier version
# hardcoded the real values here and in the accompanying test).
#
# Configure it via either:
#   - a local, gitignored `.sensitive-identifiers` file (repo root), one
#     identifier per line — see `.sensitive-identifiers.example`; or
#   - a `SENSITIVE_IDENTIFIERS` env var (comma-separated), meant for a
#     private CI secret.
# Neither is required: public clones/forks and PR CI runs simply skip this
# specific check (logged clearly as SKIPPED, not a failure) since they have
# no private list to check against — the rest of the security harness
# (committed-secret patterns, gitleaks, path-traversal suite) still runs.

def _parse_denylist_entries(entries: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    """Parses raw entries into (denylist tokens, {token: {allowed filenames}}).

    Plain entry `token` -> denylisted everywhere. Entry `token>>filename`
    -> denylisted everywhere EXCEPT that exact tracked filename (a known,
    intentional exception — e.g. the repo owner's own name as LICENSE
    copyright holder or in a GitHub badge URL — not a leak). Kept out of
    tracked code entirely: stating "<real name> is allowed in LICENSE" as a
    Python dict here would itself re-embed the real value in a tracked
    file, which is the exact mistake this rewrite removes.
    """
    denylist: set[str] = set()
    allowed: dict[str, set[str]] = {}
    for raw in entries:
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if ">>" in entry:
            token, _, filename = entry.partition(">>")
            token = token.strip().lower()
            denylist.add(token)
            allowed.setdefault(token, set()).add(filename.strip())
        else:
            denylist.add(entry.lower())
    return denylist, allowed


def _load_private_denylist() -> tuple[set[str], dict[str, set[str]]] | None:
    """Returns (denylist, per-file allow-exceptions) from a local file or CI
    secret, or None if neither is configured (meaning: skip the check,
    don't fail on it — public clones/forks have no private list)."""
    import os

    env_value = os.getenv("SENSITIVE_IDENTIFIERS")
    if env_value:
        return _parse_denylist_entries(env_value.split(","))

    local_file = ROOT / ".sensitive-identifiers"
    if local_file.is_file():
        denylist, allowed = _parse_denylist_entries(local_file.read_text(encoding="utf-8").splitlines())
        if denylist:
            return denylist, allowed

    return None


def check_no_denylisted_identifiers(report: list[dict]) -> None:
    """Guards against real client names/paths/codenames reappearing in any
    tracked file — see docs/GIT_HISTORY_CLEANUP.md, which this check exists
    to keep honest. The denylist itself is never tracked (see
    `_load_private_denylist`), and a hit is never reported with the actual
    matched value — only the file it was found in — so this check can't
    itself become a leak."""
    loaded = _load_private_denylist()
    if loaded is None:
        _log(report, "no_denylisted_identifiers", True, "SKIPPED: no private denylist configured")
        return
    denylist, denylist_allowed = loaded

    files = _git_tracked_files()
    hits: list[str] = []
    for path in files:
        if not _should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        try:
            display_path = path.relative_to(ROOT)
        except ValueError:
            display_path = path
        for token in denylist:
            if path.name in denylist_allowed.get(token, set()):
                continue
            if token in text:
                hits.append(f"denylisted identifier found in {display_path}")
                break
    _log(report, "no_denylisted_identifiers", not hits, f"{len(hits)} hits")
    for hit in hits[:10]:
        _log(report, "denylisted_identifier_hit", False, hit)


def check_dependency_audit(report: list[dict]) -> None:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
        detail = (result.stdout + result.stderr).strip() or "pip audit clean"
    except FileNotFoundError:
        # pip-audit is a required dev dependency — its absence is a broken
        # environment, not a reason to report the gate as passing.
        ok = False
        detail = "pip-audit not installed — run `pip install -e '.[dev]'`"
    except Exception as e:
        ok = False
        detail = str(e)
    _log(report, "dependency_audit", ok, detail)


def main() -> int:
    report: list[dict] = []
    check_committed_secrets(report)
    check_env_gitignored(report)
    check_no_denylisted_identifiers(report)
    check_path_traversal(report)
    check_dependency_audit(report)
    ok = all(r["status"] == "PASS" for r in report)
    REPORT_PATH.write_text(json.dumps({"checks": report, "ok": ok}, indent=2), encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
