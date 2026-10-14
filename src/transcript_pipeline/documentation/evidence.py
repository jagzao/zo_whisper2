"""Typed Evidence Plane models for Documentation Synthesis V2 (SPEC §3).

Evidence is immutable captured source material (ADR 0007). This module:

- adapts persisted artifacts (frame_mapping.json transcription data, and the
  legacy ProceduralStep objects from manual/steps.json) into typed
  `EvidenceItem`s WITHOUT mutating the source files;
- resolves transcript evidence with the frozen preference order (SPEC §14):
  1. timestamped saved segments when discoverable,
  2. unique transcription_mapping segments (deduped across frames),
  3. full persisted transcription as a lower-fidelity untimed fallback;
- assigns deterministic evidence ids (`E-001`, `E-002`, ...) from the
  chronological order of the resolved persisted evidence, so unchanged
  persisted evidence always yields the same ids;
- routes low/no-evidence (`evidenceSource="none"`) items into a review queue
  instead of the synthesis fact set.

No OCR, vision, transcription or media I/O happens here: this module only
reads what a previous run already persisted.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.models import ProceduralStep

MAX_EXCERPT_CHARS = 1200

# Fidelity levels of the resolved evidence (DV2-09: untimed fallback is
# explicitly lower fidelity and never gets fake timestamps).
FIDELITY_TIMESTAMPED_SEGMENTS = "timestamped_segments"
FIDELITY_MAPPED_SEGMENTS = "mapped_segments"
FIDELITY_UNTIMED_FULL_TRANSCRIPT = "untimed_full_transcript"


def _bound_excerpt(text: str | None, limit: int = MAX_EXCERPT_CHARS) -> str | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    return text if len(text) <= limit else text[:limit]


def _split_transcript(text: str, limit: int = MAX_EXCERPT_CHARS) -> list[str]:
    normalized = " ".join(text.split())
    chunks: list[str] = []
    start = 0
    while len(normalized) - start > limit:
        end = start + limit
        boundary = normalized.rfind(" ", start, end)
        if boundary > start:
            end = boundary + 1
        chunks.append(normalized[start:end])
        start = end
    if start < len(normalized):
        chunks.append(normalized[start:])
    return chunks


@dataclass(frozen=True)
class EvidenceItem:
    """One captured evidence moment (SPEC §3 EvidenceItem)."""

    evidence_id: str
    ordinal: int
    timestamp_start: float
    timestamp_end: float
    confidence: str
    reviewed: bool
    evidence_source: str
    transcript_excerpt: str | None = None
    ocr_excerpt: str | None = None
    frame_ref: str | None = None
    source_segment_ids: tuple[str, ...] = ()
    source_provenance: str = ""
    untimed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "ordinal": self.ordinal,
            "timestampStart": round(self.timestamp_start, 3),
            "timestampEnd": round(self.timestamp_end, 3),
            "transcriptExcerpt": self.transcript_excerpt,
            "ocrExcerpt": self.ocr_excerpt,
            "frameRef": self.frame_ref,
            "confidence": self.confidence,
            "reviewed": self.reviewed,
            "evidenceSource": self.evidence_source,
            "sourceSegmentIds": list(self.source_segment_ids),
            "sourceProvenance": self.source_provenance,
            "untimed": self.untimed,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=data["evidenceId"],
            ordinal=int(data["ordinal"]),
            timestamp_start=float(data["timestampStart"]),
            timestamp_end=float(data["timestampEnd"]),
            transcript_excerpt=data.get("transcriptExcerpt"),
            ocr_excerpt=data.get("ocrExcerpt"),
            frame_ref=data.get("frameRef"),
            confidence=data.get("confidence", "low"),
            reviewed=bool(data.get("reviewed", False)),
            evidence_source=data.get("evidenceSource", "none"),
            source_segment_ids=tuple(data.get("sourceSegmentIds", [])),
            source_provenance=data.get("sourceProvenance", ""),
            untimed=bool(data.get("untimed", False)),
        )

    def to_ref(self) -> dict[str, Any]:
        """EvidenceRef view (SPEC §3): bounded excerpts only, never the raw
        whole transcript."""
        return {
            "evidenceId": self.evidence_id,
            "timestampStart": round(self.timestamp_start, 3),
            "timestampEnd": round(self.timestamp_end, 3),
            "evidenceSource": self.evidence_source,
            "confidence": self.confidence,
            "reviewed": self.reviewed,
            "frameRef": self.frame_ref,
            "transcriptExcerpt": self.transcript_excerpt,
            "ocrExcerpt": self.ocr_excerpt,
            "sourceSegmentIds": list(self.source_segment_ids),
        }

    def is_placeholder(self) -> bool:
        """Low/no-evidence placeholders (`evidenceSource="none"`): they go to
        the review queue and can never become synthesis facts (AC-07)."""
        return self.evidence_source == "none"


@dataclass
class EvidenceTimeline:
    """Durable Evidence Plane for one processed recording."""

    items: list[EvidenceItem] = field(default_factory=list)
    review_queue: list[EvidenceItem] = field(default_factory=list)
    duration: float = 0.0
    source_media: str = ""
    language: str = "unknown"
    fidelity: str = FIDELITY_TIMESTAMPED_SEGMENTS
    source_hash: str = ""

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def review_required_count(self) -> int:
        return len(self.review_queue)

    def facts(self) -> list[EvidenceItem]:
        """Items allowed to ground synthesis: everything except placeholders
        (DV2-10: none-source items do not become synthesis facts)."""
        return [item for item in self.items if not item.is_placeholder()]

    def by_id(self) -> dict[str, EvidenceItem]:
        return {item.evidence_id: item for item in self.items}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "sourceMedia": self.source_media,
            "duration": self.duration,
            "language": self.language,
            "fidelity": self.fidelity,
            "sourceHash": self.source_hash,
            "items": [item.to_dict() for item in self.items],
            "reviewQueue": [item.to_dict() for item in self.review_queue],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> EvidenceTimeline:
        return EvidenceTimeline(
            items=[EvidenceItem.from_dict(item) for item in data.get("items", [])],
            review_queue=[EvidenceItem.from_dict(item) for item in data.get("reviewQueue", [])],
            duration=float(data.get("duration", 0.0)),
            source_media=data.get("sourceMedia", ""),
            language=data.get("language", "unknown"),
            fidelity=data.get("fidelity", FIDELITY_TIMESTAMPED_SEGMENTS),
            source_hash=data.get("sourceHash", ""),
        )

    def content_hash(self) -> str:
        """Deterministic identity over the resolved evidence content — used
        by knowledge versioning (DV2-37/38) and mutation detection (SPEC §5.10)."""
        payload = json.dumps(self.to_dict()["items"], sort_keys=True, ensure_ascii=False)
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _segment_key(segment: dict[str, Any]) -> str:
    return f"{float(segment.get('start', 0.0)):.3f}-{float(segment.get('end', 0.0)):.3f}-{segment.get('text', '')}"


def _confidence_for(source: str) -> str:
    if source in ("transcript", "transcript_ocr"):
        return "high"
    if source == "ocr":
        return "medium"
    return "low"


def _frame_has_timestamped_segments(entry: dict[str, Any]) -> list[dict[str, Any]]:
    segments = entry.get("transcription_segments") or []
    return [s for s in segments if isinstance(s, dict) and str(s.get("text", "")).strip()]


def build_evidence_timeline(
    mapping_data: dict[str, Any],
    *,
    steps: list[ProceduralStep] | None = None,
    source_media: str = "",
    frames_dir: Path | None = None,
) -> EvidenceTimeline:
    """Builds the EvidenceTimeline from persisted data only.

    Resolution order (SPEC §14):
    1. timestamped segments persisted per frame in
       `frame_mapping.json.transcription_mapping[frame].transcription_segments`;
    2. unique frame-mapped segments — the same deduped view when segments are
       shared across several frames (a segment near multiple frames appears
       in each frame's nearby list; only the first occurrence is kept);
    3. full persisted transcription as an untimed, explicitly lower-fidelity
       fallback (no fake timestamps).

    `steps` (loaded from the persisted, human-editable manual/steps.json)
    contribute the OCR/reviewed evidence captured in the original run —
    without them no visual evidence is invented. Source dicts are never
    mutated.
    """
    video_info = mapping_data.get("video_info", {})
    duration = float(video_info.get("duration", 0.0))
    frames = sorted(mapping_data.get("frames", []), key=lambda f: f.get("timestamp", 0.0))
    transcription_mapping = mapping_data.get("transcription_mapping", {}) or {}
    transcription_summary = mapping_data.get("transcription_summary", {}) or {}
    full_transcription = str(transcription_summary.get("full_transcription", "") or "").strip()
    language = transcription_summary.get("language", "unknown")

    steps_by_frame = {step.frame_ref: step for step in (steps or []) if step.frame_ref}

    raw_entries: list[dict[str, Any]] = []
    seen_segment_keys: set[str] = set()
    seen_mapped_texts: set[str] = set()
    used_any_timestamped = False

    saved_segments: list[dict[str, Any]] = []
    media_path = str(video_info.get("path", "") or "")
    segment_candidates = []
    if media_path:
        media = Path(media_path)
        segment_candidates.append(media.parent / f"{media.stem}_segments.json")
    if frames_dir is not None:
        stem = Path(source_media or str(video_info.get("name", ""))).stem
        filename = f"{stem}_segments.json"
        segment_candidates.extend((frames_dir / filename, frames_dir.parent / filename, frames_dir.parent.parent / filename))
        try:
            from transcript_pipeline.config import TRANSCRIPTIONS_DIR
            segment_candidates.extend((
                Path(TRANSCRIPTIONS_DIR) / frames_dir.parent.name / filename,
                Path(TRANSCRIPTIONS_DIR) / frames_dir.parent.parent.name / filename,
                Path(TRANSCRIPTIONS_DIR) / filename,
            ))
        except ImportError:
            pass
    for candidate in dict.fromkeys(segment_candidates):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            values = payload.get("segments", []) if isinstance(payload, dict) else []
            saved_segments = [
                value for value in values
                if isinstance(value, dict) and str(value.get("text", "")).strip()
                and value.get("start") is not None and value.get("end") is not None
            ]
            if saved_segments:
                break
        except (OSError, ValueError, TypeError):
            continue

    if saved_segments:
        for segment in saved_segments:
            raw_entries.append({
                "start": float(segment["start"]), "end": float(segment["end"]),
                "transcript": str(segment["text"]).strip(), "ocr": None, "frame": None,
                "reviewed": False, "provenance": "saved_timestamped_segments",
                "segment_ids": [str(segment.get("id", segment.get("segment_id"))) ] if segment.get("id", segment.get("segment_id")) is not None else [],
            })
        used_any_timestamped = True
        seen_segment_keys.update(_segment_key(segment) for segment in saved_segments)

    for frame in frames:
        frame_file = frame.get("frame_file", "")
        timestamp = float(frame.get("timestamp", 0.0))
        entry = transcription_mapping.get(frame_file, {}) or {}
        step = steps_by_frame.get(frame_file)

        segments = [] if saved_segments else _frame_has_timestamped_segments(entry)
        transcript_text = str(entry.get("full_text", "") or "").strip()
        # OCR evidence only from what a previous run already persisted.
        ocr_text = (step.ocr_text if step else None) or None
        reviewed = bool(step.reviewed) if step else False

        if segments:
            # 1. timestamped saved segments (deduped across frames).
            for segment in segments:
                key = _segment_key(segment)
                if key in seen_segment_keys:
                    continue
                seen_segment_keys.add(key)
                seg_start = float(segment.get("start", timestamp))
                seg_end = float(segment.get("end", timestamp))
                raw_entries.append({
                    "start": seg_start,
                    "end": seg_end,
                    "transcript": str(segment.get("text", "")).strip(),
                    "ocr": ocr_text,
                    "frame": frame_file,
                    "timestamp": timestamp,
                    "reviewed": reviewed,
                    "provenance": "frame_mapping.transcription_mapping.transcription_segments",
                })
            used_any_timestamped = True
            if ocr_text:
                # OCR captured on this frame is its own evidence moment.
                raw_entries.append({
                    "start": timestamp,
                    "end": timestamp,
                    "transcript": None,
                    "ocr": ocr_text,
                    "frame": frame_file,
                    "timestamp": timestamp,
                    "reviewed": reviewed,
                    "provenance": "steps.json.ocr_text",
                })
        elif transcript_text and not saved_segments:
            # 2. frame-mapped segment text without persisted start/end: the
            # frame PTS is real captured alignment, not a fabricated timestamp.
            # The same segment text mapped to several nearby frames is
            # recovered once (unique frame-mapped segments, DV2-08).
            text_key = " ".join(transcript_text.lower().split())
            if text_key in seen_mapped_texts:
                if ocr_text:
                    # The frame itself still contributes its own OCR moment.
                    raw_entries.append({
                        "start": timestamp,
                        "end": timestamp,
                        "transcript": None,
                        "ocr": ocr_text,
                        "frame": frame_file,
                        "timestamp": timestamp,
                        "reviewed": reviewed,
                        "provenance": "steps.json.ocr_text",
                    })
                continue
            seen_mapped_texts.add(text_key)
            raw_entries.append({
                "start": timestamp,
                "end": timestamp,
                "transcript": transcript_text,
                "ocr": ocr_text,
                "frame": frame_file,
                "timestamp": timestamp,
                "reviewed": reviewed,
                "provenance": "frame_mapping.transcription_mapping.full_text",
            })
        elif ocr_text:
            raw_entries.append({
                "start": timestamp,
                "end": timestamp,
                "transcript": None,
                "ocr": ocr_text,
                "frame": frame_file,
                "timestamp": timestamp,
                "reviewed": reviewed,
                "provenance": "steps.json.ocr_text",
            })
        else:
            # Placeholder: review queue, never a synthesis fact.
            raw_entries.append({
                "start": timestamp,
                "end": timestamp,
                "transcript": None,
                "ocr": None,
                "frame": frame_file,
                "timestamp": timestamp,
                "reviewed": reviewed,
                "provenance": "no captured evidence near this frame",
                "placeholder": True,
            })

    fidelity = FIDELITY_TIMESTAMPED_SEGMENTS if used_any_timestamped else FIDELITY_MAPPED_SEGMENTS
    has_transcript = any(entry.get("transcript") for entry in raw_entries)
    if not has_transcript and full_transcription:
        # 3. untimed full-transcript fallback: honest 0..duration span, no
        # fabricated per-item timestamps (DV2-09). Placeholder frames stay
        # queued for review; they are not fake facts.
        raw_entries.append({
            "start": 0.0,
            "end": duration,
            "transcript": full_transcription,
            "ocr": None,
            "frame": None,
            "timestamp": None,
            "reviewed": False,
            "provenance": "frame_mapping.transcription_summary.full_transcription",
            "untimed": True,
        })
        fidelity = FIDELITY_UNTIMED_FULL_TRANSCRIPT

    expanded_entries: list[dict[str, Any]] = []
    for entry in raw_entries:
        transcript = entry.get("transcript")
        if not transcript or len(transcript) <= MAX_EXCERPT_CHARS:
            expanded_entries.append(entry)
            continue
        for index, chunk in enumerate(_split_transcript(str(transcript))):
            expanded_entries.append({
                **entry,
                "transcript": chunk,
                "ocr": entry.get("ocr") if index == 0 else None,
                "frame": entry.get("frame") if index == 0 else None,
                "preserve_transcript_boundary": True,
            })
    raw_entries = expanded_entries

    # Deterministic chronological order -> deterministic E-### ids.
    raw_entries.sort(key=lambda e: (e["start"], e["end"], e["frame"] or ""))

    items: list[EvidenceItem] = []
    review: list[EvidenceItem] = []
    for ordinal, entry in enumerate(raw_entries, start=1):
        evidence_id = f"E-{ordinal:03d}"
        if entry.get("placeholder"):
            source = "none"
        elif entry.get("transcript") and entry.get("ocr"):
            source = "transcript_ocr"
        elif entry.get("transcript"):
            source = "transcript"
        elif entry.get("ocr"):
            source = "ocr"
        else:
            source = "none"
        item = EvidenceItem(
            evidence_id=evidence_id,
            ordinal=ordinal,
            timestamp_start=float(entry["start"]),
            timestamp_end=float(entry["end"]),
            transcript_excerpt=(
                entry.get("transcript") if entry.get("preserve_transcript_boundary")
                else _bound_excerpt(entry.get("transcript"))
            ),
            ocr_excerpt=_bound_excerpt(entry.get("ocr")),
            frame_ref=entry.get("frame"),
            confidence=_confidence_for(source) if not entry.get("placeholder") else "low",
            reviewed=bool(entry.get("reviewed", False)),
            evidence_source=source,
            source_provenance=str(entry.get("provenance", "")),
            untimed=bool(entry.get("untimed", False)),
            source_segment_ids=tuple(entry.get("segment_ids", ())),
        )
        items.append(item)
        if item.is_placeholder():
            review.append(item)

    timeline = EvidenceTimeline(
        items=items,
        review_queue=review,
        duration=duration,
        source_media=source_media or str(video_info.get("name", "")),
        language=language,
        fidelity=fidelity,
    )
    timeline.source_hash = timeline.content_hash()
    return timeline


def load_persisted_steps(manual_dir: Path) -> list[ProceduralStep] | None:
    """Loads the persisted manual/steps.json when present (compat evidence
    source, SPEC §10). Returns None when not yet written."""
    steps_path = manual_dir / "steps.json"
    if not steps_path.exists():
        return None
    try:
        payload = json.loads(steps_path.read_text(encoding="utf-8"))
        return [ProceduralStep.from_dict(s) for s in payload.get("steps", [])]
    except (OSError, ValueError, KeyError):
        return None
