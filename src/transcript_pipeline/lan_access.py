"""Mobile/LAN access helpers for the dashboard (W25).

The dashboard is loopback-only by default. This module implements the
explicit-opt-in pieces required to reach it from a phone on the same Wi-Fi:

- detect the machine's private LAN IPv4 addresses (used for the request
  Host/Origin allowlist and for advertised phone URLs);
- generate a self-signed HTTPS certificate whose Subject Alternative Name
  covers the configured hosts and detected LAN IPs (browsers grant camera
  permission on `https://` origins only, and only when the certificate is
  trusted by the phone);
- build a TLS 1.2+ server context for the dashboard.

Nothing here performs network I/O. The private key is written to a runtime
directory that must stay outside Git (see docs/ops/MOBILE_LAN_ACCESS.md).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

CERT_FILE_NAME = "dashboard-lan-cert.pem"
KEY_FILE_NAME = "dashboard-lan-key.pem"
CA_FILE_NAME = "dashboard-lan-ca.pem"
DEFAULT_COMMON_NAME = "whisper.local"
CERT_DAYS = 825  # ~27 months: within modern browser certificate lifetime caps


class LanCertError(RuntimeError):
    """Certificate generation is unavailable (missing `cryptography`)."""


@dataclass(frozen=True)
class LanCertResult:
    cert_path: Path
    key_path: Path
    ca_path: Path
    fingerprint_sha256: str
    hosts: tuple[str, ...]


def is_private_ipv4(value: str) -> bool:
    """True for RFC1918 private IPv4 addresses (10/8, 172.16/12, 192.168/16)."""
    try:
        addr = ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return any(addr in net for net in _PRIVATE_V4_NETWORKS)


_PRIVATE_V4_NETWORKS = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


def local_ipv4_addresses() -> list[str]:
    """Private LAN IPv4 addresses of this machine, sorted and de-duplicated.

    Uses psutil when available and falls back to the stdlib hostname lookup.
    Loopback and link-local (169.254/16) addresses are excluded — they cannot
    be reached from another device on the Wi-Fi.
    """
    addresses: set[str] = set()
    try:
        import psutil

        for _name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if getattr(addr.family, "name", str(addr.family)) != "AF_INET":
                    continue
                value = str(getattr(addr, "address", "") or "")
                if is_private_ipv4(value):
                    addresses.add(value)
    except Exception:
        addresses = set()

    if not addresses:
        try:
            info = socket.gethostbyname_ex(socket.gethostname())
            for value in info[2]:
                if is_private_ipv4(value):
                    addresses.add(value)
        except OSError:
            pass
    return sorted(addresses)


def normalize_host(value: str) -> str | None:
    """Normalizes a Host/SAN entry: strips brackets and trailing dots, lowercases.

    Returns None for empty input. IP literals and DNS names are both
    accepted; no resolution is attempted.
    """
    candidate = (value or "").strip().strip("[]").rstrip(".").lower()
    if not candidate:
        return None
    if candidate.startswith("::ffff:"):
        candidate = candidate[len("::ffff:") :]
    return candidate


def _split_hosts(hosts: Iterable[str]) -> tuple[list[str], list[str]]:
    """Splits entries into (dns_names, ip_addresses), preserving first-seen order."""
    dns_names: list[str] = []
    ip_addresses: list[str] = []
    for raw in hosts:
        normalized = normalize_host(raw)
        if not normalized:
            continue
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            if normalized not in dns_names:
                dns_names.append(normalized)
        else:
            if normalized not in ip_addresses:
                ip_addresses.append(normalized)
    return dns_names, ip_addresses


def collect_hosts(configured: Iterable[str], *, include_detected: bool = True) -> tuple[str, ...]:
    """Full SAN/advertised host set: configured entries + detected LAN IPs.

    `localhost` and `127.0.0.1` are always included so the same certificate
    also works over loopback HTTPS.
    """
    hosts: list[str] = ["localhost", "127.0.0.1"]
    for raw in configured:
        normalized = normalize_host(raw)
        if normalized and normalized not in hosts:
            hosts.append(normalized)
    if include_detected:
        for value in local_ipv4_addresses():
            if value not in hosts:
                hosts.append(value)
    return tuple(hosts)


def generate_self_signed(cert_path: Path, key_path: Path, hosts: Iterable[str]) -> str:
    """Writes a single self-signed cert/key pair with a SAN covering `hosts`.

    Returns the SHA-256 fingerprint. Kept for clients that pin/disable
    verification; the phone-trust path uses `generate_lan_chain` so the
    installed root is a proper CA, not the server end-entity.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
    except ImportError as exc:  # pragma: no cover - exercised via LanCertError tests
        raise LanCertError(
            "the 'cryptography' package is required to generate the LAN TLS certificate "
            "(install with: pip install cryptography)"
        ) from exc

    dns_names, ip_addresses = _split_hosts(hosts)
    if not dns_names and not ip_addresses:
        raise LanCertError("at least one host or IP is required for the certificate SAN")

    common_name = dns_names[0] if dns_names else DEFAULT_COMMON_NAME
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    sans: list[x509.GeneralName] = [x509.DNSName(name) for name in dns_names]
    sans.extend(x509.IPAddress(ipaddress.ip_address(value)) for value in ip_addresses)

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CERT_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_key_usage(ca=True), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        )
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .sign(key, hashes.SHA256())
    )
    fingerprint = format_fingerprint(cert.fingerprint(hashes.SHA256()))

    _write_private(
        cert_path,
        cert.public_bytes(serialization.Encoding.PEM),
    )
    _write_private(
        key_path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return fingerprint


def _key_usage(ca: bool):
    from cryptography import x509

    return x509.KeyUsage(
        digital_signature=True,
        content_commitment=False,
        key_encipherment=not ca,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=ca,
        crl_sign=ca,
        encipher_only=False,
        decipher_only=False,
    )


def generate_lan_chain(
    cert_path: Path,
    key_path: Path,
    ca_cert_path: Path,
    hosts: Iterable[str],
) -> str:
    """Writes a local CA certificate plus a server cert/key signed by it.

    Returns the server certificate SHA-256 fingerprint. The phone/browser
    trusts `ca_cert_path` (installed once as a user root certificate); the
    server presents only `cert_path`, so a proper CA -> leaf chain is built
    and no loopback/self-anchor ambiguity exists.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError as exc:  # pragma: no cover
        raise LanCertError(
            "the 'cryptography' package is required to generate the LAN TLS certificate "
            "(install with: pip install cryptography)"
        ) from exc

    dns_names, ip_addresses = _split_hosts(hosts)
    if not dns_names and not ip_addresses:
        raise LanCertError("at least one host or IP is required for the certificate SAN")

    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Whisper LAN Local CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CERT_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_key_usage(ca=True), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(DEFAULT_COMMON_NAME)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    common_name = dns_names[0] if dns_names else DEFAULT_COMMON_NAME
    server_key = ec.generate_private_key(ec.SECP256R1())
    sans: list[x509.GeneralName] = [x509.DNSName(name) for name in dns_names]
    sans.extend(x509.IPAddress(ipaddress.ip_address(value)) for value in ip_addresses)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CERT_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(_key_usage(ca=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    fingerprint = format_fingerprint(server_cert.fingerprint(hashes.SHA256()))

    _write_private(ca_cert_path, ca_cert.public_bytes(serialization.Encoding.PEM))
    _write_private(cert_path, server_cert.public_bytes(serialization.Encoding.PEM))
    _write_private(
        key_path,
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return fingerprint


def provision_lan_certificate(runtime_dir: Path, configured_hosts: Iterable[str] = ()) -> LanCertResult:
    """Creates (or reuses) the dashboard HTTPS cert/key under `runtime_dir`.

    The directory and the private key are permission-restricted and must not
    be committed. `configured_hosts` is combined with detected LAN IPs and
    loopback before being written into the SAN.
    """
    hosts = collect_hosts(configured_hosts)
    cert_path = runtime_dir / CERT_FILE_NAME
    key_path = runtime_dir / KEY_FILE_NAME
    ca_path = runtime_dir / CA_FILE_NAME
    runtime_dir.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(runtime_dir)

    if (
        cert_path.exists()
        and key_path.exists()
        and ca_path.exists()
        and set(certificate_sans(cert_path)) == set(hosts)
    ):
        fingerprint = certificate_fingerprint(cert_path)
    else:
        fingerprint = generate_lan_chain(cert_path, key_path, ca_path, hosts)
    for path in (ca_path, cert_path, key_path):
        _restrict_permissions(path)
    return LanCertResult(
        cert_path=cert_path,
        key_path=key_path,
        ca_path=ca_path,
        fingerprint_sha256=fingerprint,
        hosts=hosts,
    )


def certificate_fingerprint(cert_path: Path) -> str:
    """SHA-256 fingerprint of the certificate file (phone trust verification)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return format_fingerprint(cert.fingerprint(hashes.SHA256()))


def certificate_sans(cert_path: Path) -> list[str]:
    """Reads back the SAN entries of a certificate (verification/debug tool)."""
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    try:
        extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return []
    entries: list[str] = []
    for name in extension:
        value = getattr(name, "value", None)
        if value is not None:
            entries.append(str(value))
    return entries


def format_fingerprint(der_digest: bytes) -> str:
    return ":".join(f"{b:02x}" for b in der_digest)


def build_server_ssl_context(cert_file: Path, key_file: Path):
    """TLS 1.2+ server context for the dashboard; raises if files are missing."""
    import ssl

    if not cert_file.is_file() or not key_file.is_file():
        from transcript_pipeline.errors import ConfigurationError

        raise ConfigurationError(
            "DASHBOARD_CERT/DASHBOARD_KEY files do not exist — run the LAN certificate "
            "setup (python scripts/setup_lan_certificate.py) first."
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_file), str(key_file))
    return context


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
    _restrict_permissions(path)


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def default_runtime_dir() -> Path:
    """Gitignored runtime directory for the dashboard cert/key."""
    from transcript_pipeline.config import DATA_ROOT

    return DATA_ROOT / "lan-access"


def main(argv: list[str] | None = None) -> int:
    """`python -m transcript_pipeline.lan_access` — provision the HTTPS cert/key.

    Prints the certificate path, its SHA-256 fingerprint and the SAN entries.
    The private key contents are never printed.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m transcript_pipeline.lan_access",
        description="Provision the dashboard HTTPS cert/key for mobile/LAN access.",
    )
    parser.add_argument(
        "--runtime-dir",
        type=str,
        default=None,
        help="output directory (default: <DATA_ROOT>/lan-access) — kept outside Git",
    )
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="extra hostname or IP for the certificate SAN (repeatable)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="dashboard port to advertise in the printed phone URLs",
    )
    args = parser.parse_args(argv)

    # Read config directly (not Settings.from_env()): provisioning a
    # certificate must work even while DASHBOARD_HOST still points at a value
    # the running server would only accept once LAN mode is enabled.
    import os

    from transcript_pipeline.config import load_env

    load_env()

    runtime_dir = Path(args.runtime_dir) if args.runtime_dir else default_runtime_dir()
    raw_hosts = args.host or [
        part.strip() for part in os.getenv("ZMI_LAN_HOSTS", "").split(",") if part.strip()
    ]
    configured = list(raw_hosts)
    try:
        port = args.port or int(os.getenv("DASHBOARD_PORT", "5000"))
    except ValueError:
        port = 5000
    result = provision_lan_certificate(runtime_dir, configured)

    print(f"cert: {result.cert_path}")
    print(f"key: {result.key_path}")
    print(f"ca: {result.ca_path}")
    print(f"fingerprint-sha256: {result.fingerprint_sha256}")
    print(f"ca-fingerprint-sha256: {certificate_fingerprint(result.ca_path)}")
    print("san: " + ",".join(result.hosts))
    print(f"trust-install: copy {result.ca_path} to the phone and install it as a root certificate")
    for host in result.hosts:
        if host in {"localhost", "127.0.0.1"}:
            continue
        if is_private_ipv4(host):
            print(f"phone-url: https://{host}:{port}/")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    import sys

    sys.exit(main())

