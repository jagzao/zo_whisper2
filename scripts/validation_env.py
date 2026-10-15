"""Create and inspect the repository-local, lockfile-pinned validation env."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
LOCK_PATH = ROOT / "requirements.lock.txt"
ENV_PATH = ROOT / ".venv-validation"
STAMP_PATH = ENV_PATH / ".validation-fingerprint"


def python_path() -> Path:
    return ENV_PATH / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def fingerprint() -> str:
    digest = hashlib.sha256()
    digest.update(LOCK_PATH.read_bytes())
    digest.update(f"\0{sys.version_info.major}.{sys.version_info.minor}".encode("ascii"))
    return digest.hexdigest()


def status() -> dict[str, object]:
    expected = fingerprint()
    actual = STAMP_PATH.read_text(encoding="ascii").strip() if STAMP_PATH.is_file() else None
    return {
        "ready": python_path().is_file() and actual == expected,
        "python": str(python_path()),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "fingerprint_matches": actual == expected,
    }


def _running_inside_env() -> bool:
    try:
        return Path(sys.prefix).resolve() == ENV_PATH.resolve()
    except OSError:
        return False


def _write_stamp_atomic(value: str) -> None:
    temp = ENV_PATH / f".validation-fingerprint.tmp-{os.getpid()}"
    temp.write_text(value, encoding="ascii")
    os.replace(temp, STAMP_PATH)


def ensure() -> Path:
    current = status()
    if current["ready"]:
        return python_path()
    if _running_inside_env():
        raise RuntimeError("validation env is stale; run ensure with the base Python")
    if ENV_PATH.is_symlink():
        raise RuntimeError("refusing to replace a symlink validation env")
    if ENV_PATH.exists() and not ENV_PATH.is_dir():
        raise RuntimeError("validation env path is not a directory")

    venv.EnvBuilder(with_pip=True, clear=True).create(ENV_PATH)
    interpreter = python_path()
    subprocess.run(
        [str(interpreter), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(LOCK_PATH)],
        cwd=ROOT,
        check=True,
    )
    if not interpreter.is_file():
        raise RuntimeError("validation interpreter was not created")
    _write_stamp_atomic(fingerprint())
    return interpreter


def dependency_smoke() -> dict[str, str]:
    modules = ("pytest", "markitdown", "openpyxl", "pptx", "transcript_pipeline")
    versions: dict[str, str] = {}
    for name in modules:
        module = importlib.import_module(name)
        versions[name] = str(getattr(module, "__version__", "imported"))
    return versions


def ensure_playwright_chromium() -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
    if executable.is_file():
        return False
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode or not executable.is_file():
        raise RuntimeError("Playwright Chromium installation failed")
    return True


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else ""
    if command == "ensure":
        interpreter = ensure()
        print(json.dumps({"status": "ready", "python": str(interpreter), "fingerprint": fingerprint()}))
        return 0
    if command == "python":
        interpreter = python_path()
        if len(args) == 1:
            print(interpreter)
            return 0
        return subprocess.run([str(interpreter), *args[1:]], cwd=ROOT, check=False).returncode
    if command == "status":
        print(json.dumps(status()))
        return 0
    if command == "smoke":
        print(json.dumps({"status": "pass", "imports": dependency_smoke()}))
        return 0
    print("usage: validation_env.py {ensure|python|status|smoke}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
