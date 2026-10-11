"""K'ab ingest receiver — the HTTP API (separate process, disabled by default).

Endpoints (all under /kab/v1, all bearer-authenticated with constant-time
comparison, all returning uniform JSON errors; media bodies are streamed
straight to temp files and never buffered whole in memory):

    POST /kab/v1/sessions
    GET  /kab/v1/sessions/{sessionId}
    PUT  /kab/v1/sessions/{sessionId}/segments/{segmentIndex}/{track}/chunks/{chunkIndex}
    POST /kab/v1/sessions/{sessionId}/segments/{segmentIndex}/{track}/complete
    POST /kab/v1/sessions/{sessionId}/complete

Startup refuses to run unless: KAB_INGEST_ENABLED is true, a bind host
passing the RFC1918/ULA/loopback policy is configured, a bearer token is
configured, and TLS cert+key are configured (TLS 1.2 minimum, enforced by
the SSLContext). API responses contain no filesystem paths — session state
is expressed only through indexes, hashes, sizes and state names.
"""

from __future__ import annotations

import logging
import ssl
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

from transcript_pipeline.kab_ingest import validation
from transcript_pipeline.kab_ingest.auth import constant_time_token_match, extract_bearer_token
from transcript_pipeline.kab_ingest.bind import validate_bind_host
from transcript_pipeline.kab_ingest.errors import (
    KabIngestError,
    KabIngestValidationError,
)
from transcript_pipeline.kab_ingest.settings import KabIngestSettings
from transcript_pipeline.kab_ingest.store import (
    COMPLETED_DIR,
    DEFAULT_READ_DEADLINE_SECONDS,
    SessionStore,
)

logger = logging.getLogger(__name__)

_COMPLETION_SUMMARY_KEYS = (
    "expectedSegmentCount",
    "endedAt",
    "reason",
)


def create_app(
    settings: KabIngestSettings | None = None,
    *,
    store: SessionStore | None = None,
    data_root: Path | None = None,
) -> Flask:
    """Builds the receiver app; `store`/`data_root` are injectable for tests."""
    settings = settings or KabIngestSettings.from_env()
    settings.validate_for_server()
    store = store or SessionStore(
        settings.storage_root(),
        max_chunk_bytes=settings.max_chunk_bytes,
        max_session_bytes=settings.max_session_bytes,
    )
    data_root = (data_root or _data_root()).resolve(strict=False)

    app = Flask("kab_ingest")
    app.config["MAX_CONTENT_LENGTH"] = settings.max_chunk_bytes + 1024 * 1024
    app.config["KAB_INGEST_SETTINGS"] = settings

    @app.before_request
    def _require_bearer() -> Response | None:
        if not request.path.startswith("/kab/v1/"):
            return None
        presented = extract_bearer_token(request.headers.get("Authorization"))
        if not constant_time_token_match(presented, settings.token):
            return jsonify({"error": {"code": "unauthorized", "message": "authentication required"}}), 401
        return None

    @app.errorhandler(KabIngestError)
    def _domain_error(exc: KabIngestError) -> tuple[Response, int]:
        return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status

    @app.errorhandler(404)
    def _not_found(_exc: Exception) -> tuple[Response, int]:
        return jsonify({"error": {"code": "not_found", "message": "resource not found"}}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_exc: Exception) -> tuple[Response, int]:
        return jsonify({"error": {"code": "method_not_allowed", "message": "method not allowed"}}), 405

    @app.errorhandler(413)
    def _too_large(_exc: Exception) -> tuple[Response, int]:
        return jsonify({"error": {"code": "payload_too_large", "message": "request body too large"}}), 413

    @app.errorhandler(400)
    def _bad_request(_exc: Exception) -> tuple[Response, int]:
        return jsonify({"error": {"code": "invalid_request", "message": "malformed request"}}), 400

    @app.errorhandler(Exception)
    def _internal(exc: Exception) -> tuple[Response, int]:
        logger.error("[KAB] unhandled error: %s", type(exc).__name__)
        return jsonify({"error": {"code": "internal_error", "message": "internal error"}}), 500

    # ── POST /kab/v1/sessions ────────────────────────────────────────

    @app.post("/kab/v1/sessions")
    def create_session() -> tuple[Response, int]:
        payload = _json_body()
        if payload.get("schemaVersion") != validation.SCHEMA_VERSION:
            raise KabIngestValidationError("schemaVersion must be 1", code="invalid_schema_version")
        record = {
            "schemaVersion": validation.SCHEMA_VERSION,
            "sessionId": validation.validate_session_id(str(payload.get("sessionId", ""))),
            "title": validation.sanitize_title(payload.get("title")),
            "createdAt": validation.parse_iso8601(payload.get("createdAt"), what="createdAt"),
            "segmentDurationSec": validation.validate_positive_number(
                payload.get("segmentDurationSec"), what="segmentDurationSec"
            ),
            "requiredTracks": validation.validate_required_tracks(payload.get("requiredTracks")),
            # Optional explicit project identity (SPEC §13): absent for legacy
            # senders, never guessed from filename/title.
            "projectKey": validation.validate_project_key(payload.get("projectKey")),
        }
        session, created = store.create_session(record)
        return jsonify({"created": created, "session": _safe_session_summary(session)}), (201 if created else 200)

    # ── GET /kab/v1/projects — safe project catalog (SPEC §13) ────────

    @app.get("/kab/v1/projects")
    def list_projects() -> Response:
        """Safe authenticated fields only: key, display name, scope default,
        artifact default. No prompts, filesystem paths, secrets or internal
        configuration are exposed."""
        catalog = knowledge_project_catalog()
        return jsonify({"projects": catalog})

    # ── GET /kab/v1/sessions/{id} ────────────────────────────────────

    @app.get("/kab/v1/sessions/<session_id>")
    def get_session(session_id: str) -> Response:
        return jsonify(store.session_state(session_id))

    # ── PUT chunks ───────────────────────────────────────────────────

    @app.put("/kab/v1/sessions/<session_id>/segments/<int:segment_index>/<track>/chunks/<int:chunk_index>")
    def put_chunk(session_id: str, segment_index: int, track: str, chunk_index: int) -> Response:
        validation.validate_track(track)
        content_length = request.content_length
        if content_length is None:
            raise KabIngestValidationError("Content-Length header is required", code="missing_content_length")
        declared_size = _declared_chunk_size(request.headers.get("X-Chunk-Size"))
        if declared_size != content_length:
            raise KabIngestValidationError(
                "X-Chunk-Size does not match Content-Length", code="chunk_size_mismatch"
            )
        declared_sha = request.headers.get("X-Chunk-SHA256", "")
        budget = DEFAULT_READ_DEADLINE_SECONDS - (time.monotonic() - request.environ.get("KAB_REQUEST_START", time.monotonic()))
        result = store.put_chunk(
            session_id,
            segment_index,
            track,
            chunk_index,
            read=request.stream.read,
            expected_sha256=declared_sha,
            expected_size=content_length,
            deadline=max(budget, 1.0),
        )
        return jsonify(result)

    # ── POST segment complete ────────────────────────────────────────

    @app.post("/kab/v1/sessions/<session_id>/segments/<int:segment_index>/<track>/complete")
    def complete_segment(session_id: str, segment_index: int, track: str) -> Response:
        validation.validate_track(track)
        payload = _json_body()
        if payload.get("schemaVersion") != validation.SCHEMA_VERSION:
            raise KabIngestValidationError("schemaVersion must be 1", code="invalid_schema_version")
        result = store.complete_segment(
            session_id,
            segment_index,
            track,
            total_chunks=validation.validate_nonnegative_int_field(payload.get("totalChunks"), what="totalChunks"),
            size_bytes=validation.validate_nonnegative_int_field(payload.get("sizeBytes"), what="sizeBytes"),
            sha256=validation.validate_sha256(str(payload.get("sha256", ""))),
            extension=str(payload.get("extension", "")),
            duration_ms=validation.validate_nonnegative_int_field(payload.get("durationMs"), what="durationMs"),
            start_offset_ms=validation.validate_nonnegative_int_field(
                payload.get("startOffsetMs"), what="startOffsetMs"
            ),
        )
        if result["sizeBytes"] is not None and result["sizeBytes"] < 1:
            raise KabIngestValidationError("sizeBytes must be positive", code="invalid_segment_size")
        return jsonify(result)

    # ── POST session complete ────────────────────────────────────────

    @app.post("/kab/v1/sessions/<session_id>/complete")
    def complete_session(session_id: str) -> Response:
        payload = _json_body()
        if payload.get("schemaVersion") != validation.SCHEMA_VERSION:
            raise KabIngestValidationError("schemaVersion must be 1", code="invalid_schema_version")
        expected = validation.validate_nonnegative_int_field(
            payload.get("expectedSegmentCount"), what="expectedSegmentCount"
        )
        if expected < 1:
            raise KabIngestValidationError("expectedSegmentCount must be >= 1", code="invalid_expected_count")
        ended_at = validation.parse_iso8601(payload.get("endedAt"), what="endedAt")
        reason = validation.sanitize_reason(payload.get("reason"))

        session = store.load_session(session_id)
        requested_completion = {
            "expectedSegmentCount": expected,
            "endedAt": ended_at,
            "reason": reason,
        }
        stored_status = session.get("status")
        if stored_status in ("COMPLETED", "WAITING_FOR_SEGMENTS"):
            stored_completion = {
                "expectedSegmentCount": session.get("expectedSegmentCount"),
                "endedAt": session.get("endedAt"),
                "reason": session.get("reason"),
            }
            if stored_completion != requested_completion:
                from transcript_pipeline.kab_ingest.errors import KabIngestConflict

                raise KabIngestConflict(
                    "session completion already requested with different parameters",
                    code="completion_conflict",
                )
            if stored_status == "COMPLETED":
                completion = _read_completion(store, session_id)
                if completion is not None:
                    return jsonify({"status": "COMPLETED", "completion": completion})

        processed = store.processed_segment_indexes(session_id)
        missing = [i for i in range(expected) if i not in processed]
        if missing:
            store.finalize_session(
                session_id,
                expected_segment_count=expected,
                ended_at=ended_at,
                reason=reason,
                status="WAITING_FOR_SEGMENTS",
            )
            return jsonify(
                {
                    "status": "WAITING_FOR_SEGMENTS",
                    "expectedSegmentCount": expected,
                    "processedSegmentCount": len(processed),
                    "missingSegmentCount": len(missing),
                }
            )

        from transcript_pipeline.kab_ingest.consolidate import consolidate_session

        completion = consolidate_session(
            store,
            data_root,
            session_id,
            ended_at=ended_at,
            reason=reason,
        )
        store.finalize_session(
            session_id,
            expected_segment_count=expected,
            ended_at=ended_at,
            reason=reason,
            status="COMPLETED",
        )
        return jsonify({"status": "COMPLETED", "completion": completion})

    def _json_body() -> dict:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise KabIngestValidationError("request body must be a JSON object", code="invalid_json")
        return payload

    def _declared_chunk_size(raw: str | None) -> int:
        if raw is None or not raw.strip() or not raw.strip().isdigit():
            raise KabIngestValidationError("X-Chunk-Size header is required", code="invalid_chunk_size")
        return int(raw.strip())

    return app


def _read_completion(store: SessionStore, session_id: str) -> dict | None:
    from transcript_pipeline.kab_ingest.atomic import read_json

    path = store.paths(session_id).base / COMPLETED_DIR / "session.complete.json"
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def _safe_session_summary(session: dict) -> dict:
    return {
        "schemaVersion": session.get("schemaVersion"),
        "sessionId": session.get("sessionId"),
        "title": session.get("title"),
        "createdAt": session.get("createdAt"),
        "segmentDurationSec": session.get("segmentDurationSec"),
        "requiredTracks": session.get("requiredTracks"),
        "projectKey": session.get("projectKey"),
        "status": session.get("status"),
    }


def _load_knowledge_projects() -> list[dict]:
    """Loads projects.json entries that have second_brain enabled."""
    from transcript_pipeline.config import PROJECTS_CONFIG_PATH
    from transcript_pipeline.projects import load_projects

    projects = load_projects(PROJECTS_CONFIG_PATH)
    return [
        p
        for p in projects
        if isinstance(p.get("second_brain"), dict) and p["second_brain"].get("enabled")
    ]


def knowledge_project_catalog() -> list[dict]:
    """Safe project catalog for the K'ab sender (SPEC §13).

    Only safe authenticated fields: key, display name, scope default,
    artifact type default. No prompts, paths, secrets or internal config.
    """
    catalog: list[dict] = []
    for project in _load_knowledge_projects():
        sb = project.get("second_brain") if isinstance(project, dict) else None
        if not isinstance(sb, dict):
            continue
        catalog.append(
            {
                "key": project.get("name"),
                "displayName": project.get("name"),
                "scopeDefault": sb.get("scope", "PROJECT"),
                "artifactTypeDefault": sb.get("default_artifact_type", "KT"),
            }
        )
    return catalog


def resolve_project_config_by_key(project_key: str | None) -> dict | None:
    """Deterministic project lookup by explicit key (never filename guessing).

    Returns None when the key is absent or matches no configured project —
    callers treat that as "publishing disabled for this session" (ZK-20).
    """
    if not project_key:
        return None
    for project in _load_knowledge_projects():
        if project.get("name") == project_key:
            return project
    return None


def _data_root() -> Path:
    from transcript_pipeline.config import DATA_ROOT

    return DATA_ROOT


def _ensure_stdlib_ssl_context_class() -> Any:
    """Restores the real `ssl.SSLContext` if a client-only wrapper replaced it.

    Some environments globally inject pip's vendored truststore into `ssl`;
    its context works for clients only and breaks server-side TLS (and the
    stdlib minimum_version property recursion). Since the receiver runs as
    its own process, restoring the original class reference here is safe and
    keeps `SSLContext(...)` usable for both server and test clients.
    """
    cls: Any = ssl.SSLContext
    if "truststore" in getattr(cls, "__module__", "").lower():
        for base in getattr(cls, "__mro__", ()):
            if getattr(base, "__module__", "") == "ssl":
                ssl.SSLContext = base
                return base
    return cls


def _new_server_ssl_context() -> Any:
    """Builds a pristine TLS server context (TLS version set by caller)."""
    context_cls = _ensure_stdlib_ssl_context_class()
    return context_cls(ssl.PROTOCOL_TLS_SERVER)


def build_ssl_context(cert_file: Path, key_file: Path) -> Any:
    """TLS 1.2+ server context; startup fails closed without credentials."""
    if not cert_file.is_file() or not key_file.is_file():
        from transcript_pipeline.errors import ConfigurationError

        raise ConfigurationError(
            "TLS certificate/key files are missing — the receiver never starts without TLS."
        )
    context = _new_server_ssl_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_file), str(key_file))
    return context


def run_server(settings: KabIngestSettings | None = None) -> int:
    """Validates the full posture and serves over TLS; never runs implicitly."""
    settings = settings or KabIngestSettings.from_env()
    settings.validate_for_server()
    assert settings.cert_file is not None and settings.key_file is not None
    if not settings.cert_file.is_file() or not settings.key_file.is_file():
        from transcript_pipeline.errors import ConfigurationError

        raise ConfigurationError(
            "KAB_INGEST_CERT/KAB_INGEST_KEY files do not exist — run transcript-kab-ingest-cert first."
        )
    validate_bind_host(settings.host or "")
    app = create_app(settings)
    context = build_ssl_context(settings.cert_file, settings.key_file)
    from werkzeug.serving import make_server

    server = make_server(settings.host, settings.port, app, threaded=True, ssl_context=context)
    logger.info(
        "[KAB] receiver listening on https://%s:%s (TLS 1.2+)", settings.host, settings.port
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[KAB] receiver stopped")
    return 0
