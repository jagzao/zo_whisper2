"""Explicit bridge to the "shared kernel" in watcher/core.

watcher/ ships real functionality the daily pipeline reuses (keyframe
extraction, timestamp formatting, provider-agnostic LLM client, language
utilities). It isn't a separate microservice for that code: it's a shared
library, so instead of scattering `sys.path.insert(...)` across every
module that needs it (as the original script did), this is the single
point that exposes the boundary.

watcher/ has no `__init__.py` at any level — they're implicit Python 3
namespace packages, so having PROJECT_ROOT on sys.path is enough to
`import watcher.core...`.
"""

from __future__ import annotations

import sys

from transcript_pipeline.config import PROJECT_ROOT

_bootstrapped = False


def ensure_watcher_importable() -> bool:
    """Adds PROJECT_ROOT to sys.path if needed. Returns True if watcher/ exists."""
    global _bootstrapped
    watcher_dir = PROJECT_ROOT / "watcher"
    if not watcher_dir.is_dir():
        return False
    if not _bootstrapped:
        root_str = str(PROJECT_ROOT)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        _bootstrapped = True
    return True
