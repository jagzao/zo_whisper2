"""Rebrand guard: no public-facing tracked text file may still say
"Zo Whisper Studio" — the product is now "Zo Media Intelligence".

Scans `git ls-files` (tracked files only) and greps each text file for the
old brand. Exclusions, documented:

- `.agents/` — internal agent memory/deliverables, not public-facing.
- Binary assets (`*.png`, `*.mp4`, ...) — not text.
- `tests/security/test_dashboard_local_only.py` — `C_Dev_Zo_whisper_internal`
  is a synthetic path-traversal payload, not branding.
- `zo_whisper2` (the GitHub repo URL in CI badges) — the repo is renamed
  later, after merge; the badge URL must keep working until then.

CHANGELOG.md is intentionally NOT excluded: its historical 1.1.0 entries
were updated to the new name, so the strict check applies there too.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from transcript_pipeline.config import PROJECT_ROOT

OLD_BRAND_PATTERNS = (
    "Zo Whisper Studio",
    "zo_whisper_studio",
    "ZO WHISPER",
    "zo-whisper-studio",
)

# Synthetic path-traversal payload in a security test — not branding.
ALLOWED_SECURITY_TEST = "tests/security/test_dashboard_local_only.py"

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".mp4", ".mkv", ".mov", ".webm", ".avi",
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus",
    ".pdf", ".zip", ".gz", ".lock", ".woff", ".woff2", ".ttf",
}


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True
    )
    return [PROJECT_ROOT / line for line in result.stdout.splitlines() if line.strip()]


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return False
    if ".agents" in path.parts:
        return False
    return True


def test_no_public_facing_file_mentions_old_brand():
    offenders: list[str] = []
    for path in _tracked_files():
        if not _is_text_file(path):
            continue
        if path.relative_to(PROJECT_ROOT).as_posix() == ALLOWED_SECURITY_TEST:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in OLD_BRAND_PATTERNS:
            if pattern in content:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {pattern!r}")
    assert not offenders, (
        "Old brand still present in public-facing files:\n" + "\n".join(offenders)
    )