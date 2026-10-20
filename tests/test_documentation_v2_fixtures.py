"""DV2-48 — committed fixtures contain only synthetic organizations/apps/
screens; no real client data (TEST-MATRIX, AC-21)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.fixtures.documentation_v2 import FIXTURES_DIR, materialize_frames_dir

# Real-world tokens that must never appear in committed synthetic fixtures.
FORBIDDEN_TOKENS = (
    "procter", "gamble", "p&g", "pg_briefing", "safeguard", "gillette", "ariel",
    "downy", "tide", "pampers", "head & shoulders", "olay", "oral-b", "braun",
    "always", "gillete", "vicks", "charmin", "bounce", "swiffer", "mr. clean",
    "crest", "dawn", "febreze", "gain", "secret", "sk-ii",
    # real internal system names observed in the audit sample are NOT
    # fixtures material; anything client-identifying stays out.
)
ALLOWED_TEST_FIXTURE_TOKENS = ("p-g",)  # contract fixture keys in tests/knowledge, not V2 fixtures

SYNTHETIC_TOKENS = ("acme corp", "gadgetplus", "nimbusdesk", "flowdesk")


def _fixture_payloads() -> dict[str, str]:
    payloads = {}
    for path in sorted(FIXTURES_DIR.glob("*_frame_mapping.json")):
        payloads[path.name] = path.read_text(encoding="utf-8").lower()
    return payloads


def test_dv2_48_fixtures_contain_no_client_names_or_brands():
    payloads = _fixture_payloads()
    assert payloads, "committed V2 fixtures must exist"
    for name, content in payloads.items():
        for token in FORBIDDEN_TOKENS:
            if token in ALLOWED_TEST_FIXTURE_TOKENS:
                continue
            pattern = rf"\b{re.escape(token)}"
            assert not re.search(pattern, content), f"forbidden token {token!r} in {name}"


def test_dv2_48_fixture_organizations_are_synthetic():
    payloads = _fixture_payloads()
    everything = "\n".join(payloads.values())
    assert "acme corp" in everything
    assert "gadgetplus" in everything


def test_dv2_48_fixture_images_are_generated_screens_only(tmp_path):
    """The materialized frames are deterministic synthetic PNGs — no real
    screenshots can sneak into the committed tree because images are never
    committed at all."""
    committed_images = [
        p for p in FIXTURES_DIR.rglob("*")
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".wav"}
    ]
    assert committed_images == [], "V2 fixtures must commit no binary media"
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    assert len(list(frames_dir.glob("frame_*.png"))) == 45


def test_dv2_48_no_fixture_text_matches_real_transcript_patterns():
    payloads = _fixture_payloads()
    everything = "\n".join(payloads.values())
    # No filename/brand leak patterns typical of real recordings.
    assert not re.search(r"\b(pra|la590|gid\s?\d+)\b", everything)
    # Every media name in the fixtures is a synthetic one.
    for name, content in payloads.items():
        data = json.loads(FIXTURES_DIR.joinpath(name).read_text(encoding="utf-8"))
        media = data["video_info"]["name"]
        assert any(token in media for token in SYNTHETIC_TOKENS) or "acme" in media, (
            f"{name}: non-synthetic media name {media!r}"
        )


@pytest.mark.parametrize("fixture", ["kt_session", "tutorial", "reference_meeting"])
def test_dv2_48_all_three_fixture_shapes_load(tmp_path, fixture):
    frames_dir = materialize_frames_dir(fixture, tmp_path)
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    assert mapping["frames"]
    assert mapping["video_info"]["duration"] > 0
