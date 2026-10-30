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
    for key in ("utterances", "decisions", "actions", "questions", "topics", "observations", "evidenceRefs", "canonicalCandidates"):
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
            evaluation_state TEXT NOT NULL DEFAULT 'RECEIVED_PENDING_EVALUATION',
            evaluation_json TEXT,
            received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(meeting_intake)")}
        if "evaluation_state" not in columns:
            db.execute("ALTER TABLE meeting_intake ADD COLUMN evaluation_state TEXT NOT NULL DEFAULT 'RECEIVED_PENDING_EVALUATION'")
        if "evaluation_json" not in columns:
            db.execute("ALTER TABLE meeting_intake ADD COLUMN evaluation_json TEXT")
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


def get_intake_package(data_root: Path, session_id: str) -> dict[str, Any] | None:
    db_path = data_root / "knowledge-meetings.sqlite3"
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as db:
        row = db.execute("SELECT package_json FROM meeting_intake WHERE session_id = ?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else None


def evaluate_intake(data_root: Path, session_id: str, existing: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    from transcript_pipeline.knowledge.learning_evaluation import evaluate_meeting_candidates

    db_path = data_root / "knowledge-meetings.sqlite3"
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT package_json, evaluation_json FROM meeting_intake WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        if row[1]:
            return json.loads(row[1])
        package = json.loads(row[0])
        result = evaluate_meeting_candidates(package, existing)
        db.execute(
            "UPDATE meeting_intake SET evaluation_state = ?, evaluation_json = ? WHERE session_id = ?",
            (result["state"], json.dumps(result, ensure_ascii=False, sort_keys=True), session_id),
        )
    return result
