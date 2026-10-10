"""Small durable SQLite queue for dashboard pipeline runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class QueueStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                event TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        if "attempts" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
        return db

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _event(db: sqlite3.Connection, job_id: int | None, event: str, payload: dict[str, Any]) -> None:
        db.execute("INSERT INTO events(job_id,event,payload,created_at) VALUES(?,?,?,?)",
                   (job_id, event, json.dumps(payload), QueueStore._now()))

    def recover(self) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT id,attempts FROM jobs WHERE status='running'").fetchall()
            db.execute("UPDATE jobs SET status=CASE WHEN attempts < 3 THEN 'queued' ELSE 'failed' END, started_at=NULL, finished_at=CASE WHEN attempts < 3 THEN NULL ELSE ? END WHERE status='running'", (self._now(),))
            for job_id, attempts in rows:
                event = "recovered_after_restart" if attempts < 3 else "retry_limit_reached"
                self._event(db, job_id, event, {"attempts": attempts})
            db.commit()

    def enqueue(self, mode: str) -> tuple[int, bool]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM jobs WHERE mode=? AND status='queued' ORDER BY id LIMIT 1", (mode,)).fetchone()
            if row:
                db.commit()
                return int(row[0]), False
            cursor = db.execute("INSERT INTO jobs(mode,status,created_at) VALUES(?,'queued',?)", (mode, self._now()))
            job_id = int(cursor.lastrowid)
            self._event(db, job_id, "queued", {"mode": mode})
            db.commit()
            return job_id, True

    def cancel_latest(self, mode: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM jobs WHERE mode=? AND status='queued' ORDER BY id DESC LIMIT 1", (mode,)).fetchone()
            if row:
                db.execute("DELETE FROM jobs WHERE id=?", (row[0],))
                self._event(db, int(row[0]), "cancelled", {"reason": "request_conflict"})
            db.commit()

    def claim(self) -> tuple[int, str] | None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,mode FROM jobs WHERE status='queued' AND attempts < 3 ORDER BY id LIMIT 1").fetchone()
            if not row:
                db.commit()
                return None
            job_id, mode = int(row[0]), str(row[1])
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1,started_at=? WHERE id=?", (self._now(), job_id))
            self._event(db, job_id, "started", {"mode": mode})
            db.commit()
            return job_id, mode

    def finish(self, job_id: int, error: str | None = None) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            attempts = db.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            status = "queued" if error and attempts < 3 else "failed" if error else "completed"
            finished_at = None if status == "queued" else self._now()
            db.execute("UPDATE jobs SET status=?,finished_at=?,error=? WHERE id=?",
                       (status, finished_at, error, job_id))
            event = "retry_scheduled" if status == "queued" else status
            self._event(db, job_id, event, {"error": error, "attempt": attempts} if error else {})
            db.commit()

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as db:
            jobs = db.execute("SELECT id,mode,status,created_at,started_at,finished_at,error FROM jobs ORDER BY id DESC LIMIT 50").fetchall()
            counts = dict(db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall())
        return {
            "counts": counts,
            "jobs": [dict(zip(("id", "mode", "status", "created_at", "started_at", "finished_at", "error"), row)) for row in jobs],
        }

    def events_after(self, event_id: int) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,job_id,event,payload,created_at FROM events WHERE id>? ORDER BY id LIMIT 200",
                (event_id,),
            ).fetchall()
        return [dict(zip(("id", "job_id", "event", "payload", "created_at"), row)) for row in rows]

    def record_event(self, event: str, payload: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._event(db, None, event, payload)
            db.commit()
