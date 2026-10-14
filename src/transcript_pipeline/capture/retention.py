from __future__ import annotations

from datetime import datetime, timedelta, timezone

from transcript_pipeline.capture.models import CaptureSession, SessionStatus


def retention_advice(
    session: CaptureSession, *, now: datetime | None = None, suggest_after_days: int = 90, stale_after_days: int = 180
) -> dict[str, bool]:
    now = now or datetime.now(timezone.utc)
    activity_at = session.lastViewedAt or session.completedAt or session.createdAt
    age = now - datetime.fromisoformat(activity_at)
    eligible = (
        session.status is SessionStatus.COMPLETE
        and session.documentationState == "VALID"
        and session.sourceMediaState == "PRESENT"
        and age >= timedelta(days=suggest_after_days)
    )
    age_days = max(0, age.days)
    return {"suggestDeletion": eligible, "strongStale": eligible and age_days >= stale_after_days}
