"""Shared deterministic helpers for the K'ab ingest test suite.

Everything here is offline: synthetic bytes, synthetic frames, and a
loopback-only socket guard that fails any non-loopback connection attempt
so no test can silently reach the Internet.
"""

from __future__ import annotations

import hashlib
import json
import socket
import uuid
from pathlib import Path
from typing import Any

from transcript_pipeline.kab_ingest.settings import KabIngestSettings
from transcript_pipeline.kab_ingest.store import SessionStore

TEST_TOKEN = "kab-test-token-0123456789abcdef0123456789abcdef"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"}


def make_settings(tmp_path: Path, **overrides: Any) -> KabIngestSettings:
    defaults: dict[str, Any] = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 5443,
        "token": TEST_TOKEN,
        "max_chunk_mb": 8,
        "max_session_gb": 50,
        "root": tmp_path / "kab-inbox",
    }
    defaults.update(overrides)
    cert = defaults.pop("cert_file", tmp_path / "runtime" / "cert.pem")
    key = defaults.pop("key_file", tmp_path / "runtime" / "key.pem")
    return KabIngestSettings(cert_file=cert, key_file=key, **defaults)


def make_store(tmp_path: Path, *, max_chunk_bytes: int = 8 * 1024 * 1024, max_session_bytes: int = 50 * 1024**3) -> SessionStore:
    return SessionStore(
        tmp_path / "kab-inbox",
        max_chunk_bytes=max_chunk_bytes,
        max_session_bytes=max_session_bytes,
    )


def session_payload(session_id: str = "sess-0001", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "sessionId": session_id,
        "title": "Sesion de prueba K'ab",
        "createdAt": "2026-10-06T10:00:00+00:00",
        "segmentDurationSec": 300,
        "requiredTracks": ["video", "audio"],
    }
    payload.update(overrides)
    return payload


def chunk_bytes(seed: str, size: int = 1024) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out.extend(hashlib.sha256(f"{seed}:{counter}".encode()).digest())
        counter += 1
    return bytes(out[:size])


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def auth_headers(token: str = TEST_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeTranscriber:
    """Deterministic offline stand-in for the local Whisper processor."""

    def __init__(self, *, with_frames: bool = False, error: Exception | None = None, data_root: Path | None = None):
        self.calls: list[Path] = []
        self.with_frames = with_frames
        self.error = error
        self.data_root = data_root

    def __call__(self, media_path: Path) -> dict[str, Any]:
        self.calls.append(media_path)
        if self.error is not None:
            raise self.error
        name = media_path.name
        result: dict[str, Any] = {
            "text": f"transcripcion determinista de {name}",
            "language": "es",
            "duration": 1.0,
            "segments": [
                {"start": 0.0, "end": 0.5, "text": f"inicio de {name}"},
                {"start": 0.5, "end": 1.0, "text": f"fin de {name}"},
            ],
        }
        if self.with_frames:
            segment_index = _segment_index_from_name(name)
            frames_dir = _make_frames(self.data_root or Path("Frames"), segment_index, name)
            result["frame_info"] = {
                "frames_dir": str(frames_dir),
                "frame_count": 1,
                "video_duration": 1.0,
                "method": "test",
            }
        return result


def _segment_index_from_name(name: str) -> int:
    stem = name.split(".")[0]
    if stem.startswith("segment-"):
        return int(stem.split("-")[1])
    return 0


def _make_frames(base: Path, segment_index: int, media_name: str) -> Path:
    from PIL import Image

    from transcript_pipeline.documentation.engine import generate_documentation

    frames_dir = base / f"seg{segment_index:06d}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_name = "frame_000000.png"
    Image.new("RGB", (32, 24), color=(segment_index * 40 % 255, 10, 10)).save(frames_dir / frame_name)
    mapping = {
        "video_info": {
            "name": media_name,
            "duration": 1.0,
            "duration_formatted": "00:00:01",
            "extraction_method": "test",
            "extraction_date": "2026-10-06",
            "total_frames": 1,
        },
        "frames": [
            {"frame_file": frame_name, "timestamp": 0.0, "timestamp_formatted": "00:00:00"}
        ],
        "transcription_mapping": {
            frame_name: {
                "timestamp": 0.0,
                "timestamp_formatted": "00:00:00",
                "transcription_segments": [],
                "full_text": f"paso determinista {segment_index}",
            }
        },
    }
    (frames_dir / "frame_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    generate_documentation(
        frames_dir,
        f"segment {segment_index:06d}",
        manual_dir=frames_dir / "manual",
        ai_package_dir=frames_dir / "ai-package",
        project_config=None,
    )
    return frames_dir


def unique_session_id() -> str:
    return "sess-" + uuid.uuid4().hex[:12]


class LoopbackOnlyGuard:
    """Fails (records) any socket usage targeting a non-loopback destination.

    Patched surfaces: socket.socket.connect, socket.create_connection and
    socket.getaddrinfo (so even a DNS lookup for an outside name fails).
    """

    def __init__(self) -> None:
        self.violations: list[str] = []

    def install(self, monkeypatch: Any) -> "LoopbackOnlyGuard":
        import ipaddress

        guard = self
        real_connect = socket.socket.connect
        real_create_connection = socket.create_connection
        real_getaddrinfo = socket.getaddrinfo

        def is_allowed(host: object) -> bool:
            text = str(host).lower().strip("[]")
            if text in LOOPBACK_HOSTS:
                return True
            try:
                return ipaddress.ip_address(text).is_loopback
            except ValueError:
                return False

        def guarded_connect(sock: socket.socket, address: Any):
            host = address[0] if isinstance(address, tuple) else address
            if not is_allowed(host):
                guard.violations.append(f"connect:{address!r}")
                raise AssertionError(f"non-loopback connection attempted: {address!r}")
            return real_connect(sock, address)

        def guarded_create_connection(address: Any, *args: Any, **kwargs: Any):
            host = address[0] if isinstance(address, tuple) else address
            if not is_allowed(host):
                guard.violations.append(f"create_connection:{address!r}")
                raise AssertionError(f"non-loopback connection attempted: {address!r}")
            return real_create_connection(address, *args, **kwargs)

        def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any):
            if not is_allowed(host):
                guard.violations.append(f"dns:{host!r}")
                raise AssertionError(f"DNS resolution attempted for non-loopback host: {host!r}")
            return real_getaddrinfo(host, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", guarded_connect)
        monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
        monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
        return self
