from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PIPELINE_VERSION = "documentation-v2"
_OUTPUTS = ("manual", "ai-package", "evidence")


def _fingerprint(frames_dir: Path) -> str:
    digest = hashlib.sha256(PIPELINE_VERSION.encode())
    candidates = [frames_dir / "frame_mapping.json", frames_dir / "evidence" / "evidence.jsonl"]
    for path in candidates:
        digest.update(path.name.encode())
        if path.is_file():
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    return digest.hexdigest()


def list_versions(frames_dir: Path) -> list[dict[str, Any]]:
    root = frames_dir / "documentation_versions"
    versions = []
    if not root.is_dir():
        return versions
    for manifest in sorted(root.glob("*/version.json"), reverse=True):
        try:
            versions.append(json.loads(manifest.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return versions


def regenerate_versioned(
    frames_dir: Path,
    source_video_id: str,
    generator: Callable[..., dict[str, Any]],
    *,
    project_config: dict | None = None,
) -> dict[str, Any]:
    fingerprint = _fingerprint(frames_dir)
    versions = list_versions(frames_dir)
    if versions and versions[0].get("source_fingerprint") == fingerprint and versions[0].get("status") == "COMPLETED":
        return {"status": "IDEMPOTENT", "version": versions[0]}

    root = frames_dir / "documentation_versions"
    root.mkdir(parents=True, exist_ok=True)
    number = max((int(v.get("documentation_version", 0)) for v in versions), default=0) + 1
    final_dir = root / f"{number:06d}"
    staging = Path(tempfile.mkdtemp(prefix=".docs-version-", dir=root))
    backup = Path(tempfile.mkdtemp(prefix=".docs-current-", dir=frames_dir))
    for name in _OUTPUTS:
        current = frames_dir / name
        if current.exists():
            shutil.copytree(current, backup / name)
    previous = versions[0].get("documentation_version") if versions else None
    try:
        result = generator(frames_dir, project_config=project_config)
        fingerprint = _fingerprint(frames_dir)
        for name in _OUTPUTS:
            current = frames_dir / name
            if current.is_dir():
                shutil.copytree(current, staging / name)
        metadata = {
            "documentation_version": number,
            "pipeline_version": PIPELINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_video_id": source_video_id,
            "source_evidence_references": ["frame_mapping.json", "evidence/evidence.jsonl"],
            "source_fingerprint": fingerprint,
            "status": "COMPLETED",
            "previous_version": previous,
            "generation_status": result.get("status"),
        }
        (staging / "version.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        staging.replace(final_dir)
        return {"status": result.get("status"), "version": metadata}
    except Exception:
        for name in _OUTPUTS:
            current = frames_dir / name
            saved = backup / name
            if saved.exists():
                shutil.rmtree(current, ignore_errors=True)
                shutil.copytree(saved, current)
            else:
                shutil.rmtree(current, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
