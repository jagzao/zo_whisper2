from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcript_pipeline.config import DATA_ROOT

_LOCK = threading.Lock()
_PATH = DATA_ROOT / ".whisper" / "pipeline_metrics.json"


def _key(project: str | None, filename: str) -> str:
    return f"{project or ''}/{filename}".casefold()


def record_stage(project: str | None, filename: str, stage: str, duration_seconds: float) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with _LOCK:
        try:
            data = json.loads(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else {}
        except (OSError, ValueError):
            data = {}
        item = data.setdefault(_key(project, filename), {"project": project, "filename": filename, "stages": {}})
        item["stages"][stage] = {"duration_seconds": round(max(0.0, duration_seconds), 3), "completed_at": now.isoformat()}
        item["total_seconds"] = round(
            sum(float(value.get("duration_seconds", 0)) for value in item["stages"].values()), 3
        )
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(_PATH)
        return item


def get_metrics(project: str | None, filename: str) -> dict[str, Any]:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return data.get(_key(project, filename), {"stages": {}})
    except (OSError, ValueError):
        return {"stages": {}}
