from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from transcript_pipeline.processing_worker import (
    PROCESS_STARTED_AT,
    ProcessingJobStore,
    ProcessingWorker,
    processing_limit,
)


def test_processing_limit_uses_configured_local_timezone():
    tz = ZoneInfo("America/Mexico_City")
    assert processing_limit(datetime(2026, 10, 16, 10, tzinfo=tz)) == 1
    assert processing_limit(datetime(2026, 10, 16, 20, 59, tzinfo=tz)) == 1
    assert processing_limit(datetime(2026, 10, 16, 21, tzinfo=tz)) == 3
    assert processing_limit(datetime(2026, 10, 17, 8, 59, tzinfo=tz)) == 3


def test_duplicate_worker_claim_prevention(tmp_path):
    first = ProcessingJobStore(tmp_path)
    second = ProcessingJobStore(tmp_path)
    first.enqueue()
    results = []
    barrier = threading.Barrier(3)

    def claim(store):
        barrier.wait()
        results.append(store.claim_next(1))

    threads = [threading.Thread(target=claim, args=(store,)) for store in (first, second)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sum(result is not None for result in results) == 1


def test_concurrent_queue_calls_from_one_process_serialize_across_store_instances(tmp_path):
    stores = [ProcessingJobStore(tmp_path) for _ in range(12)]
    barrier = threading.Barrier(len(stores))
    errors = []

    def enqueue(store):
        barrier.wait()
        try:
            store.enqueue()
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=enqueue, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(stores[0].list_jobs()) == len(stores)


def test_upload_enqueue_is_idempotent_by_session_id(tmp_path):
    store = ProcessingJobStore(tmp_path)
    first = store.enqueue("full", idempotency_key="upload:session-a")
    duplicate = store.enqueue("full", idempotency_key="upload:session-a")
    other = store.enqueue("full", idempotency_key="upload:session-b")
    assert duplicate["id"] == first["id"]
    assert other["id"] != first["id"]
    store.claim_next(1)
    store.finish(first["id"], "FAILED", "synthetic failure")
    failed = next(job for job in store.list_jobs() if job["id"] == first["id"])
    assert failed["finished_at"]
    assert store.enqueue("full", idempotency_key="upload:session-a")["id"] == first["id"]
    assert len(store.list_jobs()) == 2


def test_shared_queue_lock_recreates_removed_state_directory(tmp_path):
    store = ProcessingJobStore(tmp_path)
    shutil.rmtree(store.directory)
    assert store.claim_next(1) is None
    assert store.directory.is_dir()


def test_shared_queue_lock_retries_cross_runtime_create_collision(tmp_path, monkeypatch):
    store = ProcessingJobStore(tmp_path)
    original_open = os.open
    collisions = 0

    def open_with_collision(path, flags, *args, **kwargs):
        nonlocal collisions
        if Path(path) == store.lease_path and collisions == 0:
            collisions += 1
            raise PermissionError(13, "cross-runtime exclusive-create race")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_with_collision)
    assert store.enqueue()["status"] == "QUEUED"
    assert collisions == 1


def test_hourly_scan_enqueues_pending_work(tmp_path):
    store = ProcessingJobStore(tmp_path)
    worker = ProcessingWorker(store, lambda _: None, scan_interval=3600, scan_pending=lambda: True)
    now = datetime(2026, 10, 16, 16, tzinfo=timezone.utc)
    assert worker.scan_once(now)
    assert worker.last_scan == now
    assert worker.next_scan == now + timedelta(hours=1)
    assert len(store.list_jobs()) == 1
    assert store.list_jobs()[0]["scheduled"] is True
    status = worker.status(now)
    assert status["next_scan"] is not None and status["last_scan"] is not None
    assert status["concurrency_limit"] == 1


def test_scheduler_repeats_scans_at_configured_hourly_interval(tmp_path):
    scans = []
    worker = ProcessingWorker(ProcessingJobStore(tmp_path), lambda _: None,
                              scan_interval=0.05, poll_interval=0.01,
                              scan_pending=lambda: scans.append(time.time()) or False)
    worker.start()
    assert worker.status()["state"] == "RUNNING"
    assert worker.status()["next_scan"] is not None
    deadline = time.time() + 3
    while time.time() < deadline and len(scans) < 2:
        time.sleep(0.01)
    worker.stop()
    assert len(scans) >= 2


def test_restart_recovers_dead_worker_claim(tmp_path):
    store = ProcessingJobStore(tmp_path)
    now = datetime.now(timezone.utc)
    job = store.enqueue()
    claimed = store.claim_next(1, now=now)
    assert claimed and claimed["id"] == job["id"]
    data = store._read()
    data["jobs"][0]["worker_pid"] = 99999999
    store._write(data)
    recovered = ProcessingJobStore(tmp_path).claim_next(1, now=now + timedelta(seconds=1))
    assert recovered and recovered["id"] == job["id"]
    assert recovered["attempt"] == 2
    assert recovered["recovered_at"]


def test_restart_recovers_reused_pid_from_previous_process_instance(tmp_path):
    store = ProcessingJobStore(tmp_path)
    job = store.enqueue()
    old_instance_claim = PROCESS_STARTED_AT - timedelta(seconds=1)
    claimed = store.claim_next(1, now=old_instance_claim)
    assert claimed and claimed["id"] == job["id"]

    data = store._read()
    data["jobs"][0].pop("worker_instance_id")
    store._write(data)

    recovered = store.claim_next(1, now=PROCESS_STARTED_AT + timedelta(seconds=1))
    assert recovered and recovered["id"] == job["id"]
    assert recovered["attempt"] == 2
    assert recovered["worker_instance_id"]
    assert recovered["recovered_at"]


def test_container_worker_does_not_treat_host_pid_as_dead(tmp_path):
    store = ProcessingJobStore(tmp_path)
    job = store.enqueue()
    claimed = store.claim_next(1)
    assert claimed and claimed["id"] == job["id"]
    data = store._read()
    data["jobs"][0].update(worker_pid=99999999, worker_host="other-runtime")
    store._write(data)
    assert ProcessingJobStore(tmp_path).claim_next(1) is None
    assert ProcessingJobStore(tmp_path).list_jobs()[0]["attempt"] == 1


def test_cancelled_jobs_are_not_claimed(tmp_path):
    store = ProcessingJobStore(tmp_path)
    job = store.enqueue()
    assert store.cancel(job["id"])
    assert store.claim_next(3) is None
    assert store.list_jobs()[0]["status"] == "CANCELLED"


def test_active_job_cancellation_is_observed(tmp_path):
    store = ProcessingJobStore(tmp_path)
    job = store.enqueue()
    entered = threading.Event()

    def execute(_mode, cancelled):
        entered.set()
        deadline = time.time() + 2
        while time.time() < deadline and not cancelled():
            time.sleep(0.01)
        assert cancelled()

    worker = ProcessingWorker(store, execute, executor_accepts_cancel=True)
    assert worker.run_pending_once() == 1
    assert entered.wait(1)
    assert store.cancel(job["id"])
    deadline = time.time() + 2
    while time.time() < deadline and store.list_jobs()[0]["status"] != "CANCELLED":
        time.sleep(0.01)
    assert store.list_jobs()[0]["status"] == "CANCELLED"


def test_daytime_worker_uses_one_slot(tmp_path):
    store = ProcessingJobStore(tmp_path)
    for _ in range(3):
        store.enqueue()
    started = threading.Event()
    release = threading.Event()
    worker = ProcessingWorker(store, lambda _: (started.set(), release.wait(1)), execution_limit=3)
    now = datetime(2026, 10, 16, 10, tzinfo=ZoneInfo("America/Mexico_City"))
    assert worker.run_pending_once(now) == 1
    assert started.wait(1)
    assert store.status(running=True, limit=1, next_scan=None, last_scan=None)["active_jobs"] == 1
    release.set()


def test_worker_never_exceeds_night_limit(tmp_path):
    store = ProcessingJobStore(tmp_path)
    for _ in range(4):
        store.enqueue()
    started = threading.Event()
    release = threading.Event()
    active = 0
    peak = 0
    guard = threading.Lock()

    def execute(_mode):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
            started.set()
        release.wait(2)
        with guard:
            active -= 1

    worker = ProcessingWorker(store, execute, execution_limit=3)
    now = datetime(2026, 10, 16, 22, tzinfo=ZoneInfo("America/Mexico_City"))
    assert worker.run_pending_once(now) == 3
    assert started.wait(1)
    time.sleep(0.05)
    assert peak <= processing_limit(now)
    assert store.status(running=True, limit=3, next_scan=None, last_scan=None)["active_jobs"] == 3
    release.set()
    deadline = time.time() + 2
    while time.time() < deadline and store.status(running=True, limit=3, next_scan=None, last_scan=None)["active_jobs"]:
        time.sleep(0.01)
    assert store.status(running=True, limit=3, next_scan=None, last_scan=None)["pending_jobs"] == 1
