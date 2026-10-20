from __future__ import annotations

import dataclasses
from pathlib import Path

from cryptography import x509

from transcript_pipeline import lan_access
from transcript_pipeline.dashboard import app as dashboard

LAN_IP = "192.168.50.20"


def _enable_lan(monkeypatch, runtime_dir: Path | None = None) -> None:
    monkeypatch.setattr(dashboard, "SETTINGS", dataclasses.replace(dashboard.SETTINGS, lan_access=True))
    monkeypatch.setattr(dashboard, "_LAN_HOST_ALLOWLIST", {LAN_IP})
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: [LAN_IP])
    monkeypatch.setattr(lan_access, "advertised_lan_ipv4_addresses", lambda configured=(): [LAN_IP])
    if runtime_dir is not None:
        monkeypatch.setattr(lan_access, "default_runtime_dir", lambda: runtime_dir)


def test_mobile_setup_shows_download_steps_and_secure_url(monkeypatch):
    _enable_lan(monkeypatch)

    response = dashboard.app.test_client().get("/setup", headers={"Host": f"{LAN_IP}:5000"})

    assert response.status_code == 200
    assert b"Whisper-LAN-Local-CA.cer" in response.data
    assert b"confirm installing it as a CA certificate" in response.data
    assert f"https://{LAN_IP}:5001/".encode() in response.data
    assert response.headers["Cache-Control"].startswith("no-store")


def test_certificate_route_returns_only_public_der_root(monkeypatch, tmp_path):
    _enable_lan(monkeypatch, tmp_path)
    root = tmp_path / lan_access.CA_FILE_NAME
    lan_access.generate_lan_chain(
        tmp_path / "leaf.pem", tmp_path / "leaf-key.pem", root, ["localhost", "127.0.0.1", LAN_IP]
    )

    client = dashboard.app.test_client()
    response = client.get("/setup/certificate", headers={"Host": f"{LAN_IP}:5000"})

    assert response.status_code == 200
    assert "Whisper-LAN-Local-CA.cer" in response.headers["Content-Disposition"]
    assert response.mimetype == "application/pkix-cert"
    certificate = x509.load_der_x509_certificate(response.data)
    assert certificate.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value == "Whisper LAN Local CA"
    assert b"PRIVATE KEY" not in response.data
    assert client.get("/setup/key", headers={"Host": f"{LAN_IP}:5000"}).status_code == 302


def test_advertised_lan_address_prefers_host_certificate_san(monkeypatch, tmp_path):
    lan_access.generate_lan_chain(
        tmp_path / "leaf.pem", tmp_path / "leaf-key.pem", tmp_path / lan_access.CA_FILE_NAME,
        ["localhost", "127.0.0.1", LAN_IP],
    )
    (tmp_path / lan_access.CERT_FILE_NAME).write_bytes((tmp_path / "leaf.pem").read_bytes())
    monkeypatch.setattr(lan_access, "default_runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(lan_access, "local_ipv4_addresses", lambda: ["172.19.0.2"])

    assert lan_access.advertised_lan_ipv4_addresses() == [LAN_IP, "172.19.0.2"]


def test_desktop_dashboard_has_lan_qr_and_dismissal(monkeypatch):
    _enable_lan(monkeypatch)
    client = dashboard.app.test_client()

    response = client.get("/", headers={"Host": "localhost:5000"})

    assert response.status_code == 200
    assert f"http://{LAN_IP}:5003/setup".encode() in response.data
    assert b"/setup/qr.svg" in response.data
    assert b"whisperMobileSetupDismissed" in response.data
    qr = client.get("/setup/qr.svg", headers={"Host": "localhost:5000"})
    assert qr.status_code == 200
    assert qr.mimetype == "image/svg+xml"
    assert b"<svg" in qr.data


def test_mobile_urls_use_configured_public_ports(monkeypatch, tmp_path):
    _enable_lan(monkeypatch, tmp_path)
    monkeypatch.setenv("ZMI_TRUST_PROXY", "true")
    monkeypatch.setenv("ZMI_LAN_HTTP_PORT", "5500")
    monkeypatch.setenv("ZMI_HTTPS_PORT", "5443")
    monkeypatch.setattr(
        dashboard,
        "SETTINGS",
        dataclasses.replace(dashboard.SETTINGS, lan_access=True, dashboard_cert_file=None),
    )
    lan_access.generate_lan_chain(
        tmp_path / lan_access.CERT_FILE_NAME,
        tmp_path / lan_access.KEY_FILE_NAME,
        tmp_path / lan_access.CA_FILE_NAME,
        ["localhost", "127.0.0.1", LAN_IP],
    )
    client = dashboard.app.test_client()

    home = client.get("/", headers={"Host": "localhost:5000"})
    setup = client.get("/setup", headers={"Host": f"{LAN_IP}:5500"})
    network = client.get("/api/network", headers={"Host": "localhost:5000"}).get_json()

    assert f"http://{LAN_IP}:5500/setup".encode() in home.data
    assert f"https://{LAN_IP}:5443/".encode() in setup.data
    assert network["urls"] == [f"https://{LAN_IP}:5443/"]
    assert network["http_port"] == 5500
    assert network["https_port"] == 5443
    assert network["cert_fingerprint_sha256"] == lan_access.certificate_fingerprint(
        tmp_path / lan_access.CERT_FILE_NAME
    )


def test_setup_qr_encodes_configured_http_port(monkeypatch):
    _enable_lan(monkeypatch)
    monkeypatch.setenv("ZMI_LAN_HTTP_PORT", "5500")
    import qrcode

    encoded: list[str] = []

    class FakeQr:
        def __init__(self, **_kwargs):
            pass

        def add_data(self, value: str) -> None:
            encoded.append(value)

        def make(self, *, fit: bool) -> None:
            assert fit is True

        def make_image(self, *, image_factory):
            return type("Image", (), {"to_string": lambda self: "<svg></svg>"})()

    monkeypatch.setattr(qrcode, "QRCode", FakeQr)
    response = dashboard.app.test_client().get(
        "/setup/qr.svg", headers={"Host": "localhost:5000"}
    )

    assert response.status_code == 200
    assert encoded == [f"http://{LAN_IP}:5500/setup"]


def test_lan_http_only_serves_bootstrap_and_redirects_other_paths(monkeypatch):
    _enable_lan(monkeypatch)
    client = dashboard.app.test_client()

    response = client.get("/api/health", headers={"Host": f"{LAN_IP}:5000"})

    assert response.status_code == 302
    assert response.headers["Location"] == f"https://{LAN_IP}:5001/"


def test_secure_setup_cookie_redirects_back_to_https(monkeypatch):
    _enable_lan(monkeypatch)
    client = dashboard.app.test_client()
    client.set_cookie("whisper_secure_setup", "1", domain=LAN_IP)

    response = client.get("/setup", headers={"Host": f"{LAN_IP}:5000"})

    assert response.status_code == 302
    assert response.headers["Location"] == f"https://{LAN_IP}:5001/"


def test_setup_is_not_available_when_lan_mode_is_off(monkeypatch):
    monkeypatch.setattr(dashboard, "SETTINGS", dataclasses.replace(dashboard.SETTINGS, lan_access=False))
    monkeypatch.setattr(dashboard, "_LAN_HOST_ALLOWLIST", set())

    response = dashboard.app.test_client().get("/setup", headers={"Host": f"{LAN_IP}:5000"})

    assert response.status_code == 403
