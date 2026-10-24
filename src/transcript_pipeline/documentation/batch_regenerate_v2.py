"""Resumable, local-first Docs V2 corpus inventory and regeneration."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcript_pipeline.config import AUDIO_DIR, DATA_ROOT, TRANSCRIPTIONS_DIR, VIDEOS_DIR
from transcript_pipeline.documentation.regenerate_v2 import regenerate_documentation_v2
from transcript_pipeline.documentation.versioning import generation_profile, regenerate_versioned
from transcript_pipeline.projects import load_projects, match_project

_MEDIA_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def _frames_dir(media: Path, media_root: Path) -> Path:
    relative = media.relative_to(media_root)
    return TRANSCRIPTIONS_DIR / relative.parent / f"{media.stem}_Frames" / media.stem


def _discover(projects: list[dict]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for root_name, media_root in (("videos", VIDEOS_DIR), ("audio", AUDIO_DIR)):
        if not media_root.is_dir():
            continue
        for media in sorted(media_root.rglob("*")):
            if not media.is_file() or media.suffix.lower() not in _MEDIA_EXTENSIONS:
                continue
            relative = media.relative_to(media_root)
            parts = {part.lower() for part in relative.parts}
            if root_name == "videos" and "live_capture" in parts and "final" not in parts:
                continue
            frames = _frames_dir(media, media_root)
            media_id = f"{root_name}:{relative.as_posix()}"
            project = match_project(media, projects)
            transcript_path = TRANSCRIPTIONS_DIR / relative.parent / f"{media.stem}.txt"
            segments_path = TRANSCRIPTIONS_DIR / relative.parent / f"{media.stem}_segments.json"
            transcript_available = transcript_path.is_file() or segments_path.is_file()
            mapping_path = frames / "frame_mapping.json"
            mapping = None
            mapping_invalid = False
            if mapping_path.is_file():
                try:
                    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
                    if not isinstance(mapping, dict):
                        mapping_invalid = True
                    else:
                        frame_list = mapping.get("frames")
                        if not isinstance(frame_list, list):
                            mapping_invalid = True
                        elif frame_list:
                            mapping_invalid = any(
                                not isinstance(frame, dict)
                                or not isinstance(frame.get("frame_file"), str)
                                or not (frames / frame["frame_file"]).is_file()
                                for frame in frame_list
                            )
                        summary = mapping.get("transcription_summary") or {}
                        mapped = mapping.get("transcription_mapping") or {}
                        transcript_available = transcript_available or bool(
                            str(summary.get("full_transcription") or "").strip()
                        ) or any(
                            bool(str(entry.get("full_text") or "").strip())
                            or bool(entry.get("transcription_segments"))
                            for entry in mapped.values() if isinstance(entry, dict)
                        )
                except (OSError, ValueError):
                    mapping_invalid = True
            if mapping_invalid:
                state = "INVALID_FRAME_MAPPING"
            elif not mapping or not mapping.get("frames"):
                state = "NEEDS_KEYFRAMES_ONLY" if transcript_available else "NEEDS_TRANSCRIPT_AND_KEYFRAMES"
            elif not transcript_available:
                state = "NEEDS_TRANSCRIPT"
            else:
                state = "READY"
            found.append({
                "media_id": media_id,
                "name": media.name,
                "frames_dir": str(frames),
                "project_name": project.get("name") if project else None,
                "transcript_available": transcript_available,
                "frame_mapping_available": (frames / "frame_mapping.json").is_file(),
                "state": state,
            })
    return found


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def run_batch(
    *, manifest_path: Path, inventory_only: bool = False, evidence_only: bool = False,
    mode_override: str | None = None, limit: int | None = None,
) -> dict[str, Any]:
    projects_path = DATA_ROOT / "projects.json"
    projects = load_projects(projects_path)
    projects_by_name = {project.get("name"): project for project in projects}
    items = _discover(projects)
    pg_docs_enabled = os.environ.get("PG_DOCUMENTS_V2_ENABLED", "false").strip().casefold() in {"1", "true", "yes"}
    if not pg_docs_enabled:
        for item in items:
            if item["project_name"] == "P&G":
                item["evidence_state"] = item["state"]
                item["state"] = "DOCUMENT_SYNTHESIS_PENDING_V2"
                item["documentation_status"] = "DOCUMENT_SYNTHESIS_PENDING_V2"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(DATA_ROOT),
        "inventory_only": inventory_only,
        "items": items,
    }
    _write_manifest(manifest_path, payload)
    if inventory_only:
        return payload

    ready = [item for item in items if item["state"] == "READY"]
    if limit is not None:
        ready = ready[:limit]
    for item in ready:
        frames = Path(item["frames_dir"])
        project = projects_by_name.get(item["project_name"])
        profile = generation_profile(project)
        profile["evidence_only"] = evidence_only
        profile["mode_override"] = mode_override
        try:
            def generate(path: Path, project_config: dict | None = None) -> dict[str, Any]:
                return regenerate_documentation_v2(
                    path, mode_override=mode_override, evidence_only=evidence_only,
                    project_config=project_config,
                )

            result = regenerate_versioned(
                frames,
                item["media_id"],
                generate,
                project_config=project,
                profile=profile,
            )
            item["state"] = result.get("version", {}).get(
                "generation_status", result.get("status", "UNKNOWN")
            )
            item["version"] = result.get("version")
        except Exception as exc:  # keep the rest of the corpus resumable
            item["state"] = "FAILED"
            item["error"] = type(exc).__name__
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_manifest(manifest_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m transcript_pipeline.documentation.batch_regenerate_v2",
        description="Inventory or regenerate Docs V2 from saved frame mappings without rerunning upstream media work.",
    )
    parser.add_argument("--manifest", type=Path, default=DATA_ROOT / "documentation_v2_batch_manifest.json")
    parser.add_argument("--inventory", action="store_true", help="write corpus readiness report without generating documentation")
    parser.add_argument("--evidence-only", action="store_true", help="write evidence timeline without semantic synthesis")
    parser.add_argument("--mode", choices=("AUTO", "TUTORIAL", "KT_SESSION", "PROCESS_WALKTHROUGH", "MEETING", "ARCHITECTURE", "INCIDENT", "REFERENCE"))
    parser.add_argument("--limit", type=int, help="process at most this many ready videos")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    result = run_batch(
        manifest_path=args.manifest.resolve(), inventory_only=args.inventory,
        evidence_only=args.evidence_only, mode_override=args.mode, limit=args.limit,
    )
    counts: dict[str, int] = {}
    for item in result["items"]:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    print(json.dumps({"manifest": str(args.manifest.resolve()), "total": len(result["items"]), "states": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
