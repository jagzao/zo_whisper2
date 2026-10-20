"""W25 unit tests: explicit mobile/LAN opt-in settings and certificate helpers.

Loopback defaults must remain unchanged while LAN mode is off. Synthetic hosts
only — no network I/O beyond certificate generation.
"""

from __future__ import annotations

import os
import re
import types

import pytest

from transcript_pipeline import lan_access
from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.settings import Settings

_LAN_ENV_KEYS = (
    "DASHBOARD_HOST", "DASHBOARD_PORT", "DASHBOARD_CERT", "DASHBOARD_KEY",
    "ZMI_LAN_ACCESS", "ZMI_LAN_HOSTS", "ZMI_CONTAINER_MODE",
    "ZMI_ALLOWED_EXPORT_ROOTS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Never pull in the real scan_config.env (which may set a LAN host).
    monkeypatch.setattr("transcript_pipeline.settings.load_env", lambda: None)
    for key in _LAN_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in list(os.environ):
        if key in _LAN_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)


# ── Settings: opt-in LAN mode ─────────────────────────────────────────────

def test_lan_access_defaults_off():
    assert Settings.from_env().lan_access is False


def test_loopback_default_preserved():
    assert Settings.from_env().dashboard_host == "127.0.0.1"


def test_wildcard_bind_rejected_without_lan_mode(monkeypatch):
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_lan_mode_allows_wildcard_bind(monkeypatch):
    monkeypatch.setenv("ZMI_LAN_ACCESS", "true")
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    assert Settings.from_env().dashboard_host == "0.0.0.0"


def test_lan_mode_accepts_loopback(monkeypatch):
    monkeypatch.setenv("ZMI_LAN_ACCESS", "true")
    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    assert Settings.from_env().dashboard_host == "127.0.0.1"


def test_lan_mode_still_rejects_specific_lan_ip(monkeypatch):
    # The wildcard bind is the supported path; a hardcoded LAN IP is not.
    monkeypatch.setenv("ZMI_LAN_ACCESS", "true")
    monkeypatch.setenv("DASHBOARD_HOST", "192.168.1.10")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_lan_hosts_parsed_as_comma_list(monkeypatch):
    monkeypatch.setenv("ZMI_LAN_HOSTS", "whisper.local, 192.168.1.50 ,")
    assert Settings.from_env().lan_hosts == ("whisper.local", "192.168.1.50")


def test_cert_without_key_rejected(monkeypatch):
    monkeypatch.setenv("DASHBOARD_CERT", "cert.pem")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_key_without_cert_rejected(monkeypatch):
    monkeypatch.setenv("DASHBOARD_KEY", "key.pem")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_cert_and_key_together_accepted(monkeypatch):
    monkeypatch.setenv("DASHBOARD_CERT", "cert.pem")
    monkeypatch.setenv("DASHBOARD_KEY", "key.pem")
    settings = Settings.from_env()
    assert settings.dashboard_cert_file is not None and settings.dashboard_key_file is not None


# ── lan_access: address/host helpers ──────────────────────────────────────

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10.0.0.5", True), ("172.16.0.1", True), ("172.31.255.254", True),
        ("192.168.1.20", True), ("127.0.0.1", False), ("169.254.1.1", False),
        ("8.8.8.8", False), ("172.32.0.1", False), ("not-an-ip", False),
    ],
)
def test_is_private_ipv4(value, expected):
    assert lan_access.is_private_ipv4(value) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("[::1]", "::1"),
        ("Whisper.Local.", "whisper.local"),
        ("::ffff:192.168.1.5", "192.168.1.5"),
        ("   ", None),
    ],
)
def test_normalize_host(raw, expected):
    assert lan_access.normalize_host(raw) == expected


def test_collect_hosts_includes_loopback_and_configured(monkeypatch):
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: ["192.168.1.50"])
    hosts = lan_access.collect_hosts(["whisper.local"])
    assert hosts[0] == "localhost"
    assert "127.0.0.1" in hosts
    assert "whisper.local" in hosts
    assert "192.168.1.50" in hosts


def _fake_psutil(addresses: list[str]) -> types.SimpleNamespace:
    def net_if_addrs():
        fam = types.SimpleNamespace(name="AF_INET")
        return {"eth0": [types.SimpleNamespace(family=fam, address=a) for a in addresses]}
    return types.SimpleNamespace(net_if_addrs=net_if_addrs)


def test_local_ipv4_addresses_filters_loopback_and_linklocal(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules, "psutil",
        _fake_psutil(["192.168.1.50", "127.0.0.1", "169.254.10.10", "8.8.8.8", "192.168.1.50"]),
    )
    assert lan_access.local_ipv4_addresses() == ["192.168.1.50"]


# ── lan_access: certificate generation ────────────────────────────────────

def test_generate_self_signed_san_and_fingerprint(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    fingerprint = lan_access.generate_self_signed(
        cert, key, ["whisper.local", "192.168.1.50", "127.0.0.1"]
    )
    assert re.fullmatch(r"([0-9a-f]{2}:){31}[0-9a-f]{2}", fingerprint)
    assert cert.is_file() and key.is_file()

    sans = lan_access.certificate_sans(cert)
    assert "whisper.local" in sans
    assert "192.168.1.50" in sans
    assert "127.0.0.1" in sans


def test_provision_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: ["192.168.1.50"])
    first = lan_access.provision_lan_certificate(tmp_path / "runtime", ["whisper.local"])
    second = lan_access.provision_lan_certificate(tmp_path / "runtime", ["whisper.local"])
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first.cert_path.is_file() and first.key_path.is_file()
    assert first.ca_path.is_file()
    assert "192.168.1.50" in first.hosts


def test_lan_chain_server_cert_issued_by_ca(tmp_path):
    from cryptography import x509

    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    ca = tmp_path / "ca.pem"
    lan_access.generate_lan_chain(cert, key, ca, ["whisper.local", "192.168.1.50"])

    server = x509.load_pem_x509_certificate(cert.read_bytes())
    authority = x509.load_pem_x509_certificate(ca.read_bytes())
    server.verify_directly_issued_by(authority)
    assert authority.subject == authority.issuer
    assert "192.168.1.50" in lan_access.certificate_sans(cert)


def test_lan_chain_tls_handshake_verifies_against_ca(tmp_path):
    import socket
    import ssl
    import threading

    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    ca = tmp_path / "ca.pem"
    lan_access.generate_lan_chain(cert, key, ca, ["localhost", "127.0.0.1"])
    server_ctx = lan_access.build_server_ssl_context(cert, key)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    port = listener.getsockname()[1]

    def serve() -> None:
        for _ in range(2):
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            try:
                with server_ctx.wrap_socket(conn, server_side=True) as tls:
                    tls.recv(1)
            except OSError:
                continue

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        probe_ctx = ssl._create_unverified_context()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with probe_ctx.wrap_socket(raw, server_hostname="127.0.0.1") as probe:
                    served = probe.getpeercert(binary_form=True)
        except ConnectionResetError:
            pytest.skip("host-level TLS interception resets loopback TLS handshakes")
        if _served_cert_is_intercepted(served):
            pytest.skip(
                "host-level HTTPS interception detected: the peer certificate differs from "
                "the lan_access server certificate, so live CA trust cannot be evaluated here"
            )

        client_ctx = ssl.create_default_context(cafile=str(ca))
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with client_ctx.wrap_socket(raw, server_hostname="127.0.0.1") as tls:
                assert tls.version() in ("TLSv1.2", "TLSv1.3")
    finally:
        thread.join(timeout=5)
        listener.close()


def _served_cert_is_intercepted(der: bytes) -> bool:
    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    return "Whisper LAN Local CA" not in cert.issuer.rfc4514_string()


def test_provision_without_detected_addresses_uses_loopback(tmp_path, monkeypatch):
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: [])
    result = lan_access.provision_lan_certificate(tmp_path / "runtime")
    assert "127.0.0.1" in result.hosts


def test_provision_refreshes_certificate_when_lan_ip_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: ["192.168.1.10"])
    runtime = tmp_path / "runtime"
    first = lan_access.provision_lan_certificate(runtime)
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: ["192.168.1.11"])
    second = lan_access.provision_lan_certificate(runtime)
    assert first.fingerprint_sha256 != second.fingerprint_sha256
    assert "192.168.1.11" in lan_access.certificate_sans(second.cert_path)


def test_build_server_ssl_context_requires_files(tmp_path):
    with pytest.raises(ConfigurationError):
        lan_access.build_server_ssl_context(tmp_path / "missing.pem", tmp_path / "missing-key.pem")


def test_build_server_ssl_context_loads_cert(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    lan_access.generate_self_signed(cert, key, ["localhost", "127.0.0.1"])
    context = lan_access.build_server_ssl_context(cert, key)
    import ssl

    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
