"""Deterministic mocked tests for the Docker gate runner (PLAN-ZMI-DKR-001 WP-06).

Covers: gate/command mapping, project/port isolation, compact report fields,
bounded timeouts, and cleanup scoped strictly to the zmi-test-* namespace.
No test here invokes a real `docker` binary.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import docker_gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
from scripts import e2e as e2e_mod  # noqa: E402

PROJECT = "zmi-test-unit"


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _clean_artifacts(monkeypatch):
    build_number = f"docker-test-{os.getpid()}"
    monkeypatch.setenv("BUILD_NUMBER", build_number)
    build_dir = docker_gate.ROOT / "artifacts" / "gates" / f"build-{build_number}"
    shutil.rmtree(build_dir, ignore_errors=True)
    if docker_gate.ARTIFACTS_DIR.exists():
        shutil.rmtree(docker_gate.ARTIFACTS_DIR, ignore_errors=True)
    yield
    if docker_gate.ARTIFACTS_DIR.exists():
        shutil.rmtree(docker_gate.ARTIFACTS_DIR, ignore_errors=True)
    shutil.rmtree(build_dir, ignore_errors=True)


@pytest.fixture
def calls():
    """Patch subprocess.run to record every invocation and succeed."""
    recorded: list[dict] = []

    def _run(cmd, **kwargs):
        recorded.append({"cmd": list(cmd), "kwargs": kwargs})
        return _FakeCompleted(0, "ok", "")

    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_run):
        yield recorded


def _report(gate: str) -> dict:
    return json.loads((docker_gate.ARTIFACTS_DIR / f"{gate}.json").read_text(encoding="utf-8"))


# --- gate registry / mapping -------------------------------------------------

def test_named_gates_registered_with_bounded_timeouts():
    assert set(docker_gate.GATE_FUNCS) == {
        "docker-config",
        "docker-build",
        "docker-smoke",
        "docker-persistence",
        "docker-asr-smoke",
        "docker-e2e",
    }
    assert set(docker_gate.TIMEOUTS) == set(docker_gate.GATE_FUNCS)
    assert all(t > 0 for t in docker_gate.TIMEOUTS.values())


def test_config_gate_maps_to_compose_config_only(calls):
    rc = docker_gate.run_gate("docker-config", project=PROJECT)

    assert rc == 0
    assert len(calls) == 1
    cmd = calls[0]["cmd"]
    assert cmd[:6] == ["docker", "compose", "-f", str(docker_gate.COMPOSE_FILE), "-p", PROJECT]
    assert cmd[6:] == ["--profile", "e2e", "config"]
    # Validation only: nothing is built, started, or torn down.
    for forbidden in ("build", "up", "down", "run", "exec", "prune"):
        assert forbidden not in cmd


def test_build_gate_maps_to_scoped_compose_build(calls):
    rc = docker_gate.run_gate("docker-build", project=PROJECT)

    assert rc == 0
    assert len(calls) == 2  # build both targets, then remove only this project's local images
    assert calls[0]["cmd"][6:] == ["--profile", "e2e", "build"]
    assert calls[1]["cmd"][6:] == ["--profile", "e2e", "down", "--remove-orphans", "-v", "--rmi", "local", "--timeout", "30"]
    env = calls[0]["kwargs"]["env"]
    assert str(docker_gate.TEST_ROOT) in env["ZMI_DATA_PATH"]
    assert not docker_gate.TEST_ROOT.exists()  # no test data created for build


def test_e2e_gate_runs_playwright_service_in_isolated_compose_network(calls):
    rc = docker_gate.run_gate("docker-e2e", project=PROJECT)

    assert rc == 0
    assert len(calls) == 4  # healthy app, synthetic seed, test service, scoped cleanup
    seed = calls[1]["cmd"]
    assert seed[-3:] == ["zmi-e2e", "python", "docs/assets/generate_mock_data.py"]
    run = calls[2]["cmd"]
    assert run[:6] == ["docker", "compose", "-f", str(docker_gate.COMPOSE_FILE), "-p", PROJECT]
    assert run[6:9] == ["--profile", "e2e", "run"]
    assert run[-1] == "zmi-e2e"
    assert "ZMI_BASE_URL=http://127.0.0.1:5000" in run
    assert "ZMI_TEST_DATA_ROOT=/data" in run
    assert "ZMI_E2E_EXTERNAL_SERVER=1" in run
    assert str(docker_gate.TEST_ROOT / PROJECT / "data") in calls[2]["kwargs"]["env"]["ZMI_DATA_PATH"]


def test_e2e_failure_preserves_browser_evidence_before_scoped_cleanup():
    data_root = docker_gate.TEST_ROOT / PROJECT / "data"

    def _run(cmd, **kwargs):
        cmd = list(cmd)
        if "zmi-e2e" in cmd and "docs/assets/generate_mock_data.py" in cmd:
            return _FakeCompleted(0, "seeded", "")
        if "zmi-e2e" in cmd:
            (data_root / "e2e_report.json").write_text('{"status":"FAIL"}', encoding="utf-8")
            (data_root / "dashboard_report.json").write_text('{"checks":[]}', encoding="utf-8")
            screenshots = data_root / "screenshots"
            screenshots.mkdir()
            (screenshots / "failure.png").write_bytes(b"synthetic screenshot")
            return _FakeCompleted(1, "", "synthetic browser failure")
        return _FakeCompleted(0, "ok", "")

    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_run):
        rc = docker_gate.run_gate("docker-e2e", project=PROJECT)

    assert rc == 1
    report = _report("docker-e2e")
    assert report["check"] == "docker_e2e_suite"
    evidence = docker_gate.build_artifacts_dir() / "e2e"
    assert (evidence / "e2e_report.json").read_text(encoding="utf-8") == '{"status":"FAIL"}'
    assert (evidence / "dashboard_report.json").exists()
    assert (evidence / "screenshots" / "failure.png").read_bytes() == b"synthetic screenshot"
    assert not data_root.exists()


def test_compose_e2e_service_uses_test_target_and_app_network():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "zmi-e2e:" in compose
    assert "target: test" in compose
    assert "network_mode: service:zmi" in compose
    assert "condition: service_healthy" in compose
    assert 'ZMI_BASE_URL: http://127.0.0.1:5000' in compose
    assert "${ZMI_DATA_PATH:-./zmi-data}:/data" in compose


def test_mock_data_generator_is_copied_into_playwright_image():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY docs/assets/generate_mock_data.py docs/assets/generate_mock_data.py" in dockerfile


def test_compose_external_llm_opt_in_defaults_false():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert 'ALLOW_EXTERNAL_LLM: "${ALLOW_EXTERNAL_LLM:-false}"' in compose


# --- project / port isolation ------------------------------------------------

def test_project_name_uses_build_id_and_sanitizes():
    assert docker_gate.resolve_project_name(env={"BUILD_ID": "jenkins-42"}) == "zmi-test-jenkins-42"
    weird = docker_gate.resolve_project_name(env={"BUILD_ID": "Job/Name #7!"})
    assert weird.startswith(docker_gate.PROJECT_PREFIX)
    assert docker_gate.PROJECT_NAME_RE.match(weird)


def test_project_name_local_suffix_is_deterministic():
    first = docker_gate.resolve_project_name(env={})
    second = docker_gate.resolve_project_name(env={})
    assert first == second
    assert first.startswith("zmi-test-local-")
    assert docker_gate.PROJECT_NAME_RE.match(first)


def test_project_name_validation_rejects_non_test_names():
    with pytest.raises(ValueError):
        docker_gate.resolve_project_name("production")
    with pytest.raises(ValueError):
        docker_gate.resolve_project_name("zmi-test-BAD_UPPER")


def test_run_gate_rejects_bad_project_without_invoking_docker(calls):
    assert docker_gate.run_gate("docker-smoke", project="production") == 2
    assert calls == []
    assert not docker_gate.ARTIFACTS_DIR.exists()


def test_port_is_deterministic_and_env_overridable():
    assert docker_gate.resolve_port(PROJECT, env={}) == docker_gate.resolve_port(PROJECT, env={})
    assert 5100 <= docker_gate.resolve_port(PROJECT, env={}) < 5900
    assert docker_gate.resolve_port(PROJECT, env={"ZMI_TEST_PORT": "5321"}) == 5321
    with pytest.raises(ValueError):
        docker_gate.resolve_port(PROJECT, env={"ZMI_TEST_PORT": "nope"})


# --- compact report fields ---------------------------------------------------

def test_pass_report_has_required_fields(calls):
    rc = docker_gate.run_gate("docker-config", project=PROJECT)

    assert rc == 0
    data = _report("docker-config")
    assert data["status"] == "PASS"
    assert data["gate"] == "docker-config"
    assert data["check"] == "docker-config"
    assert data["error_signature"] == ""
    assert data["command"].endswith("config")
    assert data["artifact"].endswith("/logs/docker-docker-config.log")
    assert isinstance(data["duration_seconds"], float)
    assert data["timeout_seconds"] == docker_gate.TIMEOUTS["docker-config"]
    assert data["project"] == PROJECT
    assert data["runner"] == "scripts/docker_gate.py"
    # Separate raw log exists and carries the recorded command.
    log = (ROOT / data["artifact"]).read_text(encoding="utf-8")
    assert "[compose_config_valid]" in log


def test_fail_report_carries_check_and_error_signature():
    with mock.patch.object(
        docker_gate.subprocess, "run", return_value=_FakeCompleted(1, "", "Error response from daemon: boom")
    ):
        rc = docker_gate.run_gate("docker-config", project=PROJECT)

    assert rc == 1
    data = _report("docker-config")
    assert data["status"] == "FAIL"
    assert data["check"] == "compose_config_valid"
    assert data["error_signature"] == "Error response from daemon: boom"
    assert data["command"].endswith("config")


def test_unknown_gate_returns_2_without_artifacts(calls):
    assert docker_gate.run_gate("nope") == 2
    assert calls == []
    assert not docker_gate.ARTIFACTS_DIR.exists()


def test_unexpected_gate_exception_still_reports_and_cleans_scoped_project(monkeypatch, calls):
    def explode(_ctx):
        raise RuntimeError("unexpected bounded gate failure")

    monkeypatch.setitem(docker_gate.GATE_FUNCS, "docker-smoke", (explode, True))
    rc = docker_gate.run_gate("docker-smoke", project=PROJECT)

    assert rc == 1
    report = _report("docker-smoke")
    assert report["status"] == "FAIL"
    assert report["check"] == "gate_runner_exception"
    assert "unexpected bounded gate failure" in report["error_signature"]
    log_capture = next(call["cmd"] for call in calls if "logs" in call["cmd"])
    assert log_capture[6:] == ["logs", "--no-color", "--tail", "200", "zmi"]
    cleanup = next(call["cmd"] for call in calls if "down" in call["cmd"])
    assert cleanup[6:9] == ["--profile", "e2e", "down"]
    assert cleanup[cleanup.index("--rmi") + 1] == "local"
    assert not (docker_gate.TEST_ROOT / PROJECT).exists()


# --- bounded timeouts --------------------------------------------------------

def test_timeout_is_bounded_and_reported_as_check():
    seen_timeouts: list[object] = []

    def _slow(cmd, **kwargs):
        seen_timeouts.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 1)

    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_slow):
        rc = docker_gate.run_gate("docker-config", project=PROJECT)

    assert rc == 1
    budget = docker_gate.TIMEOUTS["docker-config"]
    assert all(isinstance(t, (int, float)) and 0 < t <= budget for t in seen_timeouts)
    data = _report("docker-config")
    assert data["status"] == "FAIL"
    assert data["check"] == "timeout"
    assert data["error_signature"].startswith("timeout after")
    assert data["command"].endswith("config")


def test_wait_http_is_bounded_by_deadline():
    def _unreachable(*_args, **_kwargs):
        raise OSError("connection refused")

    start = time.monotonic()
    with mock.patch.object(docker_gate.urllib.request, "urlopen", side_effect=_unreachable):
        with mock.patch.object(docker_gate.time, "sleep"):
            assert docker_gate.wait_http("http://127.0.0.1:59999/api/status", timeout_seconds=0.05) is False
    assert time.monotonic() - start < 5


def _ctx_after_up_shrinks_deadline(offset: float) -> tuple[docker_gate.GateContext, object]:
    """GateContext whose deadline shrinks to `offset` right after compose up."""
    ctx = docker_gate.GateContext(gate="docker-smoke", project=PROJECT, port=5311, timeout=600.0)
    inner = _fake_smoke_run()

    def _run(cmd, **kwargs):
        out = inner(cmd, **kwargs)
        if "up" in cmd:
            ctx.deadline = time.monotonic() + offset
        return out

    return ctx, _run


def test_smoke_http_poll_budget_never_exceeds_small_remaining():
    ctx, _run = _ctx_after_up_shrinks_deadline(0.5)
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_run):
        with mock.patch.object(docker_gate, "wait_http", return_value=True) as wait:
            docker_gate.gate_smoke(ctx)

    assert wait.call_count == 1
    budget = wait.call_args.kwargs["timeout_seconds"]
    assert 0 < budget <= 0.5  # no 5s floor: budget stays within the small remaining time
    assert budget <= docker_gate.HEALTH_TIMEOUT


def test_smoke_http_poll_skipped_and_fails_timeout_when_budget_exhausted():
    ctx, _run = _ctx_after_up_shrinks_deadline(-1.0)
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_run):
        with mock.patch.object(docker_gate, "wait_http", return_value=True) as wait:
            with pytest.raises(docker_gate.GateError) as exc:
                docker_gate.gate_smoke(ctx)

    assert wait.call_count == 0
    assert exc.value.check == "timeout"
    assert "/api/status" in exc.value.error_signature


# --- scoped cleanup ----------------------------------------------------------

def test_smoke_gate_cleans_only_its_project_and_data(calls):
    with mock.patch.object(docker_gate, "wait_http", return_value=False):
        rc = docker_gate.run_gate("docker-smoke", project=PROJECT)

    assert rc == 1
    data = _report("docker-smoke")
    assert data["status"] == "FAIL"
    assert data["check"] == "api_status_responds"
    assert data["project"] == PROJECT

    ups = [c for c in calls if "up" in c["cmd"]]
    assert len(ups) == 1
    up_env = ups[0]["kwargs"]["env"]
    assert up_env["ZMI_DATA_PATH"].startswith(str(docker_gate.TEST_ROOT))
    assert up_env["ZMI_PORT"] == str(data["port"])

    downs = [c for c in calls if "down" in c["cmd"]]
    assert len(downs) == 1
    down = downs[0]["cmd"]
    assert down[down.index("-p") + 1] == PROJECT
    assert "-v" in down and "--remove-orphans" in down

    assert not (docker_gate.TEST_ROOT / PROJECT).exists()
    assert data["cleanup"][0]["step"] == "scoped_compose_down"
    assert data["cleanup"][1]["step"] == "scoped_data_cleanup"


# --- docker-smoke matrix -----------------------------------------------------

_SMOKE_RESPONSES: list[tuple[str, int, str, str]] = [
    ("id -u", 0, "10001\n", ""),
    ("ffmpeg -version", 0, "ffmpeg version 6.1.1 Copyright\n", ""),
    ("ffprobe -version", 0, "ffprobe version 6.1.1 Copyright\n", ""),
    ("--list-langs", 0, "List of available languages (3):\neng\nspa\nosd\n", ""),
    ("ALLOW_EXTERNAL_LLM", 0, "false\n", ""),
    ("/app/.zmi-gate-probe", 1, "", "touch: cannot touch '/app/.zmi-gate-probe': Permission denied"),
    ("/data/.zmi-gate-probe", 0, "", ""),
    ("/cache/.zmi-gate-probe", 0, "", ""),
    ("port zmi 5000", 0, "127.0.0.1:5311\n", ""),
]


def _fake_smoke_run(
    overrides: dict[str, _FakeCompleted] | None = None,
    recorded: list[dict] | None = None,
):
    overrides = overrides or {}

    def _run(cmd, **kwargs):
        if recorded is not None:
            recorded.append({"cmd": list(cmd), "kwargs": kwargs})
        text = " ".join(cmd)
        for token, returncode, stdout, stderr in _SMOKE_RESPONSES:
            if token in text:
                fake = overrides.get(token)
                return fake if fake is not None else _FakeCompleted(returncode, stdout, stderr)
        return _FakeCompleted(0, "ok", "")

    return _run


def test_smoke_matrix_passes_with_expected_exec_commands():
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_smoke_run(recorded=recorded)):
        with mock.patch.object(docker_gate, "wait_http", return_value=True):
            rc = docker_gate.run_gate("docker-smoke", project=PROJECT)

    assert rc == 0
    data = _report("docker-smoke")
    assert data["status"] == "PASS"

    cmds = [c["cmd"] for c in recorded]
    execs = [c for c in cmds if c[6:9] == ["exec", "-T", "zmi"]]
    assert len(execs) == 8
    for c in execs:
        assert c[:6] == ["docker", "compose", "-f", str(docker_gate.COMPOSE_FILE), "-p", PROJECT]

    texts = [" ".join(c) for c in cmds]
    assert any(t.endswith(" id -u") for t in texts)
    assert any(" ffmpeg -version" in t for t in texts)
    assert any(" ffprobe -version" in t for t in texts)
    assert any(" tesseract --list-langs" in t for t in texts)
    assert any(" printenv ALLOW_EXTERNAL_LLM" in t for t in texts)
    assert any("touch /app/.zmi-gate-probe" in t for t in texts)
    for target in ("/data", "/cache"):
        assert any(f"touch {target}/.zmi-gate-probe" in t and "rm -f" in t for t in texts)
    port = next(c for c in cmds if c[6:] == ["port", "zmi", "5000"])
    assert port[port.index("-p") + 1] == PROJECT

    up_index = next(i for i, c in enumerate(cmds) if "up" in c)
    first_exec = cmds.index(execs[0])
    assert up_index < first_exec
    assert cmds.index(port) > first_exec

    budget = docker_gate.TIMEOUTS["docker-smoke"]
    for call in recorded:
        assert 0 < call["kwargs"]["timeout"] <= budget

    log = (ROOT / data["artifact"]).read_text(encoding="utf-8")
    for check in (
        "compose_up_healthy",
        "runs_as_nonroot",
        "ffmpeg_version",
        "ffprobe_version",
        "tesseract_langs_eng_spa",
        "allow_external_llm_false",
        "app_unwritable",
        "data_writable",
        "cache_writable",
        "port_loopback",
    ):
        assert f"[{check}]" in log


def test_smoke_app_probe_expected_failure_is_not_gate_failure():
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_smoke_run(recorded=recorded)):
        with mock.patch.object(docker_gate, "wait_http", return_value=True):
            rc = docker_gate.run_gate("docker-smoke", project=PROJECT)

    assert rc == 0
    next(c for c in recorded if "/app/.zmi-gate-probe" in " ".join(c["cmd"]))
    data = _report("docker-smoke")
    assert data["status"] == "PASS"
    assert data["check"] == "docker-smoke"
    log = (ROOT / data["artifact"]).read_text(encoding="utf-8")
    assert "[app_unwritable]" in log
    assert "Permission denied" in log


@pytest.mark.parametrize(
    ("token", "fake", "expected_check"),
    [
        ("id -u", _FakeCompleted(0, "0\n", ""), "runs_as_nonroot"),
        ("id -u", _FakeCompleted(0, "not-a-uid\n", ""), "runs_as_nonroot"),
        ("ffmpeg -version", _FakeCompleted(127, "", "ffmpeg: not found"), "ffmpeg_version"),
        ("ffprobe -version", _FakeCompleted(127, "", "ffprobe: not found"), "ffprobe_version"),
        ("--list-langs", _FakeCompleted(0, "eng\nosd\n", ""), "tesseract_langs_eng_spa"),
        ("ALLOW_EXTERNAL_LLM", _FakeCompleted(0, "true\n", ""), "allow_external_llm_false"),
        ("ALLOW_EXTERNAL_LLM", _FakeCompleted(1, "", "printenv: ALLOW_EXTERNAL_LLM: unset"), "allow_external_llm_false"),
        ("/app/.zmi-gate-probe", _FakeCompleted(0, "", ""), "app_unwritable"),
        ("/data/.zmi-gate-probe", _FakeCompleted(1, "", "touch: Read-only file system"), "data_writable"),
        ("/cache/.zmi-gate-probe", _FakeCompleted(1, "", "touch: Permission denied"), "cache_writable"),
        ("port zmi 5000", _FakeCompleted(0, "0.0.0.0:5311\n", ""), "port_loopback"),
        ("port zmi 5000", _FakeCompleted(0, "", ""), "port_loopback"),
    ],
)
def test_smoke_matrix_failure_reports_expected_check(token, fake, expected_check):
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_smoke_run({token: fake})):
        with mock.patch.object(docker_gate, "wait_http", return_value=True):
            rc = docker_gate.run_gate("docker-smoke", project=PROJECT)

    assert rc == 1
    data = _report("docker-smoke")
    assert data["status"] == "FAIL"
    assert data["check"] == expected_check
    assert data["error_signature"]
    assert data["command"]


# --- docker-persistence matrix ------------------------------------------------

_EXPECTED_FIXTURE_RELS = {
    "projects.json",
    "project_overrides.json",
    "processed_files.json",
    docker_gate.PERSISTENCE_TRANSCRIPT_REL,
    docker_gate.PERSISTENCE_ASSET_REL,
}


def _fresh_status_payload() -> dict:
    """Exactly the dashboard's /api/status schema for a brand-new process."""
    return {
        "running": False,
        "mode": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "log_tail": "",
        "stage": None,
        "stages": {},
    }


def _fake_persistence_run(
    recorded: list[dict],
    corrupt_after_down: str | None = None,
):
    """Fake subprocess.run: `cat` serves the real fixture files the gate wrote.

    `corrupt_after_down` appends to a fixture's content once the mid-gate
    `down` has run, simulating state lost across the recreate.
    """
    state = {"down_seen": False}

    def _run(cmd, **kwargs):
        cmd = list(cmd)
        if "down" in cmd:
            state["down_seen"] = True
        stdout = "ok"
        if "exec" in cmd and "cat" in cmd:
            project = cmd[cmd.index("-p") + 1]
            rel = cmd[cmd.index("cat") + 1][len("/data/"):]
            path = docker_gate.TEST_ROOT / project / "data" / rel
            stdout = path.read_text(encoding="utf-8") if path.exists() else ""
            if corrupt_after_down and state["down_seen"] and rel == corrupt_after_down:
                stdout = f"{stdout} corrupted"
        recorded.append({"cmd": cmd, "kwargs": kwargs, "stdout": stdout})
        return _FakeCompleted(0, stdout, "")

    return _run


def test_persistence_gate_matrix_fixtures_recreate_volume_and_fresh_status():
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_persistence_run(recorded)):
        with mock.patch.object(docker_gate, "wait_http", return_value=True) as wait:
            with mock.patch.object(
                docker_gate, "http_get_json", return_value=_fresh_status_payload()
            ) as get_json:
                rc = docker_gate.run_gate("docker-persistence", project=PROJECT)

    assert rc == 0
    data = _report("docker-persistence")
    assert data["status"] == "PASS"

    cmds = [c["cmd"] for c in recorded]
    ups = [i for i, c in enumerate(cmds) if "up" in c]
    assert len(ups) == 2
    downs = [c for c in cmds if "down" in c]
    assert len(downs) == 2
    assert "-v" not in downs[0]  # mid-gate recreate keeps the model-cache volume
    assert "--remove-orphans" in downs[0]
    assert downs[0][downs[0].index("--timeout") + 1] == "30"
    assert downs[0][downs[0].index("-p") + 1] == PROJECT
    assert "-v" in downs[-1]  # final namespaced cleanup removes it

    # All five fixtures, each read exactly twice (initial + after recreate),
    # always via project-scoped `exec -T zmi cat /data/<relative-path>`.
    cats = [c for c in cmds if c[6:10] == ["exec", "-T", "zmi", "cat"]]
    assert len(cats) == 10
    for c in cats:
        assert c[:6] == ["docker", "compose", "-f", str(docker_gate.COMPOSE_FILE), "-p", PROJECT]
        assert c[10].startswith("/data/")
    rels = [c[10][len("/data/"):] for c in cats]
    assert set(rels) == _EXPECTED_FIXTURE_RELS
    assert all(rels.count(rel) == 2 for rel in set(rels))

    first_cat = cmds.index(cats[0])
    assert ups[0] < first_cat < cmds.index(downs[0])  # reads happen between up and down

    # Exact contents served back from the files the gate wrote under data_root.
    cat_outputs: dict[str, set[str]] = {}
    for call in recorded:
        cmd = call["cmd"]
        if cmd[6:10] == ["exec", "-T", "zmi", "cat"]:
            cat_outputs.setdefault(cmd[10][len("/data/"):], set()).add(call["stdout"])
    assert cat_outputs["projects.json"] == {'{"projects": []}'}
    assert cat_outputs["project_overrides.json"] == {"{}"}
    assert cat_outputs["processed_files.json"] == {"{}"}
    transcript_outputs = cat_outputs[docker_gate.PERSISTENCE_TRANSCRIPT_REL]
    assert transcript_outputs and all(
        out.startswith(f"persistence transcript {PROJECT}-") for out in transcript_outputs
    )
    asset_outputs = cat_outputs[docker_gate.PERSISTENCE_ASSET_REL]
    assert asset_outputs and all(
        out.startswith(f"persistence asset {PROJECT}-") for out in asset_outputs
    )

    # Exact named model-cache volume, inspected only after the recreate.
    volume_inspect = next(c for c in cmds if "volume" in c and "inspect" in c)
    assert f"{PROJECT}_zmi-model-cache" in volume_inspect
    assert cmds.index(volume_inspect) > ups[1]

    # /api/status fetched from the gate port and asserted fresh.
    status_url = f"http://127.0.0.1:{data['port']}/api/status"
    assert wait.call_count == 1
    assert wait.call_args.args[0] == status_url
    assert get_json.call_count == 1
    assert get_json.call_args.args[0] == status_url

    budget = docker_gate.TIMEOUTS["docker-persistence"]
    for call in recorded:
        assert 0 < call["kwargs"]["timeout"] <= budget

    log = (ROOT / data["artifact"]).read_text(encoding="utf-8")
    for slug in ("projects_json", "project_overrides_json", "processed_files_json", "transcript", "docs_asset"):
        assert f"[{slug}_readable]" in log
        assert f"[{slug}_survives_recreate]" in log
    for check in (
        "compose_up_healthy",
        "compose_down_keep_volumes",
        "compose_up_recreated",
        "model_cache_volume_scoped",
        "api_status_fresh_state",
    ):
        assert f"[{check}]" in log

    assert not (docker_gate.TEST_ROOT / PROJECT).exists()
    assert data["cleanup"][0]["step"] == "scoped_compose_down"
    assert data["cleanup"][1]["step"] == "scoped_data_cleanup"


@pytest.mark.parametrize(
    ("override", "signature_fragment"),
    [
        ({"running": True}, "running=True"),
        ({"stage": "transcribe"}, "stage='transcribe'"),
        ({"stages": {"upload": {"status": "running", "progress": None}}}, "stages[upload].status='running'"),
        ({"stages": {"store": {"status": "completed", "progress": None}}}, "stages[store].status='completed'"),
    ],
)
def test_persistence_gate_fails_when_status_is_not_fresh(override, signature_fragment):
    payload = {**_fresh_status_payload(), **override}
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_persistence_run(recorded)):
        with mock.patch.object(docker_gate, "wait_http", return_value=True):
            with mock.patch.object(docker_gate, "http_get_json", return_value=payload):
                rc = docker_gate.run_gate("docker-persistence", project=PROJECT)

    assert rc == 1
    data = _report("docker-persistence")
    assert data["status"] == "FAIL"
    assert data["check"] == "api_status_fresh_state"
    assert signature_fragment in data["error_signature"]
    # Cleanup stays namespaced: final down removes the volume, mid-gate never did.
    downs = [c["cmd"] for c in recorded if "down" in c["cmd"]]
    assert len(downs) == 2
    assert "-v" not in downs[0]
    assert "-v" in downs[-1]
    assert not (docker_gate.TEST_ROOT / PROJECT).exists()


def test_persistence_gate_fails_when_status_never_responds():
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_persistence_run(recorded)):
        with mock.patch.object(docker_gate, "wait_http", return_value=False):
            rc = docker_gate.run_gate("docker-persistence", project=PROJECT)

    assert rc == 1
    data = _report("docker-persistence")
    assert data["status"] == "FAIL"
    assert data["check"] == "api_status_responds"
    assert "/api/status" in data["error_signature"]


def test_persistence_gate_fails_when_fixture_content_changes_across_recreate():
    recorded: list[dict] = []
    with mock.patch.object(
        docker_gate.subprocess,
        "run",
        side_effect=_fake_persistence_run(recorded, corrupt_after_down="projects.json"),
    ):
        with mock.patch.object(docker_gate, "wait_http", return_value=True):
            with mock.patch.object(docker_gate, "http_get_json", return_value=_fresh_status_payload()):
                rc = docker_gate.run_gate("docker-persistence", project=PROJECT)

    assert rc == 1
    data = _report("docker-persistence")
    assert data["status"] == "FAIL"
    assert data["check"] == "projects_json_survives_recreate"
    assert "/data/projects.json mismatch" in data["error_signature"]
    downs = [c["cmd"] for c in recorded if "down" in c["cmd"]]
    assert len(downs) == 2 and "-v" not in downs[0] and "-v" in downs[-1]


class _FakeHTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_http_get_json_returns_object_payload():
    with mock.patch.object(
        docker_gate.urllib.request,
        "urlopen",
        return_value=_FakeHTTPResponse(b'{"running": false, "stage": null}'),
    ):
        assert docker_gate.http_get_json("http://127.0.0.1:5311/api/status", timeout_seconds=1.0) == {
            "running": False,
            "stage": None,
        }


def test_http_get_json_rejects_non_object_payload():
    with mock.patch.object(
        docker_gate.urllib.request, "urlopen", return_value=_FakeHTTPResponse(b"[1, 2]")
    ):
        with pytest.raises(ValueError):
            docker_gate.http_get_json("http://127.0.0.1:5311/api/status", timeout_seconds=1.0)


def test_asr_gate_fails_cleanly_when_fixture_missing():
    missing = docker_gate.ASR_FIXTURE.with_name("missing-asr-fixture.wav")
    with mock.patch.object(docker_gate, "ASR_FIXTURE", missing):
        with mock.patch.object(docker_gate.subprocess, "run", side_effect=AssertionError("docker must not run")):
            rc = docker_gate.run_gate("docker-asr-smoke", project=PROJECT)

    assert rc == 1
    data = _report("docker-asr-smoke")
    assert data["check"] == "asr_fixture_present"
    assert "missing-asr-fixture.wav" in data["error_signature"]
    assert not (docker_gate.TEST_ROOT / PROJECT).exists()


def _fake_asr_run(recorded: list[dict], output: str = '{"text":" small transcription test","language":"en","language_probability":0.99,"duration":2.6,"model":"tiny"}'):
    def _run(cmd, **kwargs):
        cmd = list(cmd)
        recorded.append({"cmd": cmd, "kwargs": kwargs})
        stdout = output if "run" in cmd and "--entrypoint" in cmd else "ok"
        return _FakeCompleted(0, stdout, "")

    return _run


def test_asr_gate_runs_tiny_twice_and_keeps_cache_across_recreate():
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_asr_run(recorded)):
        rc = docker_gate.run_gate("docker-asr-smoke", project=PROJECT)

    assert rc == 0
    cmds = [c["cmd"] for c in recorded]
    transcribes = [c for c in cmds if "--entrypoint" in c]
    assert len(transcribes) == 2
    assert all("WHISPER_MODEL=tiny" in c and "WHISPER_MODEL=large-v3" not in c for c in transcribes)
    downs = [c for c in cmds if "down" in c]
    assert len(downs) == 2  # mid-gate recreation and scoped final cleanup
    assert "-v" not in downs[0]
    assert "-v" in downs[-1]
    cache_checks = [c for c in cmds if docker_gate.ASR_CACHE_DIR in c]
    assert len(cache_checks) == 2
    indexes = {"mid_down": None, "second_cache": None, "second_transcribe": None}
    for i, cmd in enumerate(cmds):
        if cmd == downs[0]:
            indexes["mid_down"] = i
        if cmd == cache_checks[-1]:
            indexes["second_cache"] = i
        if cmd == transcribes[-1]:
            indexes["second_transcribe"] = i
    assert indexes["mid_down"] < indexes["second_cache"] < indexes["second_transcribe"]
    report = _report("docker-asr-smoke")
    assert report["status"] == "PASS"
    log = (ROOT / report["artifact"]).read_text(encoding="utf-8")
    for check in ("asr_tiny_transcript_initial", "tiny_model_cache_initial", "compose_down_keep_cache", "tiny_model_cache_survives_recreate", "asr_tiny_transcript_after_recreate"):
        assert f"[{check}]" in log


@pytest.mark.parametrize(
    ("output", "expected_check"),
    [
        ("not-json", "asr_tiny_transcript_initial"),
        ('{"text":"","language":"en","duration":2.6,"model":"tiny"}', "asr_tiny_transcript_initial"),
        ('{"text":"words","language":"","duration":2.6,"model":"tiny"}', "asr_tiny_metadata_initial"),
    ],
)
def test_asr_gate_fails_for_empty_or_invalid_transcript_metadata(output, expected_check):
    recorded: list[dict] = []
    with mock.patch.object(docker_gate.subprocess, "run", side_effect=_fake_asr_run(recorded, output)):
        rc = docker_gate.run_gate("docker-asr-smoke", project=PROJECT)

    assert rc == 1
    report = _report("docker-asr-smoke")
    assert report["status"] == "FAIL"
    assert report["check"] == expected_check
    downs = [c["cmd"] for c in recorded if "down" in c["cmd"]]
    assert len(downs) == 1 and "-v" in downs[0]


def test_scoped_rmtree_refuses_paths_outside_test_namespace(tmp_path):
    ok, detail = docker_gate.scoped_rmtree(ROOT)
    assert not ok and "refusing" in detail
    ok, detail = docker_gate.scoped_rmtree(docker_gate.TEST_ROOT)
    assert not ok and "refusing" in detail

    impostor = docker_gate.TEST_ROOT / "user-data"
    impostor.mkdir(parents=True, exist_ok=True)
    try:
        ok, detail = docker_gate.scoped_rmtree(impostor)
        assert not ok and "refusing" in detail
    finally:
        shutil.rmtree(docker_gate.TEST_ROOT, ignore_errors=True)

    legit = docker_gate.TEST_ROOT / "zmi-test-tmp" / "data"
    legit.mkdir(parents=True, exist_ok=True)
    ok, detail = docker_gate.scoped_rmtree(legit.parent)
    assert ok and detail == ""
    assert not legit.parent.exists()


def test_source_never_prunes_or_touches_global_state():
    import ast

    source = (ROOT / "scripts" / "docker_gate.py").read_text(encoding="utf-8")
    code = source.replace(ast.get_docstring(ast.parse(source)) or "", "")
    assert "prune" not in code
    for forbidden in ("docker system", "docker volume rm", "volume rm", "image rm", "-a --volumes"):
        assert forbidden not in code


# --- e2e harness env mapping (WP-06, host defaults unchanged) -----------------

def test_e2e_defaults_preserve_host_behavior(monkeypatch):
    for var in ("ZMI_BASE_URL", "ZMI_TEST_DATA_ROOT", "ZMI_E2E_EXTERNAL_SERVER"):
        monkeypatch.delenv(var, raising=False)
    mod = importlib.reload(e2e_mod)
    assert mod.DASHBOARD_URL == "http://127.0.0.1:5000"
    assert mod.TEST_DATA_ROOT == mod.ROOT
    assert mod.EXTERNAL_SERVER is False


def test_e2e_env_overrides_are_honored(monkeypatch, tmp_path):
    monkeypatch.setenv("ZMI_BASE_URL", "http://127.0.0.1:5311")
    monkeypatch.setenv("ZMI_TEST_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ZMI_E2E_EXTERNAL_SERVER", "1")
    try:
        mod = importlib.reload(e2e_mod)
        assert mod.DASHBOARD_URL == "http://127.0.0.1:5311"
        assert mod.TEST_DATA_ROOT == tmp_path.resolve()
        assert mod.REPORT_PATH == tmp_path.resolve() / "e2e_report.json"
        assert mod.EXTERNAL_SERVER is True
    finally:
        for var in ("ZMI_BASE_URL", "ZMI_TEST_DATA_ROOT", "ZMI_E2E_EXTERNAL_SERVER"):
            monkeypatch.delenv(var, raising=False)
        importlib.reload(e2e_mod)


def test_smoke_dashboard_reads_base_url_env_with_host_default():
    source = (ROOT / "tests" / "e2e" / "smoke_dashboard.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")' in source
    assert 'browser_errors.append(f"console: {msg.text}")' in source
    assert 'browser_errors.append(f"pageerror: {exc}")' in source
    assert '"critical_path_no_browser_errors"' in source
