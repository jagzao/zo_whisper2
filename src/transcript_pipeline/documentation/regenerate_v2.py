"""Deterministic V2 regeneration entry point (SPEC §14, PLAN WP-15).

    python -m transcript_pipeline.documentation.regenerate_v2 <frames-dir>
        [--mode KT_SESSION] [--evidence-only] [--projects-config projects.json]
        [--project "Name"]

Rebuilds the Evidence Plane and (when allowed) the semantic manual/package
from ALREADY PERSISTED artifacts. It MUST NOT invoke:

- Whisper/faster-whisper (transcription);
- FFmpeg keyframe extraction;
- OCR (no build_steps with frames_dir, no pytesseract);
- vision frame description.

Proof mechanism: `regenerate_documentation_v2` accepts an optional
`upstream_guard` — a mapping of module-attr -> callable that replaces every
upstream entry point during the run. The default guard hard-fails the run if
any upstream call is attempted. Tests monkeypatch the upstream modules to
raise instead (DV2-40..43).

A no-provider dry regeneration (`--evidence-only` or no provider configured)
still rebuilds the Evidence Timeline from persisted evidence and returns a
typed status.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

GuardMap = dict[str, Callable[..., Any]]


class UpstreamWorkAttemptedError(RuntimeError):
    """Raised when a forbidden upstream call is attempted during V2
    regeneration (no-upstream-work guard)."""


def _deny(*args: Any, **kwargs: Any) -> Any:
    raise UpstreamWorkAttemptedError(
        "V2 regeneration must not invoke transcription/FFmpeg/OCR/vision."
    )


def default_upstream_guard() -> GuardMap:
    """The no-upstream-work guard: every upstream entry point becomes a
    hard failure if invoked. Installing it proves the regeneration path
    never calls them."""
    return {
        "transcript_pipeline.transcription.processor.SimpleScanProcessor.transcribe_file": _deny,
        "transcript_pipeline.media.keyframe_extractor.KeyframeExtractor.extract_keyframes": _deny,
        "transcript_pipeline.documentation.engine._ocr_text": _deny,
        "transcript_pipeline.documentation.engine._vision_description": _deny,
        "transcript_pipeline.llm.openai_compatible.OpenAICompatibleProvider.describe_frame": _deny,
    }


def install_upstream_guard(guard: GuardMap) -> list[tuple[Any, Any, str]]:
    """Monkeypatches each guard entry onto already-imported modules; returns
    the undo records. Modules not currently imported are skipped — they
    cannot be invoked by a path that never imports them."""
    undos: list[tuple[Any, Any, str]] = []
    for dotted, replacement in guard.items():
        module_name, _, rest = dotted.rpartition(".")
        obj = sys.modules.get(module_name)
        if obj is None:
            continue
        if "." in rest:
            parent_name, _, attr = rest.rpartition(".")
            parent = getattr(obj, parent_name, None)
            if parent is None:
                continue
        else:
            parent = obj
            attr = rest
        original = getattr(parent, attr, None)
        undos.append((parent, original, attr))
        setattr(parent, attr, replacement)
    return undos


def undo_guard(undos: list[tuple[Any, Any, str]]) -> None:
    for parent, original, attr in undos:
        setattr(parent, attr, original)


def regenerate_documentation_v2(
    frames_dir: Path,
    *,
    mode_override: str | None = None,
    evidence_only: bool = False,
    project_config: dict | None = None,
    synthesis_service: Any | None = None,
    no_upstream_guard: bool = False,
) -> dict[str, Any]:
    """Regenerates documentation from persisted artifacts only.

    With `no_upstream_guard=False` (default), the no-upstream-work guard is
    installed for the duration of the run: any attempt to invoke
    transcription/keyframe extraction/OCR/vision raises
    UpstreamWorkAttemptedError instead of silently doing heavy work.
    """
    from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2

    undos: list[tuple[Any, Any, str]] = []
    if not no_upstream_guard:
        # Install the guard on every guarded module that is already loaded;
        # the regeneration path itself never imports upstream workers, so a
        # module being absent from sys.modules is itself proof it cannot be
        # invoked here.
        undos = install_upstream_guard(default_upstream_guard())
    try:
        return generate_documentation_v2(
            frames_dir,
            _source_name(frames_dir),
            project_config=project_config,
            synthesis_service=synthesis_service,
            evidence_only=evidence_only,
            compatibility_bundles=True,
            mode_override=mode_override,
        )
    finally:
        undo_guard(undos)


def _source_name(frames_dir: Path) -> str:
    mapping_path = frames_dir / "frame_mapping.json"
    if mapping_path.exists():
        try:
            name = (json.loads(mapping_path.read_text(encoding="utf-8"))
                    .get("video_info", {}).get("name"))
            if name:
                return str(name)
        except (OSError, ValueError):
            pass
    return frames_dir.name


def _load_project_config(path: Path | None, project_name: str | None) -> dict | None:
    if path is None:
        return None
    from transcript_pipeline.projects import load_projects

    projects = load_projects(path)
    if project_name:
        for project in projects:
            if project.get("name") == project_name:
                return project
        return None
    return projects[0] if projects else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m transcript_pipeline.documentation.regenerate_v2",
        description=(
            "Regenerate Documentation Synthesis V2 outputs (Evidence Plane + "
            "semantic manual/package) from persisted artifacts WITHOUT any "
            "retranscription, keyframe extraction, OCR or vision calls."
        ),
    )
    parser.add_argument("frames_dir", help="already-processed frames directory (contains frame_mapping.json)")
    parser.add_argument("--mode", default=None, help="explicit DocumentationMode override (e.g. KT_SESSION)")
    parser.add_argument("--evidence-only", action="store_true", help="rebuild the Evidence Plane only, no synthesis")
    parser.add_argument("--projects-config", default=None, help="optional path to projects.json for project config")
    parser.add_argument("--project", default=None, help="project name inside projects-config")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    frames_dir = Path(args.frames_dir).resolve()
    if not frames_dir.is_dir():
        print(f"error: frames dir not found: {frames_dir}", file=sys.stderr)
        return 2

    project_config = _load_project_config(
        Path(args.projects_config) if args.projects_config else None, args.project
    )
    try:
        result = regenerate_documentation_v2(
            frames_dir,
            mode_override=args.mode,
            evidence_only=args.evidence_only,
            project_config=project_config,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except UpstreamWorkAttemptedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"status={result['status']} mode={result['mode']['mode']} "
            f"evidence_items={result['evidence']['item_count']} "
            f"semantic_ready={result['semantic']['ready']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
