"""E2E harness: starts the dashboard, runs Playwright smoke test, stops server.

Env-driven URL/data root (WP-06), defaults preserve host behavior:
    ZMI_BASE_URL              dashboard URL (default http://127.0.0.1:5000)
    ZMI_TEST_DATA_ROOT        root for fixture writes/reports (default repo root)
    ZMI_E2E_EXTERNAL_SERVER=1  dashboard already running (Docker gates); the
                              harness only waits for it and runs the suite

Run:
    python scripts/e2e.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docs.assets.generate_mock_data import MOCK_MEDIA_FILENAMES

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")

# Deterministic project fixture: generate_mock_data.py only creates media and
# transcriptions, so without this file /api/projects returns [] and the
# Projects modal renders zero items. Match rules mirror the synthetic media
# filenames so project routing/filtering stays deterministic. Must never
# contain real owner project data.
SYNTHETIC_PROJECTS: list[dict] = [
    {"name": "Northwind Dev", "match": {"prefix": ["northwind_"]}},
    {"name": "Zo Interviews", "match": {"prefix": ["zo_"]}},
    {"name": "Contoso Team", "match": {"prefix": ["contoso_"]}},
    {"name": "Dev Meetings", "match": {"filename_contains": ["meeting"]}},
    {"name": "Fabrikam", "match": {"prefix": ["fabrikam_"]}},
    {"name": "Tutorials", "match": {"filename_contains": ["tutorial"]}},
]

HOST_TEST_DATA_ROOT = ROOT / "artifacts" / "gates" / "e2e-host-data"
TEST_DATA_ROOT = (
    Path(os.environ.get("ZMI_TEST_DATA_ROOT", str(ROOT))).resolve()
    if os.environ.get("ZMI_E2E_EXTERNAL_SERVER", "").strip() == "1"
    else HOST_TEST_DATA_ROOT.resolve()
)
REPORT_PATH = TEST_DATA_ROOT / "e2e_report.json"
EXTERNAL_SERVER = os.environ.get("ZMI_E2E_EXTERNAL_SERVER", "").strip() == "1"
PYTHON = sys.executable


def _server_cmd() -> list[str]:
    return [PYTHON, str(ROOT / "dashboard.py")]


def prepare_host_data_root(env: dict[str, str]) -> Path:
    """Reset only the scoped synthetic E2E root and populate it with fixtures."""
    root = HOST_TEST_DATA_ROOT.resolve()
    expected = (ROOT / "artifacts" / "gates" / "e2e-host-data").resolve()
    if HOST_TEST_DATA_ROOT.is_symlink() or root != expected or root == ROOT.resolve():
        raise RuntimeError("unsafe E2E fixture root")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    fixture_env = dict(env)
    fixture_env["ZMI_DATA_ROOT"] = str(root)
    result = subprocess.run(
        [PYTHON, str(ROOT / "docs" / "assets" / "generate_mock_data.py")],
        cwd=str(ROOT),
        env=fixture_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "fixture generation failed")[-2000:])
    (root / "projects.json").write_text(
        json.dumps({"projects": SYNTHETIC_PROJECTS}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


class HostE2EFailure(RuntimeError):
    def __init__(self, check: str, detail: str) -> None:
        super().__init__(detail)
        self.check = check


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def configure_host_environment(env: dict[str, str]) -> tuple[dict[str, str], str]:
    child_env = dict(env)
    port = _available_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    child_env.update({
        "DASHBOARD_HOST": "127.0.0.1",
        "DASHBOARD_PORT": str(port),
        "ZMI_BASE_URL": base_url,
        "ZMI_E2E_EXTERNAL_SERVER": "0",
    })
    return child_env, base_url


def _safe_child_output(output: str, limit: int = 2000) -> str:
    text = (output or "")[-limit:]
    text = text.replace(str(ROOT), "<repo>").replace(str(Path.home()), "<user>")
    text = re.sub(r"(?i)\b[A-Z]:\\[^\s\"']+", "<path>", text)
    return text


def _wait_for_server(url: str, process=None, output: list[str] | None = None, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            detail = _safe_child_output("".join(output or []))
            raise HostE2EFailure("host_e2e_server_startup", detail or "spawned dashboard exited before readiness")
        try:
            with urllib.request.urlopen(url, timeout=1.0) as _:
                if process is not None and process.poll() is not None:
                    detail = _safe_child_output("".join(output or []))
                    raise HostE2EFailure("host_e2e_server_startup", detail or "spawned dashboard exited before readiness")
                return True
        except HostE2EFailure:
            raise
        except Exception:
            time.sleep(0.5)
    return False


def validate_synthetic_files(files: list[dict], expected: set[str] | frozenset[str] = MOCK_MEDIA_FILENAMES) -> None:
    unexpected = sorted(
        str(item.get("name", "<missing filename>"))
        for item in files
        if not isinstance(item, dict) or item.get("name") not in expected
    )
    if unexpected:
        raise HostE2EFailure("host_e2e_data_isolation", "unexpected media filename detected")


def _preflight_synthetic_data(url: str) -> None:
    with urllib.request.urlopen(f"{url}/api/files", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    validate_synthetic_files(payload.get("files", []))


def _persist_report(report_path: Path, payload: dict) -> None:
    """Write the run report to its data-root path and mirror it to the repo
    root.

    scripts/gate_runner.py extracts the e2e failure signature from
    ``ROOT / "e2e_report.json"`` (REPORT_FILES), but the harness writes the
    report under ZMI_TEST_DATA_ROOT — on host runs that is the fixture root,
    so the gate used to read whatever stale report was left at the repo root
    from an older run and attribute its failures to the current gate."""
    text = json.dumps(payload, indent=2)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    mirror = ROOT / report_path.name
    if mirror != report_path and ROOT.is_dir() and os.access(ROOT, os.W_OK):
        mirror.write_text(text, encoding="utf-8")


def _write_failure(report_path: Path, check: str, detail: str, server_output: str = "") -> int:
    _persist_report(report_path, {
        "status": "FAIL",
        "check": check,
        "detail": _safe_child_output(detail),
        "server_output": _safe_child_output(server_output),
        "ok": False,
    })
    print(f"[FAIL] {check}: {_safe_child_output(detail)}")
    return 1


def _drain_output(stream, sink: list[str]) -> None:
    """Continuously reads lines from `stream` into `sink` for the process's
    whole lifetime.

    Without this, subprocess.PIPE has a small OS buffer (~64KB on Windows)
    — Werkzeug logs a line per HTTP request to stderr, and a Playwright
    smoke run makes enough requests (page polling + explicit calls) to fill
    it well before the run ends. Once full, the *server process itself*
    blocks on its next write() to the pipe, unable to handle any further
    request, until something reads from the other end — exactly the
    "dashboard stops responding partway through the run" symptom this fixes
    (reproduced identically on a fresh CI runner with no prior state, always
    at roughly the same point in a run — the buffer filling, not a load- or
    memory-dependent flake). See Python docs' own subprocess deadlock
    warning for stdout=PIPE/stderr=PIPE.
    """
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
    except (ValueError, OSError):
        pass  # stream closed under us as the process exits — fine


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if part
    )
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "DASHBOARD_HOST": "127.0.0.1",
        "ZMI_CONTAINER_MODE": "false",
        "ALLOW_EXTERNAL_LLM": "false",
        "ZMI_CONFIG_ENV": str(ROOT / "artifacts" / "gates" / "validation-config-does-not-exist.env"),
    })
    global TEST_DATA_ROOT, REPORT_PATH, DASHBOARD_URL
    if not EXTERNAL_SERVER:
        env, DASHBOARD_URL = configure_host_environment(env)
    if not EXTERNAL_SERVER:
        TEST_DATA_ROOT = prepare_host_data_root(env)
    REPORT_PATH = TEST_DATA_ROOT / "e2e_report.json"
    env["ZMI_DATA_ROOT"] = str(TEST_DATA_ROOT)
    env["ZMI_BASE_URL"] = DASHBOARD_URL
    env["ZMI_TEST_DATA_ROOT"] = str(TEST_DATA_ROOT)

    server = None
    server_output: list[str] = []
    if not EXTERNAL_SERVER:
        print("Starting dashboard...")
        server = subprocess.Popen(
            _server_cmd(),
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        drain_thread = threading.Thread(target=_drain_output, args=(server.stdout, server_output), daemon=True)
        drain_thread.start()

    try:
        try:
            if not _wait_for_server(DASHBOARD_URL, process=server, output=server_output):
                raise HostE2EFailure("host_e2e_server_startup", "dashboard did not become ready")
            if server is not None and server.poll() is not None:
                raise HostE2EFailure("host_e2e_server_startup", "spawned dashboard exited before Playwright")
            if not EXTERNAL_SERVER:
                _preflight_synthetic_data(DASHBOARD_URL)
        except HostE2EFailure as exc:
            return _write_failure(REPORT_PATH, exc.check, str(exc), "".join(server_output))
        except Exception as exc:  # noqa: BLE001
            check = "host_e2e_data_isolation" if not EXTERNAL_SERVER else "e2e_preflight"
            return _write_failure(REPORT_PATH, check, f"preflight failed: {type(exc).__name__}", "".join(server_output))

        e2e_results = []
        scripts = (
            ("black_video_tools.py",)
            if not EXTERNAL_SERVER and os.environ.get("ZMI_E2E_BLACK_VIDEO_ONLY", "") == "1"
            else ("smoke_dashboard.py",) if EXTERNAL_SERVER else ("smoke_dashboard.py", "black_video_tools.py")
        )
        for script in scripts:
            print(f"Running {script} against {DASHBOARD_URL}...")
            result = subprocess.run(
                [PYTHON, str(ROOT / "tests" / "e2e" / script)],
                cwd=str(TEST_DATA_ROOT),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            e2e_results.append({
                "script": script,
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
            if result.returncode:
                break
        ok = all(item["status"] == "PASS" for item in e2e_results)
        report = {
            "status": "PASS" if ok else "FAIL",
            "returncode": 0 if ok else e2e_results[-1]["returncode"],
            "base_url": DASHBOARD_URL,
            "checks": e2e_results,
            "stdout": "\n".join(item["stdout"] for item in e2e_results),
            "stderr": "\n".join(item["stderr"] for item in e2e_results),
            "server_output": "".join(server_output)[-4000:],
            "ok": ok,
        }
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except Exception:
                if server.poll() is None:
                    server.kill()

    _persist_report(REPORT_PATH, report)
    print(report["stdout"][-2000:])
    if report["stderr"]:
        print(report["stderr"][-1000:])
    print("Report saved: e2e_report.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
