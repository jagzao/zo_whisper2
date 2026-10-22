"""Durable queue and hourly timezone-aware processor scheduler."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROCESS_STARTED_AT = datetime.now(timezone.utc)
PROCESS_INSTANCE_ID = uuid.uuid4().hex


def processing_limit(now: datetime, timezone_name: str = "America/Mexico_City") -> int:
    local = now.astimezone(ZoneInfo(timezone_name))
    return 1 if 9 <= local.hour < 21 else 3


class ProcessingJobStore:
    def __init__(self, root: Path, *, stale_after: timedelta = timedelta(hours=6)):
        self.directory = root / ".whisper"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "processing_jobs.json"
        self.lock_path = self.directory / "processing_jobs.lock"
        self.lease_path = self.directory / "processing_jobs.lease"
        self.stale_after = stale_after

    @contextmanager
    def _locked(self):
        token = uuid.uuid4().hex
        deadline = time.monotonic() + 30
        while True:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(self.lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                    handle.write(token)
                break
            except (FileExistsError, PermissionError):
                try:
                    lease_mtime = self.lease_path.stat().st_mtime
                except FileNotFoundError:
                    lease_mtime = None
                except OSError:
                    lease_mtime = None
                if lease_mtime is not None and time.time() - lease_mtime > 30:
                    try:
                        self.lease_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for shared processing queue lock")
                time.sleep(0.01)
            except FileNotFoundError:
                self.directory.mkdir(parents=True, exist_ok=True)
        try:
            yield
        finally:
            try:
                if self.lease_path.read_text(encoding="ascii") == token:
                    self.lease_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and isinstance(data.get("jobs"), list) else {"jobs": []}
        except (OSError, ValueError):
            return {"jobs": []}

    def _write(self, data: dict[str, Any]) -> None:
        temp = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def enqueue(self, mode: str = "full", *, scheduled: bool = False,
                idempotency_key: str | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._locked():
            data = self._read()
            if idempotency_key:
                previous = next((j for j in data["jobs"] if j.get("idempotency_key") == idempotency_key), None)
                if previous:
                    return dict(previous)
            if scheduled and any(j.get("scheduled") and j.get("status") in {"QUEUED", "ACTIVE"} for j in data["jobs"]):
                return next(j for j in data["jobs"] if j.get("scheduled") and j.get("status") in {"QUEUED", "ACTIVE"})
            job = {"id": uuid.uuid4().hex, "mode": mode, "status": "QUEUED", "scheduled": scheduled,
                   "created_at": now, "updated_at": now, "attempt": 0}
            if idempotency_key:
                job["idempotency_key"] = idempotency_key
            data["jobs"].append(job)
            self._write(data)
            return dict(job)

    def claim_next(self, limit: int, *, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or datetime.now(timezone.utc)
        with self._locked():
            data = self._read()
            changed = False
            for job in data["jobs"]:
                if job.get("status") == "CANCEL_REQUESTED":
                    job.update(status="CANCELLED", updated_at=now.isoformat())
                    changed = True
                elif job.get("status") == "ACTIVE":
                    pid = job.get("worker_pid")
                    dead_worker = False
                    worker_host = job.get("worker_host")
                    same_process_namespace = worker_host == socket.gethostname() or (
                        worker_host is None and os.name == "nt"
                    )
                    process_restarted = False
                    if same_process_namespace and pid == os.getpid():
                        try:
                            owner_instance = job.get("worker_instance_id")
                            claimed_at = datetime.fromisoformat(job.get("started_at", ""))
                            process_restarted = (
                                owner_instance != PROCESS_INSTANCE_ID
                                if owner_instance is not None
                                else claimed_at < PROCESS_STARTED_AT
                            )
                        except (TypeError, ValueError):
                            process_restarted = True
                    if same_process_namespace and isinstance(pid, int) and pid != os.getpid():
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            dead_worker = True
                    try:
                        started = datetime.fromisoformat(job.get("heartbeat_at") or job["started_at"])
                    except (ValueError, KeyError):
                        started = now - self.stale_after - timedelta(seconds=1)
                    if dead_worker or process_restarted or now - started > self.stale_after:
                        job.update(status="QUEUED", updated_at=now.isoformat(), recovered_at=now.isoformat())
                        job.pop("started_at", None)
                        job.pop("heartbeat_at", None)
                        changed = True
            active = sum(j.get("status") == "ACTIVE" for j in data["jobs"])
            candidate = next((j for j in data["jobs"] if j.get("status") in {"QUEUED", "PENDING"}), None)
            if candidate is None or active >= max(1, limit):
                if changed:
                    self._write(data)
                return None
            candidate.update(status="ACTIVE", started_at=now.isoformat(), heartbeat_at=now.isoformat(),
                             updated_at=now.isoformat(), worker_pid=os.getpid(), worker_host=socket.gethostname(),
                             worker_instance_id=PROCESS_INSTANCE_ID,
                             attempt=int(candidate.get("attempt", 0)) + 1)
            self._write(data)
            return dict(candidate)

    def finish(self, job_id: str, status: str, error: str | None = None) -> None:
        with self._locked():
            data = self._read()
            for job in data["jobs"]:
                if job.get("id") == job_id and job.get("status") in {"ACTIVE", "CANCEL_REQUESTED"}:
                    if job.get("status") == "CANCEL_REQUESTED":
                        status = "CANCELLED"
                    finished_at = datetime.now(timezone.utc).isoformat()
                    job.update(status=status, updated_at=finished_at, finished_at=finished_at)
                    if error:
                        job["error"] = error[:500]
                    self._write(data)
                    return

    def cancel_requested(self, job_id: str) -> bool:
        with self._locked():
            return any(job.get("id") == job_id and job.get("status") in {"CANCEL_REQUESTED", "CANCELLED"}
                       for job in self._read()["jobs"])

    def cancel(self, job_id: str) -> bool:
        with self._locked():
            data = self._read()
            for job in data["jobs"]:
                if job.get("id") == job_id:
                    if job.get("status") in {"COMPLETED", "FAILED", "CANCELLED"}:
                        return True
                    job["status"] = "CANCELLED" if job.get("status") in {"QUEUED", "PENDING"} else "CANCEL_REQUESTED"
                    job["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self._write(data)
                    return True
            return False

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._locked():
            return [dict(job) for job in self._read()["jobs"]]

    def status(self, *, running: bool, limit: int, next_scan: datetime | None, last_scan: datetime | None) -> dict[str, Any]:
        jobs = self.list_jobs()
        return {"state": "RUNNING" if running else "STOPPED",
                "pending_jobs": sum(j.get("status") in {"QUEUED", "PENDING"} for j in jobs),
                "active_jobs": sum(j.get("status") in {"ACTIVE", "CANCEL_REQUESTED"} for j in jobs),
                "concurrency_limit": limit,
                "next_scan": next_scan.isoformat() if next_scan else None,
                "last_scan": last_scan.isoformat() if last_scan else None}


class ProcessingWorker:
    def __init__(self, store: ProcessingJobStore, executor: Callable[[str], None], *,
                 timezone_name: str = "America/Mexico_City", scan_interval: float = 3600,
                 scan_pending: Callable[[], bool] | None = None, poll_interval: float = 1,
                 execution_limit: int = 3, executor_accepts_cancel: bool = False):
        self.store = store
        self.executor = executor
        self.timezone_name = timezone_name
        self.scan_interval = scan_interval
        self.scan_pending = scan_pending or (lambda: False)
        self.poll_interval = poll_interval
        self.execution_limit = max(1, execution_limit)
        self.executor_accepts_cancel = executor_accepts_cancel
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self.last_error: str | None = None
        self.last_error_at: str | None = None
        self.last_scan: datetime | None = None
        self.next_scan: datetime | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            if self.next_scan is None:
                self.next_scan = datetime.now(timezone.utc) + timedelta(seconds=self.scan_interval)
            self._thread = threading.Thread(target=self._loop, name="whisper-processing-worker", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 2) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def scan_once(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        self.last_scan = now
        self.next_scan = now + timedelta(seconds=self.scan_interval)
        if any(job.get("status") in {"QUEUED", "PENDING", "ACTIVE", "CANCEL_REQUESTED"}
               for job in self.store.list_jobs()):
            return False
        found = self.scan_pending()
        if found:
            self.store.enqueue("full", scheduled=True)
        return found

    def _run_job(self, job: dict[str, Any]) -> None:
        try:
            if self.executor_accepts_cancel:
                self.executor(job["mode"], lambda: self.store.cancel_requested(job["id"]))
            else:
                self.executor(job["mode"])
        except Exception as exc:
            self.store.finish(job["id"], "FAILED", str(exc))
        else:
            self.store.finish(job["id"], "COMPLETED")
        finally:
            with self._lock:
                self._active.pop(job["id"], None)

    def run_pending_once(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        limit = processing_limit(now, self.timezone_name)
        launched = 0
        with self._lock:
            for job_id, thread in list(self._active.items()):
                if not thread.is_alive():
                    self._active.pop(job_id, None)
            capacity = max(0, min(limit, self.execution_limit) - len(self._active))
            for _ in range(capacity):
                job = self.store.claim_next(limit, now=now)
                if job is None:
                    break
                thread = threading.Thread(target=self._run_job, args=(job,), name=f"whisper-job-{job['id'][:8]}", daemon=True)
                self._active[job["id"]] = thread
                thread.start()
                launched += 1
        return launched

    def _loop(self) -> None:
        next_scan = self.next_scan or (datetime.now(timezone.utc) + timedelta(seconds=self.scan_interval))
        while not self._stop.is_set():
            now = datetime.now(timezone.utc)
            if now >= next_scan:
                try:
                    self.scan_once(now)
                    self.last_error = None
                    self.last_error_at = None
                except Exception as exc:
                    self.last_error = str(exc)
                    self.last_error_at = datetime.now(timezone.utc).isoformat()
                next_scan = self.next_scan or (now + timedelta(seconds=self.scan_interval))
            try:
                self.run_pending_once(now)
            except Exception as exc:
                self.last_error = str(exc)
                self.last_error_at = datetime.now(timezone.utc).isoformat()
            self._stop.wait(self.poll_interval)

    def status(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        limit = processing_limit(now, self.timezone_name)
        local_zone = ZoneInfo(self.timezone_name)
        return {**self.store.status(running=bool(self._thread and self._thread.is_alive()), limit=limit,
                                   next_scan=self.next_scan.astimezone(local_zone) if self.next_scan else None,
                                   last_scan=self.last_scan.astimezone(local_zone) if self.last_scan else None),
                "last_error": self.last_error, "last_error_at": self.last_error_at}
