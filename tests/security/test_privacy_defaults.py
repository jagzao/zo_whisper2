"""Security-relevant defaults, run as part of the `tests/security/` gate
(see `scripts/security.py::check_path_traversal`, which now runs this whole
directory instead of grepping app.py for magic strings).
"""

import pytest

from transcript_pipeline.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.setattr("transcript_pipeline.settings.load_env", lambda: None)
    for key in (
        "DASHBOARD_HOST", "ALLOW_EXTERNAL_LLM", "FRAME_DESCRIPTIONS",
        "ALLOW_FRAME_UPLOAD",
    ):
        monkeypatch.delenv(key, raising=False)


def test_dashboard_binds_localhost_by_default():
    assert Settings.from_env().dashboard_host == "127.0.0.1"


def test_outbound_llm_disabled_by_default():
    assert Settings.from_env().allow_external_llm is False


def test_frame_descriptions_disabled_by_default():
    assert Settings.from_env().frame_descriptions is False


def test_frame_upload_disabled_by_default():
    assert Settings.from_env().allow_frame_upload is False
