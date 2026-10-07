"""TLS certificate and bearer-token provisioning for the K'ab ingest.

`provision()` writes, under a runtime directory that is outside version
control (the gitignored `kab-inbox/.runtime` under DATA_ROOT by default):
- a local self-signed TLS certificate + private key (TLS 1.2+ capable),
- a high-entropy bearer token file.

The CLI prints the cert path, its SHA-256 fingerprint and the token *path*
only; the token value itself is printed exclusively when the explicit
`--show-token` flag is passed. Nothing here ever touches the network.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

CERT_FILE_NAME = "kab-ingest-cert.pem"
KEY_FILE_NAME = "kab-ingest-key.pem"
TOKEN_FILE_NAME = "kab-ingest-token"
TOKEN_BYTES = 48

_CERT_COMMON_NAME = "kab-ingest.local"
_CERT_DAYS = 3650
_FINGERPRINT_HEX_SEPARATOR = ":"


class CertProvisioningError(RuntimeError):
    """Self-signed certificate generation is unavailable (missing `cryptography`)."""


@dataclass(frozen=True)
class ProvisionResult:
    cert_path: Path
    key_path: Path
    token_path: Path
    fingerprint_sha256: str
    token: str


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def format_fingerprint(der_digest: bytes) -> str:
    return _FINGERPRINT_HEX_SEPARATOR.join(f"{b:02x}" for b in der_digest)


def generate_self_signed(cert_path: Path, key_path: Path, common_name: str = _CERT_COMMON_NAME) -> str:
    """Writes a self-signed cert/key pair; returns the SHA-256 fingerprint."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
    except ImportError as exc:
        raise CertProvisioningError(
            "the 'cryptography' package is required to generate the local TLS certificate "
            "(install with: pip install 'transcript-pipeline[dev]' or pip install cryptography)"
        ) from exc

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=_CERT_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    fingerprint = format_fingerprint(cert.fingerprint(hashes.SHA256()))

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    _write_private(cert_path, cert.public_bytes(serialization.Encoding.PEM))
    _write_private(
        key_path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return fingerprint


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    try:
        fd = path.open("wb")
        fd.write(data)
        fd.flush()
    finally:
        if fd is not None:
            fd.close()
    _restrict_permissions(path)


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def provision(runtime_dir: Path) -> ProvisionResult:
    """Creates (or reuses) cert/key/token under `runtime_dir` (never in Git)."""
    from transcript_pipeline.kab_ingest.atomic import atomic_write_text

    cert_path = runtime_dir / CERT_FILE_NAME
    key_path = runtime_dir / KEY_FILE_NAME
    token_path = runtime_dir / TOKEN_FILE_NAME

    runtime_dir.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(runtime_dir)

    if cert_path.exists() and key_path.exists():
        fingerprint = certificate_fingerprint(cert_path)
    else:
        fingerprint = generate_self_signed(cert_path, key_path)

    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            token = generate_token()
            atomic_write_text(token_path, token)
    else:
        token = generate_token()
        atomic_write_text(token_path, token)
    _restrict_permissions(token_path)

    return ProvisionResult(
        cert_path=cert_path,
        key_path=key_path,
        token_path=token_path,
        fingerprint_sha256=fingerprint,
        token=token,
    )


def certificate_fingerprint(cert_path: Path) -> str:
    """SHA-256 fingerprint of the certificate file (TOFU verification pin)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return format_fingerprint(cert.fingerprint(hashes.SHA256()))
