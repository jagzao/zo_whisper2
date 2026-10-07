"""T08-T12: constant-time bearer auth, uniform 401, TLS-only startup, no token leaks."""

from __future__ import annotations

import logging

import pytest

from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.kab_ingest.auth import constant_time_token_match, extract_bearer_token
from transcript_pipeline.kab_ingest.certs import generate_self_signed
from transcript_pipeline.kab_ingest.server import build_ssl_context, create_app
from tests.kab_ingest_utils import (
    TEST_TOKEN,
    auth_headers,
    chunk_bytes,
    make_settings,
    make_store,
    session_payload,
    sha256_hex,
)

ENDPOINTS = [
    ("POST", "/kab/v1/sessions"),
    ("GET", "/kab/v1/sessions/sess-0001"),
    ("PUT", "/kab/v1/sessions/sess-0001/segments/0/video/chunks/0"),
    ("POST", "/kab/v1/sessions/sess-0001/segments/0/video/complete"),
    ("POST", "/kab/v1/sessions/sess-0001/complete"),
]


@pytest.fixture()
def client(tmp_path):
    app = create_app(make_settings(tmp_path), store=make_store(tmp_path), data_root=tmp_path)
    app.testing = True
    return app.test_client()


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_t08_every_media_endpoint_requires_bearer(client, method, path):
    for headers in (
        {},
        {"Authorization": ""},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer"},
        {"Authorization": f"Bearer {TEST_TOKEN}-wrong"},
    ):
        response = client.open(path, method=method, headers=headers, json={})
        assert response.status_code == 401, headers
        assert response.get_json() == {"error": {"code": "unauthorized", "message": "authentication required"}}


def test_t09_valid_token_is_accepted(client):
    response = client.post("/kab/v1/sessions", headers=auth_headers(), json=session_payload())
    assert response.status_code == 201
    assert response.get_json()["created"] is True


def test_t10_token_never_appears_in_logs_or_responses(client, tmp_path, caplog):
    with caplog.at_level(logging.DEBUG):
        missing = client.get("/kab/v1/sessions/sess-0001", headers=auth_headers())
        wrong = client.post("/kab/v1/sessions", headers={"Authorization": f"Bearer {TEST_TOKEN}"}, json={})
        upload = client.put(
            "/kab/v1/sessions/sess-0001/segments/0/video/chunks/0",
            headers={**auth_headers(), "X-Chunk-Size": "4", "X-Chunk-SHA256": sha256_hex(b"abcd")},
            data=b"abcd",
        )
    assert missing.status_code == 404
    assert wrong.status_code == 400
    assert upload.status_code in (200, 400, 404)
    for record in caplog.records:
        assert TEST_TOKEN not in str(record.getMessage())
        assert TEST_TOKEN not in str(record.__dict__)


def test_t11_token_comparison_is_constant_time_digest_based():
    assert constant_time_token_match(TEST_TOKEN, TEST_TOKEN) is True
    assert constant_time_token_match(TEST_TOKEN, TEST_TOKEN + "x") is False
    assert constant_time_token_match("", TEST_TOKEN) is False
    assert constant_time_token_match(None, TEST_TOKEN) is False
    assert constant_time_token_match(TEST_TOKEN, None) is False
    assert extract_bearer_token(f"Bearer {TEST_TOKEN}") == TEST_TOKEN
    assert extract_bearer_token("Bearer  ") is None
    assert extract_bearer_token(None) is None


def test_t12_tls_is_mandatory(tmp_path):
    from pathlib import Path

    with pytest.raises(ConfigurationError):
        build_ssl_context(tmp_path / "missing-cert.pem", tmp_path / "missing-key.pem")

    runtime = tmp_path / "runtime"
    generate_self_signed(runtime / "cert.pem", runtime / "key.pem")
    context = build_ssl_context(runtime / "cert.pem", runtime / "key.pem")
    assert context.minimum_version == __import__("ssl").TLSVersion.TLSv1_2

    settings = make_settings(tmp_path, cert_file=Path("does-not-exist.pem"))
    from transcript_pipeline.kab_ingest.server import run_server

    with pytest.raises(ConfigurationError):
        run_server(settings)

    app = create_app(make_settings(tmp_path), store=make_store(tmp_path), data_root=tmp_path)
    assert app.config["MAX_CONTENT_LENGTH"] > 0
