"""Local OCR and conservative frame triage with source-frame provenance."""
from __future__ import annotations

import re
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
            center = image.crop((width * 0.1, height * 0.1, width * 0.9, height * 0.85)).resize((32, 24))
            stats = ImageStat.Stat(center)
            return stats.mean[0] < 12 and stats.stddev[0] < 9
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


def _classify(text: str, confidence: float, black: bool) -> tuple[str, list[str], list[str]]:
    if black:
        return "BLACK_OR_EMPTY", [], []
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    lowered = " ".join(lines).lower()
    if re.search(r"\b(participants?|mute all|waiting room|raise hand)\b", lowered):
        return "MEETING_GALLERY", lines[:20], []
    if re.search(r"\b(error|exception|unauthorized|access denied|not found|failed)\b", lowered):
        return "ERROR_MESSAGE", lines[:20], [line for line in lines if re.search(r"error|exception|denied|failed", line, re.I)]
    if re.search(r"\b(architecture|integration|network|service|database|application)\b", lowered):
        return "ARCHITECTURE_DIAGRAM", lines[:20], []
    if re.search(r"\b(configuration|settings|environment|connection string)\b", lowered):
        return "CONFIGURATION", lines[:20], []
    if re.search(r"\b(database|sql|table|schema|query)\b", lowered):
        return "DATABASE", lines[:20], []
    if re.search(r"\b(azure|aws|cloud|portal|subscription)\b", lowered):
        return "CLOUD_PORTAL", lines[:20], []
    if text:
        return "APPLICATION_UI", lines[:20], []
    return "OTHER", lines[:20], []


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
    visual_type, labels, errors = _classify(text, confidence or 0.0, black)
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
        "application": None,
        "visible_components": [],
        "visible_labels": labels,
        "actors": [],
        "relationships": [],
        "data_flows": [],
        "configuration_fields": [],
        "error_messages": errors,
        "operational_actions": [],
        "confidence": confidence or 0.0,
        "provenance": {"frame_id": frame_id, "timestamp": timestamp, "image_path": str(image_path)},
        "visual_analysis_status": "PARTIAL" if status == "SUCCESS" else "NEEDS_REVIEW",
        "selected": False,
        "selection_reason": None,
    }


def analyze_frames(
    frames: list[dict[str, Any]],
    frames_dir: Path,
    *,
    phash_threshold: int = 6,
    existing_ocr: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Select OCR/type changes and suppress black, gallery and near-duplicate frames."""
    from transcript_pipeline.documentation.screenshots import _hamming, _pillow_ahash

    records = [
        analyze_frame(frame, frames_dir, existing_ocr=(existing_ocr or {}).get(str(frame.get("frame_file"))))
        for frame in sorted(frames, key=lambda item: float(item.get("timestamp", 0)))
    ]
    previous_text = ""
    previous_type = ""
    selected_hashes: list[int] = []
    for record in records:
        normalized = re.sub(r"\W+", " ", record["ocr_text"].lower()).strip()
        if record["visual_type"] in {"BLACK_OR_EMPTY", "MEETING_GALLERY"}:
            record["selection_reason"] = None
            continue
        image_hash = _pillow_ahash(Path(record["source_image"]))
        duplicate = bool(image_hash is not None and any(
            _hamming(image_hash, existing) <= phash_threshold for existing in selected_hashes
        ))
        if duplicate or (normalized and normalized == previous_text):
            record["selection_reason"] = None
            continue
        if record["visual_type"] == "ERROR_MESSAGE":
            reason = "ERROR"
        elif record["visual_type"] == "ARCHITECTURE_DIAGRAM":
            reason = "ARCHITECTURE"
        elif record["visual_type"] != previous_type:
            reason = "UNIQUE_UI"
        elif normalized and normalized != previous_text:
            reason = "OCR_CHANGE"
        else:
            reason = "OTHER"
        record["selected"] = bool(record["ocr_status"] == "SUCCESS" and record["ocr_text"])
        record["selection_reason"] = reason if record["selected"] else None
        if record["selected"]:
            previous_text = normalized
            previous_type = record["visual_type"]
            if image_hash is not None:
                selected_hashes.append(image_hash)
    return {
        "schema_version": 1,
        "status": "NEEDS_REVIEW" if not records else (
            "PARTIAL" if any(item["visual_analysis_status"] == "NEEDS_REVIEW" for item in records) else "READY"
        ),
        "frame_count": len(records),
        "selected_count": sum(item["selected"] for item in records),
        "frames": records,
    }
