from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from transcript_pipeline.capture.models import (
    ROI,
    CaptureConfig,
    CaptureSegment,
    CaptureSession,
    SessionStatus,
)
from transcript_pipeline.capture.retention import retention_advice
from transcript_pipeline.capture.service import CaptureService
from transcript_pipeline.capture.store import CaptureStore
from transcript_pipeline.security import MediaRoot, SafePathResolver
from transcript_pipeline.security.exceptions import PathTraversalError


def test_session_ids_configs_and_atomic_roundtrip(tmp_path):
    store = CaptureStore(tmp_path / "live-capture")
    service = CaptureService(store)
    session = service.create_session("  Demo  ", capture_config=CaptureConfig(roi=ROI(0.1, 0.2, 0.5, 0.4)))
    assert str(UUID(session.sessionId)) == session.sessionId
    persisted = store.get_session(session.sessionId)
    assert persisted.title == "Demo"
    assert persisted.captureConfig.roi == ROI(0.1, 0.2, 0.5, 0.4)
    assert (store.session_root(session.sessionId) / "session.json").exists()
    assert json.loads((store.session_root(session.sessionId) / "session.json").read_text())["status"] == "CREATED"


def test_atomic_manifest_failure_keeps_last_good_file(tmp_path, monkeypatch):
    store = CaptureStore(tmp_path / "live-capture")
    session = CaptureService(store).create_session("Atomic")
    path = store.session_root(session.sessionId) / "session.json"
    original = path.read_bytes()
    monkeypatch.setattr("transcript_pipeline.capture.store.os.replace", lambda *args: (_ for _ in ()).throw(OSError("simulated interruption")))
    session.title = "Changed"
    with pytest.raises(OSError):
        store.save_session(session)
    assert path.read_bytes() == original


@pytest.mark.parametrize("roi", [ROI(0, 0, 1, 1)])
def test_valid_full_frame_roi(roi):
    assert roi.width == 1


@pytest.mark.parametrize("values", [(-0.1, 0, 0.2, 0.2), (0.9, 0.9, 0.2, 0.2), (0, 0, 0, 1)])
def test_invalid_roi_rejected(values):
    with pytest.raises(ValueError):
        ROI(*values)


def test_state_transitions_active_session_bound_and_segment_roundtrip(tmp_path):
    store = CaptureStore(tmp_path / "capture")
    service = CaptureService(store)
    session = service.create_session("One")
    with pytest.raises(RuntimeError, match="active capture"):
        service.create_session("Two")
    started = service.transition(session.sessionId, SessionStatus.RECORDING)
    assert started.startedAt
    with pytest.raises(ValueError, match="invalid session transition"):
        service.transition(session.sessionId, SessionStatus.COMPLETE)
    segment = CaptureSegment(session.sessionId, 1, 0, 600)
    store.save_segment(segment)
    assert store.get_segment(session.sessionId, 1) == segment


def test_store_rejects_session_path_escape_and_resolver_has_capture_root(tmp_path):
    store = CaptureStore(tmp_path / "capture")
    with pytest.raises(ValueError):
        store.session_root("../../outside")
    resolver = SafePathResolver({MediaRoot.CAPTURE: tmp_path / "capture"})
    with pytest.raises(PathTraversalError):
        resolver.resolve(MediaRoot.CAPTURE, "../outside", must_exist=False)


def test_retention_is_advisory_and_requires_complete_valid_unviewed_source():
    now = datetime.now(timezone.utc)
    session = CaptureSession(
        sessionId="efcd250c-d049-44b7-b754-aee0965046e5", title="Retention",
        status=SessionStatus.COMPLETE, documentationState="VALID", sourceMediaState="PRESENT",
        lastViewedAt=(now - timedelta(days=190)).isoformat(),
    )
    assert retention_advice(session, now=now) == {"suggestDeletion": True, "strongStale": True}
    session.status = SessionStatus.WAITING_FOR_EXTERNAL_TRANSCRIPT
    assert retention_advice(session, now=now) == {"suggestDeletion": False, "strongStale": False}
