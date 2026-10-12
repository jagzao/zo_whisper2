"""PLV5 implementation summary tests (TEST-MATRIX PLV5-I08, T05)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import implementation_summary as isum  # noqa: E402


def _payload(**overrides) -> dict:
    base = dict(
        contract_id="RESUME-PLV5-POWER-LOSS-20261010",
        branch="feat/project-lead-v4-autonomous-delivery",
        start_sha="bea8064",
        end_sha="3623bce",
        changed_files=["scripts/model_router.py", "scripts/ram_gate.py"],
        selected_model="zai-coding-plan/glm-5.2",
        unit_result="PASS",
        lint_result="PASS",
        typecheck_result="PASS",
        blockers=[],
        terminal_state="READY_FOR_CHATGPT_REVIEW",
    )
    base.update(overrides)
    return base


def test_i08_summary_written_as_json_and_md(tmp_path: Path):
    payload = isum.build_summary(**_payload())
    json_path, md_path = isum.write_summary(payload, output_dir=tmp_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    for field in isum.REQUIRED_FIELDS:
        assert field in data
    assert data["terminal_state"] == "READY_FOR_CHATGPT_REVIEW"

    md = md_path.read_text(encoding="utf-8")
    assert "contract_id" in md
    assert "READY_FOR_CHATGPT_REVIEW" in md


def test_t05_raw_logs_are_never_embedded(tmp_path: Path):
    noisy = "Traceback (most recent call last):\n  File ...\nE   assert 1 == 0"
    payload = isum.build_summary(**_payload(unit_result=noisy))
    json_path, md_path = isum.write_summary(payload, output_dir=tmp_path)

    json_text = json_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    assert "Traceback" not in json_text
    assert "Traceback" not in md_text
    assert "<redacted:raw-log>" in json_text


def test_long_values_are_truncated_not_dumped(tmp_path: Path):
    huge = "x" * 5000
    payload = isum.build_summary(**_payload(lint_result=huge))
    json_path, _ = isum.write_summary(payload, output_dir=tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["lint_result"]) <= 300
