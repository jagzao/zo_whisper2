from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from unittest import mock

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
