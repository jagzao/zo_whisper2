"""Local OCR and conservative frame triage with source-frame provenance."""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageStat
    from pytesseract import Output
except ImportError:  # pragma: no cover - optional local OCR installation
    Image = ImageOps = ImageStat = pytesseract = Output = None


VISUAL_TYPES = {
    "ARCHITECTURE_DIAGRAM", "FLOW_DIAGRAM", "APPLICATION_UI", "ADMIN_SCREEN",
    "CLOUD_PORTAL", "CONFIGURATION", "DATABASE", "CODE_OR_SCRIPT", "TABLE",
    "PRESENTATION_SLIDE", "ERROR_MESSAGE", "MEETING_GALLERY", "BLACK_OR_EMPTY", "OTHER",
}
OCR_STATUSES = {"SUCCESS", "NO_TEXT", "LOW_CONFIDENCE", "FAILED", "NOT_REQUIRED"}
SELECTION_REASONS = {"SCENE_CHANGE", "OCR_CHANGE", "TOPIC_BOUNDARY", "ARCHITECTURE", "PROCEDURE", "ERROR", "UNIQUE_UI", "OTHER"}
_RETRY_CONFIGS = ("--psm 6", "--psm 11", "--psm 11")


def _is_black(path: Path) -> bool:
    if Image is None:
        return False
    try:
        with Image.open(path) as source:
            image = source.convert("L")
            width, height = image.size
            center = image.crop((width * 0.25, height * 0.2, width * 0.75, height * 0.75)).resize((32, 24))
            stats = ImageStat.Stat(center)
            return stats.mean[0] < 50 and stats.stddev[0] < 35
    except Exception:
        return False


def _has_centered_speaker_tile(path: Path, text: str) -> bool:
    if Image is None or len(text.strip()) > 80 or not text.strip():
        return False
    try:
        with Image.open(path) as source:
            gray = source.convert("L")
            width, height = gray.size
            x0, x1 = int(width * 0.3), int(width * 0.7)
            y0, y1 = int(height * 0.22), int(height * 0.72)
            center = gray.crop((x0, y0, x1, y1))
            bright = center.point(lambda pixel: 255 if pixel >= 180 else 0)
            bounds = bright.getbbox()
            center_stats = ImageStat.Stat(center)
            if not bounds or center_stats.mean[0] > 110 or center_stats.stddev[0] > 55:
                return False
            left, top, right, bottom = bounds
            box_width, box_height = right - left, bottom - top
            aspect = box_width / max(1, box_height)
            occupied = bright.histogram()[255] / (center.width * center.height)
            centered = abs((left + right) / 2 - center.width / 2) < center.width * 0.2
            return centered and 0.65 <= aspect <= 1.4 and 0.004 <= occupied <= 0.12
    except Exception:
        return False


def _ocr_attempts(path: Path) -> tuple[list[tuple[str, str, float]], int, bool]:
    if pytesseract is None or Image is None or not path.is_file():
        return [], 0, True
    try:
        with Image.open(path) as source:
            original = source.convert("RGB")
            enlarged = ImageOps.autocontrast(original.convert("L")).resize(
                (original.width * 2, original.height * 2)
            )
    except Exception:
        return [], 0, True

    results: list[tuple[str, str, float]] = []
    errors = 0
    images = (original, original, enlarged)
    for index, (image, config) in enumerate(zip(images, _RETRY_CONFIGS)):
        try:
            text = pytesseract.image_to_string(image, config=config).strip()
            if text:
                data = pytesseract.image_to_data(image, config=config, output_type=Output.DICT)
                confidences = [float(value) for value in data.get("conf", []) if str(value).strip() not in {"", "-1"}]
                confidence = max(0.0, min(1.0, sum(confidences) / max(1, len(confidences)) / 100.0))
                results.append((text, config, confidence))
                if confidence >= 0.45:
                    return results, index, False
        except Exception:
            errors += 1
    return results, max(0, min(2, len(_RETRY_CONFIGS) - 1)), errors == len(_RETRY_CONFIGS)


def _classify(text: str, confidence: float, black: bool, speaker_tile: bool = False) -> tuple[str, list[str], list[str]]:
    if black:
        return "BLACK_OR_EMPTY", [], []
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    lowered = " ".join(lines).lower()
    if re.search(r"\b(participants?|mute all|waiting room|raise hand)\b", lowered):
        return "MEETING_GALLERY", lines[:20], []
    if speaker_tile:
        return "MEETING_GALLERY", lines[:20], []
    name_lines = []
    for line in lines:
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", line)
        if 2 <= len(words) <= 7 and line == line.strip() and all(word[:1].isupper() or word.isupper() for word in words):
            name_lines.append(words)
    operational_cues = re.search(
        r"\b(regdoc|azure|database|application overview|technical overview|data flow|configuration|environment|support group|lifecycle|api|server|role|permissions|authentication|workflow|subscription|description|department|category|owner)\b",
        lowered,
    )
    word_count = sum(len(re.findall(r"[A-Za-z][A-Za-z'-]*", line)) for line in lines)
    name_word_count = sum(len(words) for words in name_lines)
    if len(name_lines) >= 5 and word_count and name_word_count / word_count >= 0.6 and not operational_cues:
        return "MEETING_GALLERY", lines[:20], []
    if re.search(r"\b(error|exception|unauthorized|access denied|not found|failed)\b", lowered):
        return "ERROR_MESSAGE", lines[:20], [line for line in lines if re.search(r"error|exception|denied|failed", line, re.I)]
    if re.search(r"\b(architecture diagram|system architecture|integration diagram|network diagram)\b", lowered):
        return "ARCHITECTURE_DIAGRAM", lines[:20], []
    if re.search(r"\b(data flow|workflow|process flow)\b|(?:->|\u2192|\u27f6|\u21e2)", lowered):
        return "FLOW_DIAGRAM", lines[:20], []
    if re.search(r"\b(configuration|settings|environment|connection string)\b", lowered):
        return "CONFIGURATION", lines[:20], []
    if re.search(r"\b(database|sql|table|schema|query)\b", lowered):
        return "DATABASE", lines[:20], []
    if re.search(r"\b(select|insert into|create table|from\s+\w+)\b", lowered):
        return "CODE_OR_SCRIPT", lines[:20], []
    if re.search(r"\b(azure|aws|cloud|portal|subscription)\b", lowered):
        return "CLOUD_PORTAL", lines[:20], []
    if text:
        return "APPLICATION_UI", lines[:20], []
    return "OTHER", lines[:20], []


def _application_for(text: str) -> str:
    lowered = text.lower()
    regdoc = bool(re.search(r"\b(pg\s*)?regdoc\b|pgregdoc\.com", lowered))
    payments = bool(re.search(r"panelist payments|\bcprt\b|north america central product research", lowered))
    if regdoc and payments:
        return "BOTH"
    if regdoc:
        return "PG_REGDOC"
    if payments:
        return "NA_CPRT_PANELIST_PAYMENTS"
    return "SESSION_GENERAL"


def _normalize_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _topic_for(visual_type: str, application: str) -> str:
    return f"{visual_type}:{application}"


def _extract_explicit_graph(text: str, provenance: dict[str, Any]) -> dict[str, Any]:
    edge_pattern = re.compile(r"([A-Za-z0-9][A-Za-z0-9 ._/-]{1,50}?)\s*(?:->|\u2192|\u27f6|\u21e2)\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{1,50})")
    edges = []
    nodes = {}
    for line in text.splitlines():
        match = edge_pattern.search(line.strip())
        if not match:
            continue
        source, target = (re.sub(r"\s+", " ", value).strip(" .") for value in match.groups())
        if not source or not target:
            continue
        nodes[source.lower()] = source
        nodes[target.lower()] = target
        edges.append({"source": source, "target": target, "label": None, "provenance": dict(provenance)})
    return {
        "nodes": [{"id": re.sub(r"\W+", "_", label.lower()).strip("_") or f"node_{i}", "label": label, "provenance": dict(provenance)} for i, label in enumerate(nodes.values())],
        "edges": edges,
        "labels": list(nodes.values()),
        "source_frames": [dict(provenance)] if edges else [],
    }


def analyze_frame(
    frame: dict[str, Any], frames_dir: Path, *, existing_ocr: str | None = None
) -> dict[str, Any]:
    """Return OCR/classification fields; every output points to its exact frame."""
    frame_id = str(frame.get("frame_file") or frame.get("frame_id") or "")
    image_path = frames_dir / frame_id
    timestamp = float(frame.get("timestamp", 0) or 0)
    black = _is_black(image_path)
    retries = 0
    engine = "tesseract"
    if black:
        status, text, confidence = "NOT_REQUIRED", "", None
    elif existing_ocr:
        status, text, confidence = "LOW_CONFIDENCE", existing_ocr, None
        engine = "persisted"
    else:
        attempts, retries, failed = _ocr_attempts(image_path)
        if attempts:
            text, _, confidence = max(attempts, key=lambda result: (result[2], len(result[0])))
            status = "SUCCESS" if confidence >= 0.45 else "LOW_CONFIDENCE"
        elif failed:
            status, text, confidence = "FAILED", "", None
        else:
            status, text, confidence = "NO_TEXT", "", None
    transcript_text = str(frame.get("transcript_text") or "")
    speaker_tile = _has_centered_speaker_tile(image_path, text) if not black else False
    visual_type, labels, errors = _classify(text, confidence or 0.0, black, speaker_tile)
    normalized = _normalize_text(text)
    provenance = {"frame_id": frame_id, "timestamp": timestamp, "image_path": str(image_path)}
    graph = _extract_explicit_graph(text, provenance)
    application = _application_for(f"{text} {transcript_text}")
    return {
        "frame_id": frame_id,
        "timestamp": timestamp,
        "ocr_status": status,
        "ocr_text": text,
        "ocr_confidence": confidence,
        "retry_count": retries,
        "engine": engine if status != "NOT_REQUIRED" else None,
        "source_image": str(image_path),
        "visual_type": visual_type,
        "title": labels[0] if labels else None,
        "application": application,
        "topic": _topic_for(visual_type, application),
        "topic_title": labels[0] if labels else None,
        "transcript_text": transcript_text,
        "visible_components": [],
        "visible_labels": labels,
        "actors": [],
        "relationships": [],
        "data_flows": [],
        "configuration_fields": [],
        "error_messages": errors,
        "operational_actions": [],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "labels": graph["labels"],
        "source_frames": graph["source_frames"],
        "confidence": confidence or 0.0,
        "provenance": provenance,
        "source_image_size": image_path.stat().st_size if image_path.is_file() else None,
        "source_image_mtime_ns": image_path.stat().st_mtime_ns if image_path.is_file() else None,
        "visual_analysis_status": "NEEDS_REVIEW",
        "selected": False,
        "selection_reason": None,
        "ocr_text_signature": hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16],
        "perceptual_signature": None,
        "unique_information": [],
        "duplicate_of": None,
    }


def analyze_frames(
    frames: list[dict[str, Any]],
    frames_dir: Path,
    *,
    phash_threshold: int = 6,
    existing_ocr: dict[str, Any] | None = None,
    source_video: str | None = None,
) -> dict[str, Any]:
    """Select knowledge-bearing screen changes and suppress only true duplicates."""
    from transcript_pipeline.documentation.screenshots import _hamming, _pillow_ahash

    enriched_frames = []
    for frame in frames:
        frame_id = str(frame.get("frame_file") or frame.get("frame_id") or "")
        transcript_entry = frame.get("transcript_text")
        if not transcript_entry:
            transcript_entry = str(frame.get("full_text") or "")
        enriched_frames.append({**frame, "transcript_text": transcript_entry, "frame_file": frame_id})
    records = []
    for frame in sorted(enriched_frames, key=lambda item: float(item.get("timestamp", 0))):
        frame_id = str(frame.get("frame_file"))
        cached = (existing_ocr or {}).get(frame_id)
        if isinstance(cached, str):
            cached = None
        if isinstance(cached, dict) and cached.get("ocr_status") in {"FAILED", "LOW_CONFIDENCE"}:
            cached = None
        if isinstance(cached, dict):
            record = analyze_frame(frame, frames_dir, existing_ocr=str(cached.get("ocr_text") or ""))
            for field in ("ocr_status", "ocr_confidence", "retry_count", "engine"):
                if field in cached:
                    record[field] = cached[field]
            record["confidence"] = record.get("ocr_confidence") or 0.0
        else:
            record = analyze_frame(frame, frames_dir, existing_ocr=cached)
        records.append(record)

    selected: list[dict[str, Any]] = []
    duplicate_count = 0
    for record in records:
        normalized = _normalize_text(record["ocr_text"])
        words = set(normalized.split())
        if record["visual_type"] in {"BLACK_OR_EMPTY", "MEETING_GALLERY"}:
            continue
        image_hash = _pillow_ahash(Path(record["source_image"]))
        record["perceptual_signature"] = f"{image_hash:016x}" if image_hash is not None else None
        comparisons = []
        for prior in selected:
            prior_hash = int(prior["perceptual_signature"], 16) if prior["perceptual_signature"] else None
            distance = _hamming(image_hash, prior_hash) if image_hash is not None and prior_hash is not None else 64
            text_similarity = SequenceMatcher(None, normalized, _normalize_text(prior["ocr_text"])).ratio()
            comparisons.append((distance, text_similarity, prior))
        similar = [item for item in comparisons if item[0] <= phash_threshold]
        duplicate = next((item for item in similar if item[1] >= 0.85), None)
        if normalized:
            exact = next((prior for prior in selected if normalized == _normalize_text(prior["ocr_text"])), None)
            duplicate = duplicate or ((64, 1.0, exact) if exact else None)
        if duplicate:
            record["duplicate_of"] = duplicate[2]["frame_id"]
            record["selection_reason"] = None
            duplicate_count += 1
            continue

        nearest = min(comparisons, key=lambda item: item[0])[2] if comparisons else None
        prior_words = set(_normalize_text(nearest["ocr_text"]).split()) if nearest else set()
        record["unique_information"] = sorted(words - prior_words) if words else []
        if record["visual_type"] == "ERROR_MESSAGE":
            reason = "ERROR"
        elif record["visual_type"] in {"ARCHITECTURE_DIAGRAM", "FLOW_DIAGRAM"}:
            reason = "ARCHITECTURE"
        elif re.search(r"\b(click|select|choose|enter|save|submit|open|configure)\b", record["transcript_text"], re.I):
            reason = "PROCEDURE"
        elif nearest and record["topic"] != nearest["topic"]:
            reason = "TOPIC_BOUNDARY"
        elif nearest and record["unique_information"]:
            reason = "OCR_CHANGE"
        elif not nearest:
            reason = "SCENE_CHANGE"
        else:
            reason = "UNIQUE_UI"
        record["selected"] = bool(
            record["ocr_text"] and record["ocr_status"] in {"SUCCESS", "LOW_CONFIDENCE"}
        )
        record["selection_reason"] = reason if record["selected"] else None
        if record["selected"]:
            selected.append(record)

    meaningful = [item for item in records if item["visual_type"] not in {"BLACK_OR_EMPTY", "MEETING_GALLERY"}]
    topics = sorted({item["topic"] for item in meaningful if item["topic"]})
    covered_topics = sorted({
        item["topic"] for item in selected
        if item["topic"] and item["ocr_status"] == "SUCCESS"
    })
    uncovered_topics = sorted(set(topics) - set(covered_topics))
    diagrams = []
    for record in selected:
        if not record["edges"]:
            continue
        node_ids = {node["label"]: node["id"] for node in record["nodes"]}
        lines = ["flowchart LR"]
        lines.extend(f'    {node["id"]}["{node["label"].replace(chr(34), chr(39))}"]' for node in record["nodes"])
        lines.extend(f'    {node_ids[edge["source"]]} --> {node_ids[edge["target"]]}' for edge in record["edges"])
        diagrams.append({
            "diagram_id": f"diagram-{record['frame_id']}",
            "mermaid": "\n".join(lines),
            "source_video": source_video,
            "timestamps": [record["timestamp"]],
            "source_frames": [record["provenance"]],
        })
    return {
        "schema_version": 1,
        "status": "NEEDS_REVIEW" if not records else "PARTIAL",
        "frame_count": len(records),
        "technical_frame_count": sum(item["visual_type"] not in {"BLACK_OR_EMPTY", "MEETING_GALLERY"} for item in records),
        "meaningful_visual_count": len(meaningful),
        "selected_count": len(selected),
        "suppressed_duplicate_count": duplicate_count,
        "suppressed_gallery_count": sum(item["visual_type"] == "MEETING_GALLERY" for item in records),
        "suppressed_black_count": sum(item["visual_type"] == "BLACK_OR_EMPTY" for item in records),
        "visual_topics_discovered": topics,
        "visual_topics_covered": covered_topics,
        "visual_topics_uncovered": uncovered_topics,
        "visual_coverage_gate": "PASS" if not uncovered_topics else "FAIL",
        "derived_diagrams": diagrams,
        "frames": records,
    }
