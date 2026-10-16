from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from transcript_pipeline.config import DATA_ROOT

_LOCK = threading.Lock()
_PATH = DATA_ROOT / ".whisper" / "upload_ids.json"
_MAX_ENTRIES = 2000


def find_upload(upload_id: str, project: str | None, upload_root: Path) -> dict[str, Any] | None:
    with _LOCK:
        try:
            records = json.loads(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else {}
        except (OSError, ValueError):
            records = {}
        result = records.get(upload_id)
        if not result:
            return None
        if result.get("project") != project or result.get("root") != str(upload_root.resolve()):
            return None
        destination = upload_root / result.get("name", "")
        return result if destination.is_file() and destination.stat().st_size == result.get("size") else None


def remember_upload(upload_id: str, project: str | None, upload_root: Path, name: str, size: int) -> None:
    with _LOCK:
        try:
            records = json.loads(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else {}
        except (OSError, ValueError):
            records = {}
        records[upload_id] = {
            "project": project,
            "root": str(upload_root.resolve()),
            "name": name,
            "size": size,
        }
        records = dict(list(records.items())[-_MAX_ENTRIES:])
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
        temporary.replace(_PATH)


def remove_upload_records(upload_root: Path, name: str) -> None:
    with _LOCK:
        try:
            records = json.loads(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else {}
        except (OSError, ValueError):
            return
        root = str(upload_root.resolve())
        retained = {
            key: value for key, value in records.items()
            if not (value.get("root") == root and value.get("name") == name)
        }
        if retained == records:
            return
        temporary = _PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(retained, indent=2), encoding="utf-8")
        temporary.replace(_PATH)
