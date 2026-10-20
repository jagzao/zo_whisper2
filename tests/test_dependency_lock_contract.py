from __future__ import annotations

import re
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
DEV_LOCK = ROOT / "requirements.lock.txt"
RUNTIME_LOCK = ROOT / "requirements.runtime.lock.txt"


def _pins(text: str) -> dict[str, str]:
    return {name.lower(): version for name, version in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s]+)", text, re.MULTILINE)}


def _block(text: str, package: str) -> str:
    match = re.search(rf"^{re.escape(package)}==[^\n]*\n((?:[ \t]+[^\n]*\n)*)", text, re.MULTILINE | re.IGNORECASE)
    assert match is not None, f"missing lock entry: {package}"
    return match.group(1)


def test_dev_lock_contains_secure_target_versions_and_narrow_markitdown_extra():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = DEV_LOCK.read_text(encoding="utf-8")
    pins = _pins(lock)

    assert 'markitdown[docx,pptx,xls,xlsx,pdf]==0.1.8' in pyproject
    assert pins["markitdown"] == "0.1.8"
    assert Version(pins["httpx2"]) >= Version("2.12.0")
    assert Version(pins["urllib3"]) >= Version("2.8.0")
    assert Version(pins["werkzeug"]) >= Version("3.1.9")
    assert "azure-ai-documentintelligence" not in pins
    assert "azure-identity" not in pins
    assert "msal" not in pins
    assert "pyjwt" not in pins


def test_dev_lock_reverse_dependency_chains_are_expected():
    lock = DEV_LOCK.read_text(encoding="utf-8")
    assert "openai" in _block(lock, "httpx2")
    assert "requests" in _block(lock, "urllib3")
    assert "flask" in _block(lock, "werkzeug")


def test_runtime_lock_was_not_modified_by_dev_remediation():
    runtime = _pins(RUNTIME_LOCK.read_text(encoding="utf-8"))
    assert runtime["urllib3"] == "2.8.0"
    assert runtime["werkzeug"] == "3.1.9"
