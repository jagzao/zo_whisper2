"""Project-level OpenCode autonomy contract.

These tests guard the runtime layer that Markdown policy alone cannot enforce:
routine question/doom-loop prompts must be disabled for this project.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_opencode_config_denies_routine_owner_prompts():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    permission = config["permission"]
    assert permission["question"] == "deny"
    assert permission["doom_loop"] == "deny"


def test_project_lead_has_no_artificial_steps_limit():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    agent = config.get("agent", {}).get("project-lead", {})
    assert "steps" not in agent
    assert "maxSteps" not in agent
