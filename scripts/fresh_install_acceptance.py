"""Fresh-environment acceptance for the documented product install.

Creates an isolated venv, installs the public [studio] extra, and runs the
browser-free product smoke harness with external LLM calls disabled.

Usage:
    python scripts/fresh_install_acceptance.py

Requires FFmpeg/ffprobe on PATH because the public smoke harness verifies the
real media dependency. Tesseract remains optional for installation; OCR
feature tests cover it separately when available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("[FAIL] FFmpeg/ffprobe must be available on PATH")
        return 2

    with tempfile.TemporaryDirectory(prefix="zmi-fresh-install-") as tmp:
        env_dir = Path(tmp) / "venv"
        print(f"[INFO] Creating isolated venv: {env_dir}")
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python = _venv_python(env_dir)

        install = subprocess.run(
            [str(python), "-m", "pip", "install", "-e", ".[studio]"],
            cwd=str(ROOT),
            check=False,
        )
        if install.returncode != 0:
            print("[FAIL] studio install failed")
            return install.returncode

        env = os.environ.copy()
        env["ALLOW_EXTERNAL_LLM"] = "false"
        smoke = subprocess.run(
            [str(python), str(ROOT / "scripts" / "smoke.py")],
            cwd=str(ROOT),
            env=env,
            check=False,
        )
        if smoke.returncode != 0:
            print("[FAIL] fresh-install smoke failed")
            return smoke.returncode

    print("[PASS] fresh [studio] install + smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
