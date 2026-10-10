"""Deterministic Docker gate runner (PLAN-ZMI-DKR-001 WP-06).

Runs one named Docker gate against a fully isolated Compose project:

- project name: ``zmi-test-${BUILD_ID or deterministic local suffix}``;
- test data: only under ``artifacts/gates/docker/projects/<project>/``;
- cleanup: exactly that project (``docker compose -p <project> down -v``)
  and that test path — never ``docker system prune``, never volumes or
  paths outside the ``zmi-test-`` namespace.

Each gate has a bounded timeout, writes a compact per-gate JSON report
(``artifacts/gates/docker/<gate>.json``) plus a separate raw log
(``artifacts/gates/docker/logs/<gate>.log``) with command/check/
error_signature/artifact/duration fields.

Gates: docker-config, docker-build, docker-smoke, docker-persistence,
docker-asr-smoke, docker-e2e.

Run:
    python scripts/docker_gate.py <gate> [--project NAME]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compose.yml"
ARTIFACTS_DIR = ROOT / "artifacts" / "gates" / "docker"
LOGS_DIR = ARTIFACTS_DIR / "logs"
TEST_ROOT = ARTIFACTS_DIR / "projects"

PROJECT_PREFIX = "zmi-test-"
PROJECT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

# Bounded per-gate timeouts (seconds).
TIMEOUTS: dict[str, int] = {
    "docker-config": 120,
    "docker-build": 1800,
    "docker-smoke": 600,
    "docker-persistence": 900,
    "docker-asr-smoke": 1800,
    "docker-e2e": 1800,
}
CLEANUP_TIMEOUT = 300
HEALTH_TIMEOUT = 120

ASR_FIXTURE = ROOT / "tests" / "fixtures" / "asr_smoke.wav"

# Runs inside the container (WP-08 adds the fixture; WP-06 wires the gate).
# Model downloads land under /cache via the image's HF_HOME default.
ASR_SMOKE_SCRIPT = (
    "import json, sys\n"
    "from faster_whisper import WhisperModel\n"
    "model = WhisperModel('tiny', device='cpu', compute_type='int8')\n"
    "segments, info = model.transcribe('/data/asr-fixture.wav', beam_size=1)\n"
    "text = ' '.join(s.text for s in segments).strip()\n"
    "print(json.dumps({'text': text, 'language': info.language, 'language_probability': info.language_probability, 'duration': info.duration, 'model': 'tiny'}))\n"
    "sys.exit(0 if text and info.language else 3)\n"
)
ASR_CACHE_DIR = "/cache/huggingface/hub/models--Systran--faster-whisper-tiny"


class GateError(Exception):
    """A gate step failed: `check` names it, `error_signature` describes it."""

    def __init__(self, check: str, error_signature: str) -> None:
        super().__init__(error_signature)
        self.check = check
        self.error_signature = error_signature


def _as_text(data: object) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data if isinstance(data, str) else ""


def _signature(stdout: str, stderr: str, limit: int = 500) -> str:
    text = (stdout or "").strip()
    error = (stderr or "").strip()
    signature = ""
    for line in reversed(f"{text}\n{error}".splitlines()):
        if line.strip():
            signature = line.strip()
            break
    return signature if len(signature) <= limit else signature[:limit]


def sanitize_build_id(raw: str) -> str:
    """Reduce an arbitrary BUILD_ID to a valid compose project token."""
    token = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")
    token = token[:40].rstrip("-_")
    return token or "build"


def validate_project(project: str) -> str:
    if not project.startswith(PROJECT_PREFIX):
        raise ValueError(f"project name must start with {PROJECT_PREFIX!r}: {project!r}")
    if not PROJECT_NAME_RE.match(project):
        raise ValueError(f"invalid compose project name: {project!r}")
    return project


def build_artifacts_dir() -> Path:
    build = (os.environ.get("BUILD_NUMBER") or "local").strip()
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", build)[:80] or "local"
    return ROOT / "artifacts" / "gates" / f"build-{safe}"


def resolve_project_name(explicit: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """zmi-test-${BUILD_ID or deterministic local suffix} (ZMI_TEST_PROJECT wins)."""
    env = os.environ if env is None else env
    if explicit:
        return validate_project(explicit)
    for var in ("ZMI_TEST_PROJECT", "BUILD_ID"):
        raw = (env.get(var) or "").strip()
        if raw:
            token = raw if var == "ZMI_TEST_PROJECT" else sanitize_build_id(raw)
            return validate_project(PROJECT_PREFIX + token)
    digest = hashlib.sha1(str(ROOT).lower().encode("utf-8")).hexdigest()[:8]
    return validate_project(f"{PROJECT_PREFIX}local-{digest}")


def resolve_port(project: str, env: Mapping[str, str] | None = None) -> int:
    """Deterministic loopback test port (5100-5899) derived from the project."""
    env = os.environ if env is None else env
    raw = (env.get("ZMI_TEST_PORT") or "").strip()
    if raw:
        try:
            port = int(raw)
        except ValueError as exc:
            raise ValueError(f"invalid ZMI_TEST_PORT: {raw!r}") from exc
        if not 1024 <= port <= 65535:
            raise ValueError(f"ZMI_TEST_PORT out of range: {port}")
        return port
    digest = hashlib.sha1(project.encode("utf-8")).digest()
    return 5100 + (int.from_bytes(digest[:4], "big") % 800)


def scoped_rmtree(path: Path) -> tuple[bool, str]:
    """Remove `path` only when it is a zmi-test-* dir under TEST_ROOT."""
    try:
        resolved = path.resolve()
        test_root = TEST_ROOT.resolve()
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if resolved == test_root or not resolved.is_relative_to(test_root):
        return False, f"refusing to remove path outside test root: {path}"
    if not resolved.name.startswith(PROJECT_PREFIX):
        return False, f"refusing to remove non-test path: {path}"
    if not resolved.exists():
        return True, ""
    try:
        shutil.rmtree(resolved)
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def compose_base(project: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", project]


def wait_http(url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if getattr(response, "status", 200) == 200:
                    return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def http_get_json(url: str, timeout_seconds: float) -> dict:
    """GET `url` and return its JSON object payload (never a list/scalar)."""
    with urllib.request.urlopen(url, timeout=max(0.0, timeout_seconds)) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object from {url}, got {type(payload).__name__}")
    return payload


@dataclass
class GateContext:
    gate: str
    project: str
    port: int
    timeout: float
    commands: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    failed_command: str = ""
    deadline: float = 0.0

    def __post_init__(self) -> None:
        self.deadline = time.monotonic() + self.timeout

    @property
    def project_dir(self) -> Path:
        return TEST_ROOT / self.project

    @property
    def data_root(self) -> Path:
        return self.project_dir / "data"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def compose_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["ZMI_DATA_PATH"] = str(self.data_root)
        env["ZMI_PORT"] = str(self.port)
        env["ALLOW_EXTERNAL_LLM"] = "false"
        return env

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def ensure_data_root(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)

    def up_cmd(self) -> list[str]:
        return [*compose_base(self.project), "up", "-d", "--wait"]

    def run(
        self,
        check: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
        expect_fail: bool = False,
    ) -> str:
        command = " ".join(cmd)
        self.commands.append(command)
        self.log.append(f"\n== [{check}] {command}\n")
        remaining = self.remaining()
        if remaining <= 0:
            self.failed_command = command
            raise GateError("timeout", f"gate budget exhausted before: {command}")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(ROOT),
                env=env if env is not None else os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            self.log.append(_as_text(exc.output))
            self.log.append(_as_text(exc.stderr))
            self.failed_command = command
            raise GateError("timeout", f"timeout after {round(remaining)}s: {command}") from None
        stdout, stderr = result.stdout or "", result.stderr or ""
        self.log.append(stdout)
        self.log.append(stderr)
        failed = result.returncode != 0
        if failed != expect_fail:
            self.failed_command = command
            if expect_fail:
                raise GateError(
                    check,
                    f"expected command failure but exited {result.returncode}: {command}",
                )
            raise GateError(check, _signature(stdout, stderr))
        return stdout


def gate_config(ctx: GateContext) -> None:
    out = ctx.run("compose_config_valid", [*compose_base(ctx.project), "--profile", "e2e", "config"])
    if not out.strip():
        raise GateError("compose_config_nonempty", "docker compose config produced no output")


def gate_build(ctx: GateContext) -> None:
    ctx.run(
        "compose_build_runtime_and_test",
        [*compose_base(ctx.project), "--profile", "e2e", "build"],
        env=ctx.compose_env(),
    )


def _exec_cmd(ctx: GateContext, *args: str) -> list[str]:
    return [*compose_base(ctx.project), "exec", "-T", "zmi", *args]


def gate_smoke(ctx: GateContext) -> None:
    ctx.ensure_data_root()
    ctx.run("compose_up_healthy", ctx.up_cmd(), env=ctx.compose_env())
    budget = min(HEALTH_TIMEOUT, ctx.remaining())
    if budget <= 0:
        raise GateError("timeout", f"gate budget exhausted before: GET {ctx.base_url}/api/status")
    if not wait_http(f"{ctx.base_url}/api/status", timeout_seconds=budget):
        raise GateError("api_status_responds", f"GET {ctx.base_url}/api/status did not return 200 within {round(budget)}s")

    uid = ctx.run("runs_as_nonroot", _exec_cmd(ctx, "id", "-u")).strip()
    if not uid.isdigit() or int(uid) == 0:
        raise GateError("runs_as_nonroot", f"id -u returned {uid!r}, expected a non-root uid")

    ctx.run("ffmpeg_version", _exec_cmd(ctx, "ffmpeg", "-version"))
    ctx.run("ffprobe_version", _exec_cmd(ctx, "ffprobe", "-version"))

    langs = ctx.run("tesseract_langs_eng_spa", _exec_cmd(ctx, "tesseract", "--list-langs"))
    available = {line.strip() for line in langs.splitlines() if line.strip()}
    missing = {"eng", "spa"} - available
    if missing:
        raise GateError("tesseract_langs_eng_spa", f"tesseract --list-langs missing: {sorted(missing)}")

    flag = ctx.run("allow_external_llm_false", _exec_cmd(ctx, "printenv", "ALLOW_EXTERNAL_LLM")).strip()
    if flag.lower() != "false":
        raise GateError("allow_external_llm_false", f"ALLOW_EXTERNAL_LLM={flag!r}, expected 'false'")

    ctx.run("app_unwritable", _exec_cmd(ctx, "sh", "-c", "touch /app/.zmi-gate-probe"), expect_fail=True)

    for check, target in (("data_writable", "/data"), ("cache_writable", "/cache")):
        ctx.run(
            check,
            _exec_cmd(
                ctx,
                "sh",
                "-c",
                f"touch {target}/.zmi-gate-probe && rm -f {target}/.zmi-gate-probe",
            ),
        )

    binding = ctx.run(
        "port_loopback",
        [*compose_base(ctx.project), "port", "zmi", "5000"],
        env=ctx.compose_env(),
    ).strip()
    if not binding.startswith("127.0.0.1:"):
        raise GateError("port_loopback", f"port zmi 5000 bound as {binding!r}, expected 127.0.0.1:*")


# Persistence matrix fixtures: (check slug, path relative to /data, exact
# content). All five live solely under the gate's data_root bind mount and
# mirror real app state: project config, manual overrides, the processed
# files DB, one transcription, and one docs manual asset (the
# <stem>_Frames/<stem>/manual/assets layout KeyframeExtractor + the
# documentation engine produce).
PERSISTENCE_TRANSCRIPT_REL = "CarpetaTranscripciones/persistence/gate-transcript.txt"
PERSISTENCE_ASSET_REL = (
    "CarpetaTranscripciones/persistence/tutorial_Frames/tutorial/manual/assets/step-01.jpg"
)


def _persistence_fixtures(project: str) -> list[tuple[str, str, str]]:
    token = f"{project}-{time.strftime('%Y%m%dT%H%M%S')}"
    return [
        ("projects_json", "projects.json", '{"projects": []}'),
        ("project_overrides_json", "project_overrides.json", "{}"),
        ("processed_files_json", "processed_files.json", "{}"),
        ("transcript", PERSISTENCE_TRANSCRIPT_REL, f"persistence transcript {token}"),
        ("docs_asset", PERSISTENCE_ASSET_REL, f"persistence asset {token}"),
    ]


def _write_persistence_fixtures(ctx: GateContext, fixtures: list[tuple[str, str, str]]) -> None:
    for _slug, rel, content in fixtures:
        path = ctx.data_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes: no newline translation, so `cat` output matches exactly.
        path.write_bytes(content.encode("utf-8"))


def _verify_persistence_fixtures(
    ctx: GateContext, fixtures: list[tuple[str, str, str]], phase: str
) -> None:
    for slug, rel, content in fixtures:
        check = f"{slug}_{phase}"
        out = ctx.run(check, _exec_cmd(ctx, "cat", f"/data/{rel}"))
        if out != content:
            raise GateError(check, f"/data/{rel} mismatch: {out.strip()[:200]!r}")


def _verify_api_status_fresh(ctx: GateContext) -> None:
    """After recreate the dashboard must boot into a fresh run state.

    Only fields that exist in the /api/status schema are asserted:
    `running` false, `stage` null, and every reported stage pending (a
    brand-new process starts with an empty `stages` map — also fresh).
    """
    url = f"{ctx.base_url}/api/status"
    budget = min(HEALTH_TIMEOUT, ctx.remaining())
    if budget <= 0:
        raise GateError("timeout", f"gate budget exhausted before: GET {url}")
    if not wait_http(url, timeout_seconds=budget):
        raise GateError("api_status_responds", f"GET {url} did not return 200 within {round(budget)}s")
    ctx.log.append(f"\n== [api_status_fresh_state] GET {url}\n")
    try:
        status = http_get_json(url, timeout_seconds=min(10.0, max(1.0, ctx.remaining())))
    except Exception as exc:  # noqa: BLE001 - any fetch/parse failure fails this check
        raise GateError("api_status_responds", f"GET {url} failed: {type(exc).__name__}: {exc}") from None
    ctx.log.append(json.dumps(status, ensure_ascii=False) + "\n")

    problems: list[str] = []
    running = status.get("running")
    if running is not False:
        problems.append(f"running={running!r}, expected false")
    stage = status.get("stage")
    if stage is not None:
        problems.append(f"stage={stage!r}, expected null")
    stages = status.get("stages")
    if isinstance(stages, dict):
        for name, entry in sorted(stages.items()):
            entry_status = entry.get("status") if isinstance(entry, dict) else entry
            if entry_status != "pending":
                problems.append(f"stages[{name}].status={entry_status!r}, expected 'pending'")
    if problems:
        raise GateError("api_status_fresh_state", "; ".join(problems))


def gate_persistence(ctx: GateContext) -> None:
    ctx.ensure_data_root()
    fixtures = _persistence_fixtures(ctx.project)
    _write_persistence_fixtures(ctx, fixtures)

    ctx.run("compose_up_healthy", ctx.up_cmd(), env=ctx.compose_env())
    _verify_persistence_fixtures(ctx, fixtures, phase="readable")

    # Recreate without -v: the bind-mounted data AND the named model-cache
    # volume must survive.
    ctx.run(
        "compose_down_keep_volumes",
        [*compose_base(ctx.project), "down", "--remove-orphans", "--timeout", "30"],
        env=ctx.compose_env(),
    )
    ctx.run("compose_up_recreated", ctx.up_cmd(), env=ctx.compose_env())
    _verify_persistence_fixtures(ctx, fixtures, phase="survives_recreate")

    ctx.run(
        "model_cache_volume_scoped",
        ["docker", "volume", "inspect", f"{ctx.project}_zmi-model-cache"],
    )
    _verify_api_status_fresh(ctx)


def gate_asr_smoke(ctx: GateContext) -> None:
    if not ASR_FIXTURE.exists():
        rel = ASR_FIXTURE.relative_to(ROOT).as_posix()
        raise GateError("asr_fixture_present", f"missing ASR fixture: {rel} (expected from WP-08)")
    ctx.ensure_data_root()
    shutil.copyfile(ASR_FIXTURE, ctx.data_root / "asr-fixture.wav")
    ctx.run("compose_up_healthy", ctx.up_cmd(), env=ctx.compose_env())

    def transcribe(phase: str) -> None:
        output = ctx.run(
            f"asr_tiny_transcript_{phase}",
            [
                *compose_base(ctx.project),
                "run", "--rm", "--no-deps",
                "-e", "WHISPER_MODEL=tiny",
                "--entrypoint", "python",
                "zmi", "-c", ASR_SMOKE_SCRIPT,
            ],
            env=ctx.compose_env(),
        )
        try:
            result = json.loads(next(line for line in reversed(output.splitlines()) if line.strip()))
        except (StopIteration, ValueError) as exc:
            raise GateError(f"asr_tiny_transcript_{phase}", f"invalid ASR JSON: {type(exc).__name__}") from None
        if not isinstance(result, dict) or not result.get("text", "").strip():
            raise GateError(f"asr_tiny_transcript_{phase}", "ASR returned empty transcript")
        if (
            result.get("model") != "tiny"
            or not isinstance(result.get("language"), str)
            or not result["language"].strip()
            or not isinstance(result.get("duration"), (int, float))
            or result["duration"] <= 0
        ):
            raise GateError(f"asr_tiny_metadata_{phase}", "ASR metadata missing model/language/duration")

    def verify_cache(phase: str) -> None:
        ctx.run(
            f"tiny_model_cache_{phase}",
            [*compose_base(ctx.project), "exec", "-T", "zmi", "test", "-d", ASR_CACHE_DIR],
            env=ctx.compose_env(),
        )

    transcribe("initial")
    verify_cache("initial")
    ctx.run(
        "compose_down_keep_cache",
        [*compose_base(ctx.project), "down", "--remove-orphans", "--timeout", "30"],
        env=ctx.compose_env(),
    )
    ctx.run("compose_up_recreated", ctx.up_cmd(), env=ctx.compose_env())
    verify_cache("survives_recreate")
    transcribe("after_recreate")


def gate_e2e(ctx: GateContext) -> None:
    ctx.ensure_data_root()
    ctx.run("compose_up_healthy", ctx.up_cmd(), env=ctx.compose_env())
    base = [
        *compose_base(ctx.project),
        "--profile", "e2e",
        "run", "--rm", "--no-deps",
        "-e", "ZMI_BASE_URL=http://127.0.0.1:5000",
        "-e", "ZMI_DATA_ROOT=/data",
        "-e", "ZMI_TEST_DATA_ROOT=/data",
        "-e", "ZMI_E2E_EXTERNAL_SERVER=1",
    ]
    try:
        ctx.run(
            "docker_e2e_seed_synthetic",
            [*base, "zmi-e2e", "python", "docs/assets/generate_mock_data.py"],
            env=ctx.compose_env(),
        )
        ctx.run("docker_e2e_suite", [*base, "zmi-e2e"], env=ctx.compose_env())
    finally:
        _preserve_e2e_artifacts(ctx)


def _preserve_e2e_artifacts(ctx: GateContext) -> None:
    """Keep only browser evidence outside the disposable synthetic data root."""
    destination = build_artifacts_dir() / "e2e"
    for name in ("e2e_report.json", "dashboard_report.json"):
        source = ctx.data_root / name
        if source.is_file():
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination / name)
    screenshots = ctx.data_root / "screenshots"
    if screenshots.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(screenshots, destination / "screenshots", dirs_exist_ok=True)


def _capture_container_logs(ctx: GateContext) -> None:
    command = [*compose_base(ctx.project), "logs", "--no-color", "--tail", "200", "zmi"]
    label = "container_logs_last_200"
    rendered = " ".join(command)
    ctx.commands.append(rendered)
    ctx.log.append(f"\n== [{label}] {rendered}\n")
    remaining = min(60.0, ctx.remaining())
    if remaining <= 0:
        ctx.log.append("log capture skipped: gate time budget exhausted\n")
        return
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=ctx.compose_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=remaining,
        )
        ctx.log.extend((result.stdout or "", result.stderr or ""))
    except Exception as exc:  # noqa: BLE001 - secondary evidence never masks the primary failure
        ctx.log.append(f"log capture failed: {type(exc).__name__}: {exc}\n")


GATE_FUNCS: dict[str, tuple[object, bool]] = {
    "docker-config": (gate_config, False),
    "docker-build": (gate_build, True),
    "docker-smoke": (gate_smoke, True),
    "docker-persistence": (gate_persistence, True),
    "docker-asr-smoke": (gate_asr_smoke, True),
    "docker-e2e": (gate_e2e, True),
}


def _run_cleanup_step(ctx: GateContext, check: str, cmd: list[str]) -> tuple[bool, str]:
    ctx.commands.append(" ".join(cmd))
    ctx.log.append(f"\n== [{check}] {' '.join(cmd)}\n")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=ctx.compose_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=CLEANUP_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - cleanup failure is reported, never fatal to the runner
        detail = f"{type(exc).__name__}: {exc}"
        ctx.log.append(detail + "\n")
        return False, detail
    stdout, stderr = result.stdout or "", result.stderr or ""
    ctx.log.append(stdout)
    ctx.log.append(stderr)
    if result.returncode != 0:
        return False, _signature(stdout, stderr)
    return True, ""


def compose_cleanup(ctx: GateContext) -> tuple[bool, str]:
    """Down exactly this test project, including its project-scoped volumes."""
    cmd = [
        *compose_base(ctx.project), "--profile", "e2e", "down",
        "--remove-orphans", "-v", "--rmi", "local", "--timeout", "30",
    ]
    return _run_cleanup_step(ctx, "scoped_compose_down", cmd)


def run_gate(gate: str, project: str | None = None) -> int:
    """Run one gate, write compact JSON + raw log, return 0 PASS / 1 FAIL / 2 bad input."""
    entry = GATE_FUNCS.get(gate)
    if entry is None:
        return 2
    gate_fn, lifecycle = entry
    try:
        project_name = resolve_project_name(project)
        port = resolve_port(project_name)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 2

    ctx = GateContext(gate=gate, project=project_name, port=port, timeout=float(TIMEOUTS[gate]))
    status, check, error_signature = "PASS", gate, ""
    cleanup_report: list[dict] = []
    start = time.monotonic()
    try:
        gate_fn(ctx)
    except GateError as exc:
        status, check, error_signature = "FAIL", exc.check, exc.error_signature
    except Exception as exc:  # noqa: BLE001 - still report and run scoped cleanup on unexpected failures
        status, check = "FAIL", "gate_runner_exception"
        error_signature = f"{type(exc).__name__}: {exc}"[:500]

    if lifecycle:
        if status == "FAIL" and gate in {"docker-smoke", "docker-persistence", "docker-asr-smoke", "docker-e2e"}:
            _capture_container_logs(ctx)
        ok, detail = compose_cleanup(ctx)
        cleanup_report.append({"step": "scoped_compose_down", "status": "ok" if ok else "fail", "detail": detail})
        if not ok and status == "PASS":
            status, check, error_signature = "FAIL", "scoped_cleanup", detail
        ok, detail = scoped_rmtree(ctx.project_dir)
        cleanup_report.append({"step": "scoped_data_cleanup", "status": "ok" if ok else "fail", "detail": detail})
        if not ok and status == "PASS":
            status, check, error_signature = "FAIL", "scoped_cleanup", detail
    duration = time.monotonic() - start

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    raw_log = "".join(ctx.log) or "(no output)\n"
    (LOGS_DIR / f"{gate}.log").write_text(raw_log, encoding="utf-8")
    build_dir = build_artifacts_dir()
    build_logs = build_dir / "logs"
    build_logs.mkdir(parents=True, exist_ok=True)
    build_log = build_logs / f"docker-{gate}.log"
    build_log.write_text(raw_log, encoding="utf-8")

    report = {
        "status": status,
        "gate": gate,
        "check": check,
        "error_signature": error_signature,
        "command": ctx.failed_command or (ctx.commands[-1] if ctx.commands else ""),
        "commands": list(ctx.commands),
        "artifact": build_log.relative_to(ROOT).as_posix(),
        "duration_seconds": round(duration, 2),
        "timeout_seconds": TIMEOUTS[gate],
        "project": ctx.project,
        "port": ctx.port,
        "data_root": f"artifacts/gates/docker/projects/{ctx.project}/data",
        "cleanup": cleanup_report,
        "runner": "scripts/docker_gate.py",
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = ARTIFACTS_DIR / f"{gate}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (build_dir / f"docker-{gate}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[{status}] {gate} ({round(duration, 2)}s) -> {report_path.relative_to(ROOT).as_posix()}")
    return 0 if status == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python scripts/docker_gate.py <gate> [--project NAME]")
        print(f"gates: {', '.join(GATE_FUNCS)}")
        return 0 if argv else 2
    gate = argv[0]
    project = None
    if "--project" in argv:
        index = argv.index("--project")
        if index + 1 < len(argv):
            project = argv[index + 1]
    return run_gate(gate, project)


if __name__ == "__main__":
    sys.exit(main())
