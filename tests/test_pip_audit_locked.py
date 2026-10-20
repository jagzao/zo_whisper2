from __future__ import annotations

from pathlib import Path

from scripts import pip_audit_locked as locked_audit


def _result(status: str, vulnerabilities: list[dict] | None = None) -> dict:
    return {"status": status, "vulnerabilities": vulnerabilities or [], "exit_code": 0}


def test_system_trust_is_injected_before_cli(tmp_path):
    order = []

    def inject():
        order.append("trust")

    def cli(args):
        order.append("cli")
        return _result("CLEAN")

    report = locked_audit.audit_lock(tmp_path / "requirements.lock.txt", cli, inject)
    assert order == ["trust", "cli"]
    assert report["status"] == "CLEAN"


def test_wrapper_uses_pinned_lock_without_dependency_resolution(tmp_path):
    args = locked_audit.build_cli_args(tmp_path / "requirements.lock.txt", "pypi")
    assert "--no-deps" in args
    assert "--disable-pip" in args
    assert args[args.index("--progress-spinner") + 1] == "off"
    assert args[args.index("--format") + 1] == "json"
    assert args[args.index("--vulnerability-service") + 1] == "pypi"
    assert args[args.index("-r") + 1] == str(tmp_path / "requirements.lock.txt")
    assert "--trusted-host" not in args
    assert "--insecure" not in args
    source = Path(locked_audit.__file__).read_text(encoding="utf-8")
    assert "verify=False" not in source
    assert "CERT_NONE" not in source
    assert "http://" not in source


def test_pypi_clean_has_no_fallback(tmp_path):
    services = []
    def cli(args):
        services.append(args[args.index("--vulnerability-service") + 1])
        return _result("CLEAN")
    report = locked_audit.audit_lock(tmp_path / "lock.txt", cli, lambda: None)
    assert report["status"] == "CLEAN"
    assert report["service_used"] == "pypi"
    assert report["transport_fallback"] is False
    assert services == ["pypi"]


def test_pypi_vulnerability_is_reported_without_fallback(tmp_path):
    calls = []
    vuln = {"package": "lib", "version": "1.2", "advisory": "GHSA-test", "fixed_versions": ["1.3"]}
    def cli(args):
        calls.append(args)
        return _result("VULNERABLE", [vuln])
    report = locked_audit.audit_lock(tmp_path / "lock.txt", cli, lambda: None)
    assert report["status"] == "VULNERABLE"
    assert report["vulnerabilities"] == [vuln]
    assert report["service_used"] == "pypi"
    assert report["transport_fallback"] is False
    assert len(calls) == 1


def test_pypi_transport_failure_falls_back_once_to_osv_clean(tmp_path):
    services = []
    def cli(args):
        service = args[args.index("--vulnerability-service") + 1]
        services.append(service)
        return _result("TRANSPORT_ERROR" if service == "pypi" else "CLEAN")
    report = locked_audit.audit_lock(tmp_path / "lock.txt", cli, lambda: None)
    assert report["status"] == "CLEAN"
    assert report["service_used"] == "osv"
    assert report["transport_fallback"] is True
    assert services == ["pypi", "osv"]


def test_both_services_transport_failure_stops_after_fallback(tmp_path):
    services = []
    def cli(args):
        services.append(args[args.index("--vulnerability-service") + 1])
        return _result("TRANSPORT_ERROR")
    report = locked_audit.audit_lock(tmp_path / "lock.txt", cli, lambda: None)
    assert report["status"] == "TRANSPORT_ERROR"
    assert report["service_used"] == "osv"
    assert report["transport_fallback"] is True
    assert services == ["pypi", "osv"]


def test_malformed_cli_json_is_invalid_report(monkeypatch):
    monkeypatch.setattr(locked_audit.runpy, "run_module", lambda *args, **kwargs: print("not json"))
    result = locked_audit._run_cli(["-r", "lock.txt"])
    assert result["status"] == "INVALID_REPORT"


def test_wrapper_never_prints_environment_secret_values(monkeypatch, capsys, tmp_path):
    secret_values = {
        "PIP_CERT": "CERT_SECRET_SENTINEL",
        "REQUESTS_CA_BUNDLE": "REQUESTS_SECRET_SENTINEL",
        "CURL_CA_BUNDLE": "CURL_SECRET_SENTINEL",
        "SSL_CERT_FILE": "SSL_SECRET_SENTINEL",
        "HTTPS_PROXY": "https://proxy-user:proxy-pass@proxy.invalid",
    }
    for name, value in secret_values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(locked_audit, "audit_lock", lambda lock: {
        "status": "TRANSPORT_ERROR", "service_used": "osv", "transport_fallback": True,
        "vulnerabilities": [], "error_type": "SSLError",
    })
    assert locked_audit.main(["--lockfile", str(tmp_path / "lock.txt")]) == 2
    output = capsys.readouterr().out
    assert "SSLError" in output
    assert all(value not in output for value in secret_values.values())
