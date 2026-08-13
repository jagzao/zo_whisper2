import logging

from transcript_pipeline.logging_setup import configure_logging, new_run_id


def _clear_root_handlers() -> list[logging.Handler]:
    """pytest's own logging plugin reinstalls handlers on the root logger
    right before each test body runs (during the "call" phase, after fixture
    setup) — clearing must happen here, inside the test, not in a fixture."""
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers.clear()
    return saved


def test_new_run_id_is_short_and_distinct():
    a, b = new_run_id(), new_run_id()
    assert a != b
    assert len(a) == 8


def test_configure_logging_sets_up_handlers(tmp_path, monkeypatch):
    saved = _clear_root_handlers()
    try:
        monkeypatch.setattr("transcript_pipeline.logging_setup.PROJECT_ROOT", tmp_path)
        run_id = configure_logging("test.log")
        root = logging.getLogger()
        assert len(root.handlers) == 2
        assert run_id
        assert (tmp_path / "test.log").exists()
    finally:
        logging.getLogger().handlers[:] = saved


def test_configure_logging_is_idempotent(tmp_path, monkeypatch):
    saved = _clear_root_handlers()
    try:
        monkeypatch.setattr("transcript_pipeline.logging_setup.PROJECT_ROOT", tmp_path)
        first_run_id = configure_logging("first.log")
        second_run_id = configure_logging("second.log")
        assert first_run_id == second_run_id
        assert not (tmp_path / "second.log").exists()
    finally:
        logging.getLogger().handlers[:] = saved


def test_file_id_defaults_and_can_be_overridden(tmp_path, monkeypatch):
    saved = _clear_root_handlers()
    try:
        monkeypatch.setattr("transcript_pipeline.logging_setup.PROJECT_ROOT", tmp_path)
        configure_logging("test.log")
        logger = logging.getLogger("test_file_id_logger")

        logger.info("no file id")
        adapter = logging.LoggerAdapter(logger, {"file_id": "clip_01"})
        adapter.info("with file id")
        for h in logging.getLogger().handlers:
            h.flush()

        log_content = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "file=-" in log_content
        assert "file=clip_01" in log_content
    finally:
        logging.getLogger().handlers[:] = saved
