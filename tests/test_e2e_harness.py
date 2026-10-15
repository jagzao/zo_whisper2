from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts import e2e

_SMOKE_SPEC = importlib.util.spec_from_file_location(
    "zmi_smoke_dashboard",
    Path(__file__).resolve().parent / "e2e" / "smoke_dashboard.py",
)
assert _SMOKE_SPEC and _SMOKE_SPEC.loader
_SMOKE = importlib.util.module_from_spec(_SMOKE_SPEC)
_SMOKE_SPEC.loader.exec_module(_SMOKE)


def test_host_e2e_fixture_root_is_scoped_and_does_not_touch_workspace_media(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    host_root = root / "artifacts" / "gates" / "e2e-host-data"
    real_media = root / "Videos" / "owner.mp4"
    real_media.parent.mkdir(parents=True)
    real_media.write_bytes(b"preserve")
    host_root.mkdir(parents=True)
    (host_root / "stale.txt").write_text("test-owned", encoding="utf-8")
    monkeypatch.setattr(e2e, "ROOT", root)
    monkeypatch.setattr(e2e, "HOST_TEST_DATA_ROOT", host_root)

    def fake_run(command, **kwargs):
        assert command[1] == str(root / "docs" / "assets" / "generate_mock_data.py")
        assert kwargs["env"]["ZMI_DATA_ROOT"] == str(host_root.resolve())
        Path(kwargs["env"]["ZMI_DATA_ROOT"], "fixture.generated").write_text("synthetic", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    with mock.patch.object(e2e.subprocess, "run", side_effect=fake_run):
        prepared = e2e.prepare_host_data_root({})

    assert prepared == host_root.resolve()
    assert not (host_root / "stale.txt").exists()
    assert (host_root / "fixture.generated").exists()
    assert real_media.read_bytes() == b"preserve"


def test_host_e2e_fixture_writes_deterministic_synthetic_projects_json(tmp_path, monkeypatch):
    # Regression: the fixture generator creates no projects.json, so the
    # Projects modal listed 0 items and projects_modal_items failed.
    from transcript_pipeline.projects import validate_project

    root = tmp_path / "repo"
    host_root = root / "artifacts" / "gates" / "e2e-host-data"
    host_root.mkdir(parents=True)
    monkeypatch.setattr(e2e, "ROOT", root)
    monkeypatch.setattr(e2e, "HOST_TEST_DATA_ROOT", host_root)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "", "")

    with mock.patch.object(e2e.subprocess, "run", side_effect=fake_run):
        prepared = e2e.prepare_host_data_root({})

    projects_file = prepared / "projects.json"
    assert projects_file.exists()
    first_content = projects_file.read_text(encoding="utf-8")
    projects = json.loads(first_content)["projects"]
    assert len(projects) >= 1
    assert all(validate_project(project) == [] for project in projects)

    with mock.patch.object(e2e.subprocess, "run", side_effect=fake_run):
        e2e.prepare_host_data_root({})
    assert (prepared / "projects.json").read_text(encoding="utf-8") == first_content


def test_folder_visibility_wait_is_bounded_and_checks_four_cards():
    class Locator:
        def count(self):
            return 4

    class Page:
        timeout = None
        expression: str | None = None

        def wait_for_function(self, expression, timeout):
            self.expression = expression
            self.timeout = timeout

        def locator(self, selector):
            assert selector == "#folders .folder"
            return Locator()

    page = Page()
    assert _SMOKE.wait_for_folder_cards(page)
    assert page.timeout == 30000
    assert page.expression is not None
    assert "length === 4" in page.expression


def test_host_e2e_uses_dynamic_loopback_url_not_port_5000(monkeypatch):
    monkeypatch.setattr(e2e, "_available_loopback_port", lambda: 52173)
    env, url = e2e.configure_host_environment({"ZMI_BASE_URL": "http://127.0.0.1:5000"})

    assert url == "http://127.0.0.1:52173"
    assert env["DASHBOARD_HOST"] == "127.0.0.1"
    assert env["DASHBOARD_PORT"] == "52173"
    assert env["ZMI_BASE_URL"] == url
    assert env["ZMI_E2E_EXTERNAL_SERVER"] == "0"
    assert ":5000" not in url
    response = mock.MagicMock()
    response.__enter__.return_value = response
    with mock.patch.object(e2e.urllib.request, "urlopen", return_value=response) as urlopen:
        assert e2e._wait_for_server(url, timeout=0.1)
    assert urlopen.call_args.args[0] == url


def test_external_e2e_keeps_supplied_base_url(monkeypatch):
    monkeypatch.setenv("ZMI_BASE_URL", "http://127.0.0.1:5311")
    monkeypatch.setenv("ZMI_TEST_DATA_ROOT", str(e2e.ROOT / "external-test-root"))
    monkeypatch.setenv("ZMI_E2E_EXTERNAL_SERVER", "1")
    try:
        mod = importlib.reload(e2e)
        assert mod.DASHBOARD_URL == "http://127.0.0.1:5311"
    finally:
        monkeypatch.delenv("ZMI_BASE_URL", raising=False)
        monkeypatch.delenv("ZMI_TEST_DATA_ROOT", raising=False)
        monkeypatch.delenv("ZMI_E2E_EXTERNAL_SERVER", raising=False)
        importlib.reload(e2e)


def test_exited_host_child_cannot_satisfy_readiness():
    child = mock.Mock()
    child.poll.return_value = 1
    with mock.patch.object(e2e.urllib.request, "urlopen", side_effect=AssertionError("must not probe")):
        with pytest.raises(e2e.HostE2EFailure) as exc:
            e2e._wait_for_server("http://127.0.0.1:52173", process=child, output=[])
    assert exc.value.check == "host_e2e_server_startup"


def test_synthetic_preflight_accepts_mock_fixture_names():
    e2e.validate_synthetic_files([{"name": name} for name in e2e.MOCK_MEDIA_FILENAMES])


def test_synthetic_preflight_rejects_unexpected_filename_without_path():
    with pytest.raises(e2e.HostE2EFailure) as exc:
        e2e.validate_synthetic_files([{"name": "gravity_ai_medical.mp4", "path": "C:\\private\\Videos"}])
    assert exc.value.check == "host_e2e_data_isolation"
    assert "C:\\private" not in str(exc.value)


def test_browser_cleanup_does_not_replace_primary_failure():
    class ClosedHandle:
        def close(self):
            raise RuntimeError("TargetClosedError")

    with pytest.raises(ValueError, match="folders_visible"):
        with mock.patch.object(_SMOKE, "_close_safely", wraps=_SMOKE._close_safely):
            from contextlib import ExitStack
            with ExitStack() as cleanup:
                cleanup.callback(_SMOKE._close_safely, ClosedHandle())
                raise ValueError("folders_visible")
