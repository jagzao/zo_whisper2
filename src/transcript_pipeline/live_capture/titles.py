from __future__ import annotations

import re
from dataclasses import dataclass


_DATE_TIME = re.compile(r"\b(20\d{2}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s*(?:UTC|GMT))\b", re.I)
_SESSION = re.compile(r"\bsession\s*(?:#|no\.?\s*)?(\d+)\b", re.I)
_CATEGORIES = ("compliance", "app support", "application support", "training", "onboarding", "operations")


@dataclass(frozen=True)
class TitleObservation:
    title: str | None
    category: str | None
    session_number: int | None
    displayed_at: str | None
    confidence: float
    status: str
    signature: str | None


def parse_title_text(text: str, ocr_confidence: float = 1.0) -> TitleObservation:
    """Extract visible title metadata without filling in absent values."""
    raw = " ".join((text or "").split())
    try:
        confidence = max(0.0, min(1.0, float(ocr_confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    date_match = _DATE_TIME.search(raw)
    session_match = _SESSION.search(raw)
    category_match = next((value for value in _CATEGORIES if value in raw.lower()), None)
    title_parts = []
    for line in (part.strip() for part in re.split(r"[\r\n]+", text or "")):
        if not line:
            continue
        if _DATE_TIME.search(line):
            continue
        title_parts.append(line)
    title = " ".join(" ".join(title_parts).split()) or None
    has_family = bool(re.search(r"\b(?:AMS\s+KAP|compliance|app(?:lication)?\s+support|training|onboarding|operations)\b", raw, re.I))
    complete = bool(title and has_family and session_match)
    confidence = min(confidence, 0.99) if complete else min(confidence, 0.6)
    signature = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() if title else None
    status = "CANDIDATE" if complete and confidence >= 0.65 else "NEEDS_TITLE_REVIEW"
    return TitleObservation(
        title=title,
        category=category_match.title() if category_match else None,
        session_number=int(session_match.group(1)) if session_match else None,
        displayed_at=date_match.group(1) if date_match else None,
        confidence=confidence,
        status=status,
        signature=signature,
    )


class MultiFrameTitleConfirmer:
    """Require stable title evidence across independent video samples."""

    def __init__(self, stable_samples: int = 2, minimum_confidence: float = 0.65):
        if stable_samples < 2:
            raise ValueError("stable_samples must be at least 2")
        self.stable_samples = stable_samples
        self.minimum_confidence = minimum_confidence
        self._candidate: str | None = None
        self._count = 0
        self._current: str | None = None

    def observe(self, observation: TitleObservation) -> dict:
        signature = observation.signature
        if not signature or observation.confidence < self.minimum_confidence:
            self._candidate = None
            self._count = 0
            return {"status": "NEEDS_TITLE_REVIEW", "confirmed": False, "boundary": False, "count": 0}
        if signature == self._candidate:
            self._count += 1
        else:
            self._candidate = signature
            self._count = 1
        if self._count < self.stable_samples:
            return {"status": "CANDIDATE", "confirmed": False, "boundary": False, "count": self._count}
        boundary = self._current is not None and signature != self._current
        self._current = signature
        return {"status": "CONFIRMED", "confirmed": True, "boundary": boundary, "count": self._count}
