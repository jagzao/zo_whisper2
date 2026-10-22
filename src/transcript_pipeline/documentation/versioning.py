from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PIPELINE_VERSION = "documentation-v2"
GENERATION_REVISION = "docs-v2-corpus-1"
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


def generation_profile(project_config: dict | None = None) -> dict[str, Any]:
    """Return non-secret inputs that change semantic generation behavior."""
    from transcript_pipeline.documentation.modes import normalize_documentation_config
    from transcript_pipeline.settings import SETTINGS

    parsed = urlsplit(SETTINGS.llm_base_url)
    endpoint = f"{parsed.scheme}://{parsed.hostname or ''}{parsed.path.rstrip('/')}"
    if parsed.port:
        endpoint += f":{parsed.port}"
    project = project_config if isinstance(project_config, dict) else {}
    return {
        "generation_revision": GENERATION_REVISION,
        "provider_type": SETTINGS.llm_provider_type,
        "endpoint": endpoint,
        "model": SETTINGS.llm_model,
        "external_allowed": SETTINGS.allow_external_llm,
        "project_classification": project.get("data_classification", "internal"),
        "documentation": normalize_documentation_config(project.get("documentation")),
    }


def _profile_fingerprint(profile: dict[str, Any]) -> str:
    serialized = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fingerprint = _fingerprint(frames_dir)
    profile = profile or generation_profile(project_config)
    profile_fingerprint = _profile_fingerprint(profile)
    versions = list_versions(frames_dir)
    if (versions and versions[0].get("source_fingerprint") == fingerprint
            and versions[0].get("profile_fingerprint") == profile_fingerprint
            and versions[0].get("status") == "COMPLETED"
            and versions[0].get("generation_status") != "SYNTHESIS_INVALID"):
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
            "profile": profile,
            "profile_fingerprint": profile_fingerprint,
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
