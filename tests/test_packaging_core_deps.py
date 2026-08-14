"""Packaging guard: a plain `pip install .` (core dependencies only, no
extras) must never pull in the optional AI/vision/document stack. Those
belong exclusively in the `llm`/`vision`/`documents` extras (see
pyproject.toml) so a purely-local transcription install stays lightweight.

Reads pyproject.toml directly rather than doing a real clean-venv install —
fast enough to run in the normal pytest suite, and it's the declaration
(not a resolver's transitive closure) this guard cares about: someone
re-adding e.g. "openai" to [project.dependencies] should fail immediately.
"""

from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 — the project supports >=3.10

from transcript_pipeline.config import PROJECT_ROOT

FORBIDDEN_IN_CORE = {"openai", "markitdown", "pytesseract", "imagehash"}


def _core_dependency_names() -> set[str]:
    data = tomllib.loads(Path(PROJECT_ROOT, "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    names = set()
    for dep in deps:
        # e.g. "faster-whisper>=1.0.0" -> "faster-whisper"; normalize '-'/'_'.
        name = dep.split("[")[0]
        for sep in ("==", ">=", "<=", "~=", ">", "<", "!="):
            name = name.split(sep)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def test_core_dependencies_exclude_optional_ai_document_vision_stack():
    core_deps = _core_dependency_names()
    forbidden_hits = {name for name in FORBIDDEN_IN_CORE if name in core_deps}
    assert not forbidden_hits, (
        f"{forbidden_hits} found in [project.dependencies] — these belong in the "
        "llm/vision/documents optional-dependencies extras, not core."
    )
