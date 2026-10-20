"""Audit one fully pinned requirements lock using the OS certificate store."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import runpy
import sys
from collections.abc import Callable
from pathlib import Path

STATUS_CLEAN = "CLEAN"
STATUS_VULNERABLE = "VULNERABLE"
STATUS_TRANSPORT_ERROR = "TRANSPORT_ERROR"
STATUS_INVALID_REPORT = "INVALID_REPORT"


def build_cli_args(lockfile: Path, service: str) -> list[str]:
    return [
        "--no-deps",
        "--disable-pip",
        "--progress-spinner",
        "off",
        "--format",
        "json",
        "--vulnerability-service",
        service,
        "-r",
        str(lockfile),
    ]


def _transport_failure(stderr: str) -> bool:
    lower = stderr.lower()
    return any(
        marker in lower
        for marker in ("vulnerability service", "connection", "ssl", "certificate", "timed out", "network", "dns", "proxy")
    )


def _run_cli(args: list[str]) -> dict[str, object]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    previous_argv = sys.argv
    exit_code = 0
    try:
        sys.argv = ["pip_audit", *args]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_module("pip_audit", run_name="__main__")
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else int(exc.code is not None)
    except Exception as exc:  # Never expose exception text, which can contain proxy details.
        stderr.write(type(exc).__name__)
        exit_code = 1
    finally:
        sys.argv = previous_argv

    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("dependencies"), list):
        return {
            "status": STATUS_TRANSPORT_ERROR if _transport_failure(stderr.getvalue()) else STATUS_INVALID_REPORT,
            "exit_code": exit_code or 1,
            "vulnerabilities": [],
        }

    vulnerabilities = []
    for dependency in payload["dependencies"]:
        if not isinstance(dependency, dict):
            return {"status": STATUS_INVALID_REPORT, "exit_code": exit_code or 1, "vulnerabilities": []}
        vulns = dependency.get("vulns", [])
        if not isinstance(vulns, list):
            return {"status": STATUS_INVALID_REPORT, "exit_code": exit_code or 1, "vulnerabilities": []}
        for vuln in vulns:
            if not isinstance(vuln, dict):
                return {"status": STATUS_INVALID_REPORT, "exit_code": exit_code or 1, "vulnerabilities": []}
            vulnerabilities.append({
                "package": dependency.get("name"),
                "version": dependency.get("version"),
                "advisory": vuln.get("id"),
                "fixed_versions": vuln.get("fix_versions", []),
            })

    if vulnerabilities:
        return {"status": STATUS_VULNERABLE, "exit_code": exit_code or 1, "vulnerabilities": vulnerabilities}
    if exit_code == 0:
        return {"status": STATUS_CLEAN, "exit_code": 0, "vulnerabilities": []}
    return {"status": STATUS_TRANSPORT_ERROR, "exit_code": exit_code, "vulnerabilities": []}


def audit_lock(
    lockfile: Path,
    cli_runner: Callable[[list[str]], dict[str, object]] | None = None,
    trust_injector: Callable[[], None] | None = None,
) -> dict[str, object]:
    if trust_injector is None:
        import truststore

        trust_injector = truststore.inject_into_ssl
    trust_injector()
    if cli_runner is None:
        cli_runner = _run_cli

    first = cli_runner(build_cli_args(lockfile, "pypi"))
    first.update({"service_used": "pypi", "transport_fallback": False})
    if first["status"] != STATUS_TRANSPORT_ERROR:
        return first

    fallback = cli_runner(build_cli_args(lockfile, "osv"))
    fallback.update({"service_used": "osv", "transport_fallback": True})
    return fallback


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_lock(args.lockfile)
    except Exception as exc:
        report = {
            "status": STATUS_TRANSPORT_ERROR,
            "service_used": "none",
            "transport_fallback": False,
            "vulnerabilities": [],
            "error_type": type(exc).__name__,
        }
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return {STATUS_CLEAN: 0, STATUS_VULNERABLE: 1}.get(str(report["status"]), 2)


if __name__ == "__main__":
    raise SystemExit(main())
