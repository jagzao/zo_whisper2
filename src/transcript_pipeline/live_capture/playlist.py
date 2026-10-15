from __future__ import annotations

import re
import os
import uuid
from io import BytesIO
from pathlib import Path

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.atomic import atomic_write_json, read_json
from transcript_pipeline.live_capture.errors import ValidationError
from transcript_pipeline.live_capture.titles import parse_title_text

PLAYLIST_SCHEMA = 1
STABLE_SAMPLES = 2


def _empty(session_id: str) -> dict:
    return {
        "schemaVersion": PLAYLIST_SCHEMA,
        "sessionId": session_id,
        "candidateSignature": None,
        "candidateCount": 0,
        "reviewCandidateSignature": None,
        "reviewCandidateCount": 0,
        "currentSignature": None,
        "logicalVideos": [],
        "reviewCandidates": [],
    }


class PlaylistService:
    def __init__(self, capture_service):
        self.capture = capture_service

    def _file(self, session_id: str) -> Path:
        return self.capture.store.session_dir(models.validate_session_id(session_id)) / "playlist.json"

    def _load(self, session_id: str) -> dict:
        session = self.capture.get_session(session_id)
        if session.capture_mode != "playlist":
            raise ValidationError("session is not in Continuous Playlist mode")
        path = self._file(session_id)
        data = read_json(path) or _empty(session_id)
        if data.get("schemaVersion") != PLAYLIST_SCHEMA or data.get("sessionId") != session_id:
            raise ValidationError("playlist manifest is malformed")
        return data

    def list(self, session_id: str) -> dict:
        return self._with_mappings(session_id, self._load(session_id))

    def _with_mappings(self, session_id: str, data: dict) -> dict:
        session = self.capture.get_session(session_id)
        current_offset = int(data.get("currentOffsetMs", 0))
        current_sequence = int(data.get("currentFragmentSequence", 0))
        for item in data["logicalVideos"]:
            end_offset = item.get("endOffsetMs")
            if end_offset is None:
                end_offset = current_offset
            end_sequence = item.get("endFragmentSequence")
            if end_sequence is None:
                end_sequence = current_sequence
            start_sequence = int(item.get("startFragmentSequence") or 0)
            item["fragmentIds"] = (
                [models.fragment_id(seq) for seq in range(start_sequence, end_sequence + 1)]
                if end_sequence >= start_sequence else []
            )
            duration_ms = session.chunk_duration_sec * 1000
            first = int(item.get("startOffsetMs", 0)) // duration_ms
            last = max(first, max(0, int(end_offset) - 1) // duration_ms)
            item["processingChunkIds"] = [models.chunk_id(index) for index in range(first, last + 1)]
        return data

    def observe(self, session_id: str, text: str, confidence: float, offset_ms: int, fragment_sequence: int) -> dict:
        for name, value in (("offset_ms", offset_ms), ("fragment_sequence", fragment_sequence)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(f"{name} must be a nonnegative integer")
        data = self._load(session_id)
        observed = parse_title_text(text, confidence)
        data["currentOffsetMs"] = offset_ms
        data["currentFragmentSequence"] = fragment_sequence
        if observed.status == "NEEDS_TITLE_REVIEW":
            signature = observed.signature or re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()[:120]
            if signature and data.get("reviewCandidateSignature") == signature:
                data["reviewCandidateCount"] = int(data.get("reviewCandidateCount", 0)) + 1
            elif signature:
                data["reviewCandidateSignature"] = signature
                data["reviewCandidateCount"] = 1
            if signature and data["reviewCandidateCount"] >= STABLE_SAMPLES:
                existing = next((item for item in data["reviewCandidates"] if item.get("signature") == signature), None)
                if existing:
                    existing["confidence"] = max(existing["confidence"], observed.confidence)
                else:
                    data["reviewCandidates"].append({
                        "id": "review-" + uuid.uuid4().hex[:10],
                        "title": observed.title or "Unknown / Needs review",
                        "category": observed.category,
                        "sessionNumber": observed.session_number,
                        "displayedAt": observed.displayed_at,
                        "confidence": observed.confidence,
                        "status": "NEEDS_TITLE_REVIEW",
                        "signature": signature,
                        "offsetMs": offset_ms,
                        "fragmentSequence": fragment_sequence,
                    })
            data["candidateSignature"] = None
            data["candidateCount"] = 0
            atomic_write_json(self._file(session_id), data)
            return self._with_mappings(session_id, data)

        data["reviewCandidateSignature"] = None
        data["reviewCandidateCount"] = 0
        signature = observed.signature
        if data.get("candidateSignature") == signature:
            data["candidateCount"] = int(data.get("candidateCount", 0)) + 1
        else:
            data["candidateSignature"] = signature
            data["candidateCount"] = 1
            data["candidateOffsetMs"] = offset_ms
            data["candidateFragmentSequence"] = fragment_sequence
        if data["candidateCount"] >= STABLE_SAMPLES:
            if data.get("currentSignature") != signature:
                boundary_offset = int(data.get("candidateOffsetMs", offset_ms))
                boundary_sequence = int(data.get("candidateFragmentSequence", fragment_sequence))
                videos = data["logicalVideos"]
                if videos and videos[-1].get("endOffsetMs") is None:
                    videos[-1]["endOffsetMs"] = boundary_offset
                    videos[-1]["endFragmentSequence"] = boundary_sequence
                logical_id = f"logical-{len(videos) + 1:06d}"
                videos.append({
                    "id": logical_id,
                    "title": observed.title,
                    "category": observed.category,
                    "sessionNumber": observed.session_number,
                    "recordedAt": observed.displayed_at,
                    "confidence": observed.confidence,
                    "status": "CONFIRMED",
                    "signature": signature,
                    "startOffsetMs": boundary_offset,
                    "endOffsetMs": None,
                    "startFragmentSequence": boundary_sequence,
                    "endFragmentSequence": None,
                    "processingChunkIds": [],
                })
                data["currentSignature"] = signature
        atomic_write_json(self._file(session_id), data)
        return self._with_mappings(session_id, data)

    def review(self, session_id: str, logical_id: str, action: str, payload: dict) -> dict:
        data = self._load(session_id)
        videos = data["logicalVideos"]
        index = next((i for i, item in enumerate(videos) if item["id"] == logical_id), None)
        if index is None:
            candidate = next((item for item in data["reviewCandidates"] if item["id"] == logical_id), None)
            if candidate is None or action not in {"rename", "recorded-date"}:
                raise ValidationError("logical video not found")
            if action == "rename":
                title = str(payload.get("title") or "").strip()
                if not title:
                    raise ValidationError("title required")
                candidate["title"] = title[:300]
            else:
                value = str(payload.get("recordedAt") or "").strip()
                if not value:
                    raise ValidationError("recordedAt required")
                candidate["displayedAt"] = value[:64]
            candidate["manuallyReviewed"] = True
            atomic_write_json(self._file(session_id), data)
            return self._with_mappings(session_id, data)
        item = videos[index]
        if action == "rename":
            title = str(payload.get("title") or "").strip()
            if not title:
                raise ValidationError("title required")
            item["title"] = title[:300]
            item["manuallyReviewed"] = True
        elif action == "recorded-date":
            value = str(payload.get("recordedAt") or "").strip()
            if not value:
                raise ValidationError("recordedAt required")
            item["recordedAt"] = value[:64]
            item["manuallyReviewed"] = True
        elif action == "confirm":
            item["status"] = "CONFIRMED"
            item["manuallyReviewed"] = True
        elif action == "split":
            offset = payload.get("offsetMs")
            if isinstance(offset, bool) or not isinstance(offset, int):
                raise ValidationError("offsetMs must be an integer")
            start = int(item.get("startOffsetMs", 0))
            end = item.get("endOffsetMs")
            if offset <= start or (end is not None and offset >= end):
                raise ValidationError("split offset must be inside the logical video")
            second = dict(item)
            second["id"] = f"logical-{len(videos) + 1:06d}"
            second["startOffsetMs"] = offset
            second["startFragmentSequence"] = payload.get("fragmentSequence", item.get("startFragmentSequence"))
            second["title"] = str(payload.get("title") or item["title"])
            item["endOffsetMs"] = offset
            item["endFragmentSequence"] = second["startFragmentSequence"]
            videos.insert(index + 1, second)
        elif action == "merge":
            if index + 1 >= len(videos):
                raise ValidationError("logical video has no following neighbor")
            following = videos.pop(index + 1)
            item["endOffsetMs"] = following.get("endOffsetMs")
            item["endFragmentSequence"] = following.get("endFragmentSequence")
            item["processingChunkIds"] = sorted(set(item.get("processingChunkIds", [])) | set(following.get("processingChunkIds", [])))
        else:
            raise ValidationError("unsupported review action")
        atomic_write_json(self._file(session_id), data)
        return self._with_mappings(session_id, data)

    def confirm_candidate(self, session_id: str, candidate_id: str) -> dict:
        data = self._load(session_id)
        candidate = next((item for item in data["reviewCandidates"] if item["id"] == candidate_id), None)
        if candidate is None:
            raise ValidationError("title candidate not found")
        videos = data["logicalVideos"]
        if videos and videos[-1].get("endOffsetMs") is None:
            videos[-1]["endOffsetMs"] = candidate["offsetMs"]
            videos[-1]["endFragmentSequence"] = candidate["fragmentSequence"]
        logical = dict(candidate)
        logical.update({
            "id": f"logical-{len(videos) + 1:06d}",
            "status": "CONFIRMED",
            "startOffsetMs": logical.pop("offsetMs"),
            "startFragmentSequence": logical.pop("fragmentSequence"),
            "endOffsetMs": None,
            "endFragmentSequence": None,
            "manuallyReviewed": True,
            "processingChunkIds": [],
        })
        data["logicalVideos"].append(logical)
        data["reviewCandidates"] = [item for item in data["reviewCandidates"] if item["id"] != candidate_id]
        data["currentSignature"] = logical.get("signature")
        atomic_write_json(self._file(session_id), data)
        return self._with_mappings(session_id, data)


def ocr_title_image(image_bytes: bytes) -> tuple[str, float]:
    """Run the existing local Tesseract OCR dependency on one small frame."""
    try:
        import pytesseract
        from PIL import Image
        from pytesseract import Output

        configured_tesseract = os.environ.get("TESSERACT_CMD")
        if configured_tesseract:
            pytesseract.pytesseract.tesseract_cmd = configured_tesseract
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        result = pytesseract.image_to_data(image, output_type=Output.DICT)
        lines: dict[tuple[str, str, str], list[str]] = {}
        scores = []
        for index, (word, raw_score) in enumerate(zip(result.get("text", []), result.get("conf", []))):
            word = str(word).strip()
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue
            if word and score >= 0:
                key = tuple(str(result.get(name, [""] * (index + 1))[index]) for name in ("block_num", "par_num", "line_num"))
                lines.setdefault(key, []).append(word)
                scores.append(score / 100.0)
        text = "\n".join(" ".join(words) for words in lines.values())
        return text, (sum(scores) / len(scores) if scores else 0.0)
    except Exception:
        return "", 0.0
