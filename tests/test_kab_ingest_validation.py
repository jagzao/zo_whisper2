"""T13-T16: session ID / path / track / extension / schema safety."""

from __future__ import annotations

import pytest

from transcript_pipeline.kab_ingest.errors import KabIngestValidationError
from transcript_pipeline.kab_ingest.validation import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    sanitize_title,
    validate_extension,
    validate_required_tracks,
    validate_session_id,
)
from tests.kab_ingest_utils import (
    auth_headers,
    chunk_bytes,
    make_settings,
    make_store,
    session_payload,
    sha256_hex,
)

APP_SETTINGS = None


@pytest.fixture()
def client(tmp_path):
    from transcript_pipeline.kab_ingest.server import create_app

    app = create_app(make_settings(tmp_path), store=make_store(tmp_path), data_root=tmp_path)
    app.testing = True
    return app.test_client()


@pytest.mark.parametrize("sid", ["a", "A", "0", "sess-0001", "S" * 64, "abc_DEF-123"])
def test_t13_session_id_policy_accepts_strict_ids(sid):
    assert validate_session_id(sid) == sid


@pytest.mark.parametrize(
    "sid",
    [
        "",
        "-leading",
        "_leading",
        "with space",
        "with/slash",
        "with\\backslash",
        "..",
        "../escape",
        "a" * 65,
        "uniñ",
        "dot.name",
    ],
)
def test_t13_session_id_policy_rejects_everything_else(sid):
    with pytest.raises(KabIngestValidationError):
        validate_session_id(sid)


def test_t14_track_and_required_tracks_are_strict():
    with pytest.raises(KabIngestValidationError):
        validate_required_tracks([])
    with pytest.raises(KabIngestValidationError):
        validate_required_tracks(["mic"])
    with pytest.raises(KabIngestValidationError):
        validate_required_tracks(["video", "video"])
    assert validate_required_tracks(["video"]) == ["video"]
    assert validate_required_tracks(["audio", "video"]) == ["video", "audio"]


def test_t14_invalid_track_rejected_by_api(client, tmp_path):
    client.post("/kab/v1/sessions", headers=auth_headers(), json=session_payload())
    bad_track = client.put(
        "/kab/v1/sessions/sess-0001/segments/0/mic/chunks/0",
        headers={**auth_headers(), "X-Chunk-Size": "4", "X-Chunk-SHA256": sha256_hex(b"abcd")},
        data=b"abcd",
    )
    assert bad_track.status_code == 400
    bad_complete = client.post(
        "/kab/v1/sessions/sess-0001/segments/0/subtitles/complete",
        headers=auth_headers(),
        json={"schemaVersion": 1},
    )
    assert bad_complete.status_code == 400


@pytest.mark.parametrize(
    ("track", "ext", "allowed"),
    [
        ("video", ".mp4", True),
        ("video", ".mkv", True),
        ("video", ".mov", True),
        ("video", ".webm", True),
        ("video", ".wav", False),
        ("video", ".exe", False),
        ("video", ".mp3", False),
        ("audio", ".wav", True),
        ("audio", ".m4a", True),
        ("audio", ".mp3", True),
        ("audio", ".flac", True),
        ("audio", ".ogg", True),
        ("audio", ".opus", True),
        ("audio", ".mp4", False),
        ("audio", ".exe", False),
    ],
)
def test_t15_extension_allowlists_per_track(track, ext, allowed):
    if allowed:
        assert validate_extension(track, ext) == ext
    else:
        with pytest.raises(KabIngestValidationError):
            validate_extension(track, ext)


def test_t15_extension_with_path_separator_rejected():
    for ext in ("a/b", "..%2f", ".mp4/x", ".\x00mp4"):
        with pytest.raises(KabIngestValidationError):
            validate_extension("video", ext)
    assert VIDEO_EXTENSIONS and AUDIO_EXTENSIONS


def test_t16_schema_and_body_safety(client):
    headers = auth_headers()

    bad_schema = client.post("/kab/v1/sessions", headers=headers, json={**session_payload(), "schemaVersion": 2})
    assert bad_schema.status_code == 400

    no_json = client.post("/kab/v1/sessions", headers=headers, data="not json", content_type="application/json")
    assert no_json.status_code == 400

    bad_created = client.post(
        "/kab/v1/sessions", headers=headers, json={**session_payload(), "createdAt": "not-a-date"}
    )
    assert bad_created.status_code == 400

    bad_duration = client.post(
        "/kab/v1/sessions", headers=headers, json={**session_payload(), "segmentDurationSec": 0}
    )
    assert bad_duration.status_code == 400

    missing = client.get("/kab/v1/sessions/unknown-session", headers=headers)
    assert missing.status_code == 404

    negative_index = client.put(
        "/kab/v1/sessions/sess-0001/segments/-1/video/chunks/0",
        headers={**headers, "X-Chunk-Size": "4", "X-Chunk-SHA256": sha256_hex(b"abcd")},
        data=b"abcd",
    )
    assert negative_index.status_code == 404

    traversal = client.get("/kab/v1/sessions/..%2fescape", headers=headers)
    assert traversal.status_code in (400, 404)


def test_t16_title_sanitization():
    assert sanitize_title("  hola   mundo\n ") == "hola mundo"
    assert sanitize_title("tab\ttitle") == "tab title"
    for bad in ("", "   ", None, 42, "x" * 201):
        with pytest.raises(KabIngestValidationError):
            sanitize_title(bad)


def test_store_rejects_oversize_index(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    with pytest.raises(KabIngestValidationError):
        store.put_chunk(
            "sess-0001",
            10**10,
            "video",
            0,
            read=iter([b"x"]).__next__,
            expected_sha256=sha256_hex(b"x"),
            expected_size=1,
        )
    assert chunk_bytes("unused")
