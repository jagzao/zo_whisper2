"""T47: synthetic offline end-to-end run.

Generates 2 tiny videos + 2 audio clips locally with FFmpeg, uploads them
chunk-by-chunk over a temporary TLS loopback receiver, completes segments,
runs the worker, completes the session, and asserts the consolidated
outputs and COMPLETED state. Loopback-only socket guard proves the whole
flow touches nothing beyond 127.0.0.1; skipped when FFmpeg is unavailable.
"""

from __future__ import annotations

import http.client
import json
import shutil
import ssl
import subprocess
import threading

import pytest

from tests.kab_ingest_utils import (
    FakeTranscriber,
    LoopbackOnlyGuard,
    make_settings,
    make_store,
    session_payload,
    sha256_hex,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
SESSION_ID = "sess-e2e-kab"
VIDEO_SEGMENT_COUNT = 2


def _generate_media(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    videos = []
    audios = []
    for index in range(VIDEO_SEGMENT_COUNT):
        video = media_dir / f"seg{index}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"testsrc2=duration=0.6:size=160x120:rate=10",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
            ],
            check=True, capture_output=True, timeout=180,
        )
        audio = media_dir / f"seg{index}.m4a"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
                "-c:a", "aac", str(audio),
            ],
            check=True, capture_output=True, timeout=180,
        )
        videos.append(video)
        audios.append(audio)
    return videos, audios


def _split(data: bytes, parts: int) -> list[bytes]:
    size = max(1, len(data) // parts)
    chunks = [data[i : i + size] for i in range(0, len(data), size)]
    return chunks or [data]


@pytest.fixture()
def tls_receiver(tmp_path):
    from transcript_pipeline.kab_ingest.certs import provision
    from transcript_pipeline.kab_ingest.server import build_ssl_context, create_app
    from werkzeug.serving import make_server

    runtime = provision(tmp_path / "runtime")
    settings = make_settings(tmp_path, token=runtime.token)
    app = create_app(settings, store=make_store(tmp_path), data_root=tmp_path)
    context = build_ssl_context(runtime.cert_path, runtime.key_path)
    server = make_server("127.0.0.1", 0, app, threaded=True, ssl_context=context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "127.0.0.1", server.server_address[1], runtime.token
    server.shutdown()
    thread.join(timeout=10)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available")
def test_t47_synthetic_offline_e2e(tmp_path, tls_receiver, monkeypatch):
    guard = LoopbackOnlyGuard().install(monkeypatch)
    host, port, token = tls_receiver

    videos, audios = _generate_media(tmp_path)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    connection = _connect(host, port)
    status, body = _request(
        connection, "POST", "/kab/v1/sessions",
        headers,
        session_payload(session_id=SESSION_ID, title="Sesion E2E K'ab"),
    )
    assert status == 201, body

    for segment_index in range(VIDEO_SEGMENT_COUNT):
        for track, media_path, ext in (("video", videos[segment_index], ".mp4"), ("audio", audios[segment_index], ".m4a")):
            data = media_path.read_bytes()
            pieces = _split(data, 2)
            for chunk_index, piece in enumerate(pieces):
                status, body = _request(
                    connection,
                    "PUT",
                    f"/kab/v1/sessions/{SESSION_ID}/segments/{segment_index}/{track}/chunks/{chunk_index}",
                    {
                        "Authorization": f"Bearer {token}",
                        "X-Chunk-Size": str(len(piece)),
                        "X-Chunk-SHA256": sha256_hex(piece),
                    },
                    piece,
                )
                assert status == 200, body
            status, body = _request(
                connection,
                "POST",
                f"/kab/v1/sessions/{SESSION_ID}/segments/{segment_index}/{track}/complete",
                headers,
                {
                    "schemaVersion": 1,
                    "totalChunks": len(pieces),
                    "sizeBytes": len(data),
                    "sha256": sha256_hex(data),
                    "extension": ext,
                    "durationMs": 600,
                    "startOffsetMs": segment_index * 600,
                },
            )
            assert status == 200, body
            payload = json.loads(body)
            assert payload["ready"] is (track == "audio"), payload

    status, body = _request(
        connection, "POST", f"/kab/v1/sessions/{SESSION_ID}/complete",
        headers,
        {
            "schemaVersion": 1,
            "expectedSegmentCount": VIDEO_SEGMENT_COUNT,
            "endedAt": "2026-10-06T12:00:00+00:00",
            "reason": "cierre e2e",
        },
    )
    assert status == 200, body
    assert json.loads(body)["status"] == "WAITING_FOR_SEGMENTS"

    status, body = _request(connection, "GET", f"/kab/v1/sessions/{SESSION_ID}", headers)
    state = json.loads(body)
    assert state["status"] == "WAITING_FOR_SEGMENTS"
    assert str(tmp_path) not in body

    from transcript_pipeline.kab_ingest.worker import KabIngestWorker

    store = make_store(tmp_path)
    transcriber = FakeTranscriber(with_frames=True, data_root=tmp_path)
    worker = KabIngestWorker(store, tmp_path, transcribe=transcriber, poll_seconds=0.01)
    assert worker.run_once() == VIDEO_SEGMENT_COUNT

    status, body = _request(
        connection, "POST", f"/kab/v1/sessions/{SESSION_ID}/complete",
        headers,
        {
            "schemaVersion": 1,
            "expectedSegmentCount": VIDEO_SEGMENT_COUNT,
            "endedAt": "2026-10-06T12:00:00+00:00",
            "reason": "cierre e2e",
        },
    )
    assert status == 200, body
    completion_response = json.loads(body)
    assert completion_response["status"] == "COMPLETED"
    completion = completion_response["completion"]
    assert completion["availability"]["transcript"] is True
    assert completion["availability"]["manifestJson"] is True

    completed = tmp_path / "kab-inbox" / SESSION_ID / "completed"
    assert (completed / "session.complete.json").is_file()
    stored = json.loads((completed / "session.complete.json").read_text(encoding="utf-8"))
    assert stored["status"] == "COMPLETED"
    for value in stored["outputs"].values():
        assert not _looks_absolute(value)

    transcripts_dir = tmp_path / "CarpetaTranscripciones" / "kab" / SESSION_ID
    segments_doc = json.loads((transcripts_dir / "SESSION_SEGMENTS.json").read_text(encoding="utf-8"))
    assert [s["sourceSegmentIndex"] for s in segments_doc["segments"]] == [0, 0, 1, 1]
    assert [s["localStart"] for s in segments_doc["segments"]] == [0.0, 0.5, 0.6, 1.1]

    assert (completed / "manual" / "MANUAL.md").is_file()
    assert (completed / "ai-package" / "manifest.json").is_file()

    status, body = _request(
        connection, "POST", f"/kab/v1/sessions/{SESSION_ID}/complete",
        headers,
        {
            "schemaVersion": 1,
            "expectedSegmentCount": VIDEO_SEGMENT_COUNT,
            "endedAt": "2026-10-06T12:00:00+00:00",
            "reason": "cierre e2e",
        },
    )
    assert status == 200, body
    assert json.loads(body)["status"] == "COMPLETED"

    connection.close()
    assert guard.violations == []


def _connect(host: str, port: int) -> http.client.HTTPSConnection:
    from transcript_pipeline.kab_ingest.server import _ensure_stdlib_ssl_context_class

    _ensure_stdlib_ssl_context_class()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return http.client.HTTPSConnection(host, port, context=context, timeout=30)


def _request(connection: http.client.HTTPSConnection, method: str, path: str, headers: dict, payload=None) -> tuple[int, str]:
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, bytes):
        body = payload
    else:
        body = None
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    return response.status, response.read().decode("utf-8")


def _looks_absolute(value: str) -> bool:
    from pathlib import Path, PureWindowsPath

    return Path(value).is_absolute() or PureWindowsPath(value).drive != ""
