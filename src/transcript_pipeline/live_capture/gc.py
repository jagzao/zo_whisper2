"""Read-only media retention suggestions for completed Live Capture chunks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from transcript_pipeline.live_capture.models import ChunkState, SessionStatus
from transcript_pipeline.live_capture.store import ManifestStore


def deletion_candidates(
    videos_root: Path,
    *,
    now: datetime | None = None,
    retention_days: int = 90,
    documentation_exists: Callable[[Path], bool],
) -> list[dict[str, object]]:
    """Return suggestions only; this function never deletes or mutates media."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    store = ManifestStore(videos_root)
    candidates = []
    for session in store.list_sessions():
        if session.status is SessionStatus.ACTIVE:
            continue
        for chunk in session.chunks:
            if chunk.state is not ChunkState.PROCESSED or not chunk.media_extension:
                continue
            media = store.chunk_media_path(session.session_id, chunk.index, chunk.media_extension)
            if not media.is_file() or not documentation_exists(media):
                continue
            try:
                stale_at = datetime.fromtimestamp(max(media.stat().st_mtime, media.stat().st_atime), timezone.utc)
                finalized = datetime.fromisoformat(chunk.finalized_at or chunk.created_at).astimezone(timezone.utc)
            except (OSError, ValueError, TypeError):
                continue
            if max(stale_at, finalized) >= cutoff:
                continue
            candidates.append({
                "session_id": session.session_id,
                "chunk_id": chunk.chunk_id,
                "path": str(media),
                "size_bytes": media.stat().st_size,
                "reasons": ["processed", "documentation_generated", f"unused_over_{retention_days}_days"],
                "requires_confirmation": True,
            })
    return candidates
