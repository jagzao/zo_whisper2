"""Local, idempotent evidence intake for completed Zavi meetings.

Intake only records a package. It never makes learning or embedding decisions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class MeetingPackageError(ValueError):
    pass


def validate_meeting_package(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MeetingPackageError("package_must_be_object")
    required = ("schemaVersion", "sessionId", "projectId", "meetingType", "startedAt", "endedAt")
    if any(value.get(key) is None or not str(value[key]).strip() for key in required):
        raise MeetingPackageError("missing_required_field")
    if value["schemaVersion"] != 1:
        raise MeetingPackageError("unsupported_schema_version")
    for key in ("utterances", "decisions", "actions", "questions", "topics", "observations", "evidenceRefs"):
        if key in value and not isinstance(value[key], list):
            raise MeetingPackageError(f"{key}_must_be_array")
    return value


def store_meeting_package(data_root: Path, package: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    db_path = data_root / "knowledge-meetings.sqlite3"
    data_root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS meeting_intake (
            session_id TEXT PRIMARY KEY,
            content_sha256 TEXT NOT NULL,
            package_json TEXT NOT NULL,
            received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )""")
        row = db.execute(
            "SELECT content_sha256 FROM meeting_intake WHERE session_id = ?",
            (package["sessionId"],),
        ).fetchone()
        if row:
            if row[0] != digest:
                return {"status": "CONFLICT", "sessionId": package["sessionId"]}
            return {"status": "DUPLICATE", "sessionId": package["sessionId"]}
        db.execute(
            "INSERT INTO meeting_intake(session_id, content_sha256, package_json) VALUES (?, ?, ?)",
            (package["sessionId"], digest, payload),
        )
    return {"status": "RECEIVED_PENDING_EVALUATION", "sessionId": package["sessionId"]}
