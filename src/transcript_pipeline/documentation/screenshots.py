"""Representative screenshot selection (SPEC §9, PLAN WP-09).

Screenshots are selected per SEMANTIC SECTION (from the section's evidence
references), never per source frame:

- candidate score: section evidence reference + confidence + reviewed +
  OCR text density + temporal centrality;
- perceptual-hash dedup (ImageHash when installed; a deterministic Pillow
  average-hash otherwise; same-frame path dedup as final fallback) with
  Hamming distance <= 6 by default;
- per-section and global caps;
- graceful deterministic fallback: a missing/failed image never fails
  documentation.

Source frames are NEVER deleted or modified.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.knowledge_models import KnowledgeDocument

logger = logging.getLogger(__name__)

DEFAULT_PHASH_THRESHOLD = 6
DEFAULT_MAX_PER_SECTION = 2
DEFAULT_MAX_TOTAL = 24

try:  # optional, preferred
    import imagehash as _imagehash
    from PIL import Image as _PILImage
    _IMAGEHASH_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    _imagehash = None
    try:
        from PIL import Image as _PILImage
    except ImportError:
        _PILImage = None
    _IMAGEHASH_AVAILABLE = False

try:
    from PIL import Image as _PIL_IMAGE_FOR_FLAG
    _PIL_AVAILABLE = True
    del _PIL_IMAGE_FOR_FLAG
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False


@dataclass(frozen=True)
class ScreenshotPick:
    section_id: str
    evidence_id: str
    frame_ref: str
    source_path: Path
    score: float


@dataclass
class ScreenshotSelection:
    picks: list[ScreenshotPick] = field(default_factory=list)
    dropped_duplicates: int = 0
    phash_mode: str = "path"  # imagehash | pillow | path

    def for_section(self, section_id: str) -> list[ScreenshotPick]:
        return [pick for pick in self.picks if pick.section_id == section_id]


def _pillow_ahash(path: Path) -> int | None:
    """Deterministic 64-bit average hash using Pillow only (fallback when
    the ImageHash package is absent)."""
    if _PILImage is None:
        return None
    try:
        with _PILImage.open(path) as img:
            gray = img.convert("L").resize((8, 8))
            pixels = list(gray.getdata())
        average = sum(pixels) / len(pixels)
        bits = 0
        for pixel in pixels:
            bits = (bits << 1) | (1 if pixel > average else 0)
        return bits
    except Exception as e:  # noqa: BLE001 - unreadable image never fails docs
        logger.debug("[DOCS-V2] ahash failed for %s: %s", path.name, e)
        return None


def _imagehash_value(path: Path) -> int | None:
    if not _IMAGEHASH_AVAILABLE or _PILImage is None:
        return None
    try:
        with _PILImage.open(path) as img:
            return int(_imagehash.phash(img))  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        logger.debug("[DOCS-V2] phash failed for %s: %s", path.name, e)
        return None


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _score_item(item, section_mid: float) -> float:
    confidence = {"high": 3.0, "medium": 2.0, "low": 1.0}.get(item.confidence, 1.0)
    reviewed_bonus = 1.0 if item.reviewed else 0.0
    ocr_density = min(len(item.ocr_excerpt or "") / 40.0, 2.0)
    span = max(section_mid, 1.0)
    centrality = max(0.0, 2.0 - 2.0 * abs(item.timestamp_start - section_mid) / span)
    return confidence + reviewed_bonus + ocr_density + centrality


def select_screenshots(
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    frames_dir: Path,
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    max_per_section: int = DEFAULT_MAX_PER_SECTION,
    phash_threshold: int = DEFAULT_PHASH_THRESHOLD,
    use_phash: bool = True,
) -> ScreenshotSelection:
    """Deterministic representative selection. Never raises; never deletes."""
    by_id = timeline.by_id()
    use_imagehash = use_phash and _IMAGEHASH_AVAILABLE
    use_pillow = use_phash and not use_imagehash and _PIL_AVAILABLE
    mode = "imagehash" if use_imagehash else ("pillow" if use_pillow else "path")

    selected_hashes: list[int] = []
    selected_paths: set[Path] = set()
    picks: list[ScreenshotPick] = []
    dropped = 0

    sections = document.sections or []
    # Procedures also get their evidence frames as candidates.
    section_refs: list[tuple[str, list[str]]] = [
        (section.id, list(section.evidence_refs)) for section in sections
    ]
    for procedure in document.procedures:
        refs = list(procedure.evidence_refs)
        for step in procedure.steps:
            refs.extend(step.evidence_refs)
        section_refs.append((procedure.id, refs))

    for section_id, refs in section_refs:
        section_mid = _refs_midpoint(refs, by_id)
        candidates = []
        for ref in refs:
            item = by_id.get(ref)
            if item is None or not item.frame_ref:
                continue
            path = frames_dir / Path(item.frame_ref).name
            if not path.is_file():
                continue
            candidates.append((item, path))
        # Deterministic ordering: score desc, then chronological.
        candidates.sort(key=lambda pair: (-_score_item(pair[0], section_mid), pair[0].ordinal))

        taken = 0
        for item, path in candidates:
            if taken >= max_per_section:
                break
            if path in selected_paths:
                dropped += 1
                continue
            if use_imagehash or use_pillow:
                digest = _imagehash_value(path) if use_imagehash else _pillow_ahash(path)
                if digest is not None:
                    if any(_hamming(digest, other) <= phash_threshold for other in selected_hashes):
                        dropped += 1
                        continue
                    selected_hashes.append(digest)
            selected_paths.add(path)
            picks.append(ScreenshotPick(
                section_id=section_id,
                evidence_id=item.evidence_id,
                frame_ref=item.frame_ref,
                source_path=path,
                score=_score_item(item, section_mid),
            ))
            taken += 1

    if len(picks) > max_total:
        # Drop the globally lowest-scored picks (stable for equal scores).
        ranked = sorted(picks, key=lambda pick: (-pick.score, pick.section_id, pick.evidence_id))
        keep = {id(pick) for pick in ranked[:max_total]}
        dropped += len(picks) - max_total
        picks = [pick for pick in picks if id(pick) in keep]

    return ScreenshotSelection(picks=picks, dropped_duplicates=dropped, phash_mode=mode)


def _refs_midpoint(refs: list[str], by_id: dict) -> float:
    timestamps = [by_id[r].timestamp_start for r in refs if r in by_id]
    if not timestamps:
        return 0.0
    return sum(timestamps) / len(timestamps)
