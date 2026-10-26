"""Fixture helpers for Documentation Synthesis V2 tests (WP-18).

`materialize_frames_dir` copies a committed synthetic frame_mapping.json
into a tmp directory and materializes the persisted evidence state a real
previous run would have left on disk:

- deterministic synthetic PNG frames (plain colored screens, some
  near-identical for perceptual-hash dedup tests, one visually distinct);
- `manual/steps.json` carrying the persisted OCR evidence (compat evidence
  source), so V2 reads OCR without ever running pytesseract.

Mock synthesis providers return frozen structured JSON and cite REAL
evidence ids parsed from the deterministic request payload — no LLM, no
network (PLAN WP-18).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

FIXTURES_DIR = Path(__file__).resolve().parent

_BASE_COLORS = {
    "kt_session": (62, 96, 132),
    "tutorial": (34, 120, 76),
    "reference_meeting": (120, 62, 34),
}


def load_fixture(fixture: str) -> dict:
    filename = {
        "kt_session": "kt_session_frame_mapping.json",
        "tutorial": "tutorial_frame_mapping.json",
        "reference_meeting": "reference_meeting_frame_mapping.json",
    }[fixture]
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


def load_fixture_ocr(fixture: str) -> dict[str, str]:
    from tests.fixtures.documentation_v2.build_fixtures import BUILDERS

    builders = {
        "kt_session": BUILDERS["kt_session_frame_mapping.json"],
        "tutorial": BUILDERS["tutorial_frame_mapping.json"],
        "reference_meeting": BUILDERS["reference_meeting_frame_mapping.json"],
    }
    _, ocr_by_frame = builders[fixture]()
    return ocr_by_frame


def _synthetic_frame(path: Path, base: tuple[int, int, int], variant: int, text: str) -> None:
    img = Image.new("RGB", (320, 200), color=base)
    draw = ImageDraw.Draw(img)
    # Small deterministic per-variant perturbation: near-identical frames for
    # consecutive repeated OCR screens, visibly different otherwise.
    shade = base if variant == 0 else tuple(min(255, c + variant) for c in base)
    draw.rectangle((8, 8, 311, 191), fill=shade, outline=(20, 20, 20), width=2)
    draw.text((16, 16), text[:40], fill=(240, 240, 240))
    img.save(path)


def materialize_frames_dir(fixture: str, tmp_path: Path) -> Path:
    """Builds a realistic persisted frames dir for one fixture."""
    mapping = load_fixture(fixture)
    ocr_by_frame = load_fixture_ocr(fixture)
    base = _BASE_COLORS[fixture]

    frames_dir = tmp_path / f"{fixture}_Frames"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_mapping.json").write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # These synthetic recordings contain timestamped speech across their full
    # duration so semantic tests exercise synthesis, while source-gate tests
    # separately cover incomplete transcripts.
    transcript = str(mapping.get("transcription_summary", {}).get("full_transcription", ""))
    utterances = [part.strip() for part in re.split(r"(?<=[.!?])\s+", transcript) if part.strip()]
    duration = float(mapping.get("video_info", {}).get("duration", 0))
    if utterances and duration > 0:
        interval = duration / len(utterances)
        segments = [
            {"id": str(index), "start": index * interval, "end": min(duration, index * interval + interval * 0.8), "text": text}
            for index, text in enumerate(utterances)
        ]
        (frames_dir.parent / f"{Path(mapping['video_info']['name']).stem}_segments.json").write_text(
            json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8"
        )

    last_ocr = ""
    variant = 0
    steps = []
    for index, frame in enumerate(mapping["frames"], start=1):
        name = frame["frame_file"]
        text = ocr_by_frame.get(name, "")
        if text and text == last_ocr:
            variant = (variant + 1) % 3  # near-identical repeated screen
        else:
            variant = 0
            last_ocr = text
        _synthetic_frame(frames_dir / name, base, variant, text)
        entry = mapping["transcription_mapping"].get(name, {})
        transcript = (entry.get("full_text") or "").strip()
        if transcript and text:
            instruction = f"{transcript}\n\nOn-screen text: {text}"
            evidence_source, confidence = "transcript_ocr", "high"
        elif transcript:
            instruction, evidence_source, confidence = transcript, "transcript", "high"
        elif text:
            instruction, evidence_source, confidence = f"On-screen text: {text}", "ocr", "medium"
        else:
            instruction = "(no transcript or on-screen text captured near this moment — review evidence before trusting this step)"
            evidence_source, confidence = "none", "low"
        steps.append({
            "id": f"step-{index:04d}",
            "order": index,
            "title": (transcript or text or f"Step at {frame['timestamp_formatted']}")[:70],
            "instruction": instruction,
            "action": None,
            "target": None,
            "timestamp": frame["timestamp"],
            "transcript_ref": transcript,
            "frame_ref": name,
            "confidence": confidence,
            "tags": [],
            "visual_description": None,
            "ocr_text": text or None,
            "evidence_source": evidence_source,
            "reviewed": False,
        })

    manual_dir = frames_dir / "manual"
    manual_dir.mkdir()
    (manual_dir / "steps.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "source": {
                "video_name": mapping["video_info"]["name"],
                "duration": mapping["video_info"]["duration"],
                "language": "en",
                "extraction_method": "smart_scene",
                "generated_at": "2026-01-01T00:00:00+00:00",
            },
            "steps": steps,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return frames_dir
