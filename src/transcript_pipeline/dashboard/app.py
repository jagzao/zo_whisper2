#!/usr/bin/env python3
"""
Dashboard UI to control the transcription pipeline.

Features:
- Displays input/output folders.
- Shows the audio/video file -> transcription relationship.
- Drop area to upload files to Video_compress/ with a project prefix.
- Project CRUD (projects.json).
- RUN button to execute the compressor and master pipeline modules
  (`python -m transcript_pipeline.media.compressor` and
  `python -m transcript_pipeline.pipeline.master`).
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from flask import Flask, jsonify, make_response, redirect, render_template, request, send_file, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from transcript_pipeline import lan_access
from transcript_pipeline.config import (
    AUDIO_DIR,
    DATA_ROOT,
    LOG_DIR,
    PROCESSED_FILES_DB,
    PROJECTS_CONFIG_PATH,
    TRANSCRIPTIONS_DIR,
    VIDEO_COMPRESS_DIR,
    VIDEOS_DIR,
    load_env,
)
from transcript_pipeline.documentation.engine import (
    generate_documentation,
    load_steps,
    regenerate_from_steps,
    remove_step,
    update_step,
)
from transcript_pipeline.live_capture import CaptureService
from transcript_pipeline.live_capture import errors as capture_errors
from transcript_pipeline.live_capture import models as capture_models
from transcript_pipeline.live_capture.black_video import (
    apply_video_edits,
    crop_black_borders,
    detect_black_borders,
    detect_black_intervals,
    trim_black_intervals,
    validate_video_edit_spec,
)
from transcript_pipeline.live_capture.playlist import PlaylistService, ocr_title_image
from transcript_pipeline.logging_setup import configure_logging
from transcript_pipeline.media.utils import run_ffprobe
from transcript_pipeline.processing_worker import ProcessingJobStore, ProcessingWorker
from transcript_pipeline.projects import validate_project
from transcript_pipeline.security import (
    MediaRoot,
    PathNotFoundError,
    PathTraversalError,
    SafePathResolver,
    SecurityError,
)
from transcript_pipeline.settings import SETTINGS

load_env()

# Runtime paths follow DATA_ROOT (ZMI_DATA_ROOT); module attribute names
# are load-bearing — tests monkeypatch them.
ROOT = DATA_ROOT
VIDEO_COMPRESS = VIDEO_COMPRESS_DIR
AUDIO_BASE = AUDIO_DIR
VIDEOS_BASE = VIDEOS_DIR
TRANSCRIPTIONS_BASE = TRANSCRIPTIONS_DIR
PROJECTS_PATH = PROJECTS_CONFIG_PATH
PROCESSED_DB = PROCESSED_FILES_DB

RESOLVER = SafePathResolver(
    {
        MediaRoot.AUDIO: AUDIO_BASE,
        MediaRoot.VIDEOS: VIDEOS_BASE,
        MediaRoot.VIDEO_COMPRESS: VIDEO_COMPRESS,
        MediaRoot.TRANSCRIPTIONS: TRANSCRIPTIONS_BASE,
    }
)

SUPPORTED_MEDIA = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
_MEDIA_DURATION_CACHE: dict[tuple[str, int, int], float | None] = {}
_MEDIA_DURATION_FUTURES: dict[tuple[str, int, int], Future[float | None]] = {}
_MEDIA_DURATION_CACHE_LOCK = threading.Lock()
_MEDIA_DURATION_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="whisper-media-probe")
_VIDEO_EDIT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper-video-edit")
_VIDEO_EDIT_JOBS: dict[str, dict[str, Any]] = {}
_VIDEO_EDIT_KEYS: dict[str, str] = {}
_VIDEO_EDIT_SOURCE_JOBS: dict[str, str] = {}
_VIDEO_EDIT_JOBS_LOCK = threading.Lock()

RUN_ID = configure_logging("dashboard.log")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")
if os.getenv("ZMI_TRUST_PROXY", "").strip().lower() == "true":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)


def _lan_http_port() -> int:
    return int(os.getenv("ZMI_LAN_HTTP_PORT", "5003"))


def _lan_https_port() -> int:
    return int(os.getenv("ZMI_HTTPS_PORT", "5001"))


def _lan_https_available() -> bool:
    if os.getenv("ZMI_TRUST_PROXY", "").strip().lower() == "true":
        return True
    certificate = SETTINGS.dashboard_cert_file
    return bool(certificate and certificate.is_file())
app.config["MAX_CONTENT_LENGTH"] = SETTINGS.upload_max_mb * 1024 * 1024

# This dashboard is explicitly localhost-only (SETTINGS.dashboard_host is
# enforced loopback-only at Settings.from_env() time; with
# ZMI_CONTAINER_MODE=true the bind may additionally be 0.0.0.0 — that is
# container-internal only, since Compose publishes the port on the host's
# loopback and never on the network) — no remote mode, no user accounts.
# The Host/Origin/token protections below are unchanged in container mode
# and still enforced. The token below is the only thing standing between
# "any process that can reach this port" and "the browser tab the owner
# opened".
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# W25: extra Host/Origin values accepted only when ZMI_LAN_ACCESS is enabled.
# Populated once at import from the configured host list plus the machine's
# detected private LAN IPv4 addresses; tests and operators can override it.
# Empty (loopback-only) unless LAN mode is explicitly opted in.
_LAN_HOST_ALLOWLIST: set[str] = set()
if SETTINGS.lan_access:
    _LAN_HOST_ALLOWLIST.update(h.lower() for h in SETTINGS.lan_hosts)
    _LAN_HOST_ALLOWLIST.update(lan_access.advertised_lan_ipv4_addresses(SETTINGS.lan_hosts))
# Shared across application workers and restarts, never logged — the frontend
# reads it from the page it was served and echoes it on mutations. Host,
# Origin and private-client checks remain independent authorization guards.
def _load_dashboard_token(data_root: Path = DATA_ROOT) -> str:
    """Share the anti-CSRF token across workers and dashboard restarts."""
    configured = os.environ.get("WHISPER_DASHBOARD_TOKEN", "").strip()
    if configured:
        return configured
    token_path = data_root / ".whisper" / "dashboard-token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with token_path.open("x", encoding="ascii") as token_file:
            token = secrets.token_urlsafe(32)
            token_file.write(token)
            token_file.flush()
            os.fsync(token_file.fileno())
            return token
    except FileExistsError:
        for _ in range(20):
            token = token_path.read_text(encoding="ascii").strip()
            if token:
                return token
            time.sleep(0.01)
        raise RuntimeError("Dashboard token file is empty")


_DASHBOARD_TOKEN = _load_dashboard_token()
BUILD_REVISION = os.environ.get("WHISPER_BUILD_REVISION", "").strip()
if not BUILD_REVISION:
    try:
        BUILD_REVISION = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        BUILD_REVISION = "unknown"

# media_ids currently being documented (in-memory concurrency guard so a
# second "Generate Documentation" for the same video is rejected, not queued).
_doc_generation_lock = threading.Lock()
_doc_generation_inflight: set[str] = set()
_reprocess_inflight: set[str] = set()

# CaptureService is bound to the *current* VIDEOS_BASE (monkeypatchable in
# tests) — recreated only when the resolved root changes, so per-session locks
# stay shared for the lifetime of a given data root.
_capture_service: CaptureService | None = None
_capture_service_root: Path | None = None
_capture_service_lock = threading.Lock()
_processing_worker: ProcessingWorker | None = None
_processing_worker_root: Path | None = None
_processing_worker_lock = threading.Lock()


def _has_pending_processing() -> bool:
    from transcript_pipeline.file_tracker import FileTracker

    tracker = FileTracker(db_path=PROCESSED_DB)
    for base in (VIDEO_COMPRESS, AUDIO_BASE, VIDEOS_BASE):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_MEDIA:
                continue
            if base == VIDEOS_BASE and "live_capture" in path.relative_to(base).parts:
                continue
            if base == VIDEO_COMPRESS:
                return True
            if not tracker.is_file_processed(path):
                return True
    return False


def _execute_processing_job(mode: str, cancel_check=lambda: False) -> None:
    global _run_state
    with _run_lock:
        if not _run_state.get("running"):
            _run_state.update(running=True, mode=mode, started_at=datetime.now().isoformat(),
                              finished_at=None, error=None, log_tail="", stage="upload", stages=_fresh_stages())
    try:
        _run_pipeline(mode, cancel_check=cancel_check)
    finally:
        if _run_state.get("running"):
            _run_state["running"] = False
            _run_state["finished_at"] = datetime.now().isoformat()


def _get_processing_worker() -> ProcessingWorker:
    global _processing_worker, _processing_worker_root
    root = ROOT.resolve()
    with _processing_worker_lock:
        if _processing_worker is None or _processing_worker_root != root:
            store = ProcessingJobStore(root)
            _processing_worker = ProcessingWorker(
                store, _execute_processing_job, timezone_name=SETTINGS.processing_timezone,
                scan_pending=lambda: not _run_state.get("running") and _has_pending_processing(),
                executor_accepts_cancel=True,
            )
            _processing_worker_root = root
        return _processing_worker


def _get_capture_service() -> CaptureService:
    global _capture_service, _capture_service_root
    root = VIDEOS_BASE.resolve()
    with _capture_service_lock:
        if _capture_service is None or _capture_service_root != root:
            service = CaptureService(videos_root=root)
            for session in service.list_sessions():
                if session.status is capture_models.SessionStatus.ACTIVE:
                    service.reconcile(session.session_id)
            _capture_service = service
            _capture_service_root = root
        return _capture_service


def _get_playlist_service() -> PlaylistService:
    return PlaylistService(_get_capture_service())


def _hostname_only(host_header: str) -> str:
    """Strips the port from a Host/Origin-style host, IPv6-bracket aware."""
    host_header = host_header.strip().lower()
    if host_header.startswith("["):
        return host_header.split("]")[0].lstrip("[")
    if host_header.count(":") == 1:
        return host_header.rsplit(":", 1)[0]
    return host_header


def _allowed_request_hostnames() -> set[str]:
    """Loopback names plus (only with LAN mode) configured/detected LAN hosts."""
    return _LOCAL_HOSTNAMES | _LAN_HOST_ALLOWLIST


@app.before_request
def _enforce_local_only() -> Any:
    allowed = _allowed_request_hostnames()
    if SETTINGS.lan_access:
        try:
            remote = ipaddress.ip_address(request.remote_addr or "")
        except ValueError:
            return jsonify({"ok": False, "error": "This dashboard is available only on the local network."}), 403
        if not remote.is_loopback and not remote.is_private:
            logger.warning("[SECURITY] Rejected non-private LAN client: %s", remote)
            return jsonify({"ok": False, "error": "Forbidden"}), 403

    host = _hostname_only(request.host or "")
    if host not in allowed:
        logger.warning("[SECURITY] Rejected request with non-local Host: %s", request.host)
        return jsonify({"ok": False, "error": "This dashboard host is not authorized."}), 403

    if SETTINGS.lan_access and not request.is_secure and host not in _LOCAL_HOSTNAMES:
        if request.method not in {"GET", "HEAD"} or request.path not in {
            "/setup",
            "/setup/",
            "/setup/certificate",
            "/setup/qr.svg",
        }:
            return redirect(f"https://{host}:{_lan_https_port()}/", code=302)

    if request.method in _MUTATING_METHODS:
        origin = request.headers.get("Origin")
        if origin and (urlparse(origin).hostname or "").lower() not in allowed:
            logger.warning("[SECURITY] Rejected %s with non-local Origin: %s", request.method, origin)
            return jsonify({"ok": False, "error": "This request origin is not authorized."}), 403

        token = request.headers.get("X-Local-Dashboard-Token", "")
        if not secrets.compare_digest(token, _DASHBOARD_TOKEN):
            logger.warning("[SECURITY] Rejected %s with missing/invalid dashboard token", request.method)
            return jsonify({"ok": False, "error": "Dashboard authorization expired. Reload Whisper and try again."}), 403

    return None


@app.errorhandler(SecurityError)
def _handle_security_error(e: SecurityError) -> Any:
    # Never echo the resolved/candidate path back to the client.
    logger.warning("[SECURITY] %s: %s", type(e).__name__, e)
    status = 404 if isinstance(e, PathNotFoundError) else 400
    return jsonify({"ok": False, "error": "Invalid or forbidden path"}), status


@app.errorhandler(413)
def _handle_too_large(e: Any) -> Any:
    return jsonify({"ok": False, "error": "File too large"}), 413


@app.errorhandler(capture_errors.LiveCaptureError)
def _handle_capture_error(e: capture_errors.LiveCaptureError) -> Any:
    # A corrupt-manifest message embeds the resolved filesystem path — never
    # echo that back to the client; log it server-side and return a generic body.
    if isinstance(e, capture_errors.ManifestCorruptError):
        logger.warning("[CAPTURE] %s", e)
        return jsonify({"ok": False, "error": "Capture data is corrupted"}), 500
    status = {
        capture_errors.ValidationError: 400,
        capture_errors.SessionNotFoundError: 404,
        capture_errors.ChunkNotFoundError: 404,
        capture_errors.SessionConflictError: 409,
        capture_errors.InvalidTransitionError: 409,
        capture_errors.FragmentConflictError: 409,
        capture_errors.AssemblyError: 409,
        capture_errors.ChunkTooLargeError: 413,
        capture_errors.FragmentTooLargeError: 413,
    }.get(type(e), 500)
    return jsonify({"ok": False, "error": str(e)}), status


# ── Global run state ─────────────────────────────────────────────────────
_run_lock = threading.Lock()
_run_state: dict[str, Any] = {
    "running": False,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "log_tail": "",
    "stage": None,
    "stages": {},
}


def _fresh_stages() -> dict[str, dict[str, Any]]:
    """Per-stage state for a new run: every stage pending, no fabricated
    progress (progress stays None unless a real measurable total exists)."""
    return {name: {"status": "pending", "progress": None} for name in PIPELINE_STAGES}

# The real pipeline lifecycle, in order. `_infer_stage` derives "how far the
# current run has gotten" from real subprocess output (never fabricated) by
# scanning for markers this codebase's own logging already emits — see
# CLAUDE.md's Architecture section for where each marker comes from.
PIPELINE_STAGES = ["upload", "analyze", "compress", "transcribe", "vision_ocr", "route", "document", "store"]

_STAGE_MARKERS: list[tuple[str, str]] = [
    ("STEP 1: Compressing videos", "compress"),
    ("[SCAN]", "analyze"),
    ("[TUTORIAL]", "analyze"),
    ("[INIT] Loading Whisper model", "transcribe"),
    ("[OK]", "transcribe"),
    ("[KEYFRAMES]", "vision_ocr"),
    ("[MEETING_DEV]", "vision_ocr"),
    ("completed_routed", "route"),
    ("[DOCS]", "document"),
    ("[SAVE]", "store"),
    ("PROCESS FINISHED", "store"),
]


def _infer_stage(log_tail: str) -> str | None:
    """Furthest pipeline stage reached so far in this run's real log output.

    Tracks the max stage index seen (not "last line matched") so a
    multi-file run doesn't appear to regress when file N+1 starts back at
    "analyze" while file N already reached "store".

    Also derives the per-stage `_run_state["stages"]` map: stages before the
    furthest reached are "completed", the furthest is "running", the rest
    stay "pending". Progress is never fabricated — it stays None.
    """
    reached_idx = -1
    stage: str | None = None
    for line in log_tail.splitlines():
        for marker, candidate in _STAGE_MARKERS:
            if marker in line:
                idx = PIPELINE_STAGES.index(candidate)
                if idx > reached_idx:
                    reached_idx = idx
                    stage = candidate
    if stage is not None:
        _apply_stage_derivation(stage)
    return stage


def _apply_stage_derivation(current: str) -> None:
    """Marks stages up to `current` as completed/running in `_run_state`.

    `current` is the furthest stage reached; everything before it is
    completed, it is running, everything after stays pending. If the run has
    already errored, the furthest reached stage is instead marked "failed"
    (localizing the failure to the stage where it happened) and later stages
    remain pending.
    """
    current_idx = PIPELINE_STAGES.index(current)
    stages = _run_state.setdefault("stages", _fresh_stages())
    for name in PIPELINE_STAGES:
        idx = PIPELINE_STAGES.index(name)
        entry = stages.setdefault(name, {"status": "pending", "progress": None})
        if idx < current_idx:
            entry["status"] = "completed"
        elif idx == current_idx:
            entry["status"] = "failed" if _run_state.get("error") else "running"
        else:
            entry["status"] = "pending"


def _atomic_write_text(path: Path, content: str) -> None:
    """Writes `content` to `path` without leaving a corrupt/truncated file
    if the process is interrupted mid-write."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


# ── File helpers ──────────────────────────────────────────────────────────
def _to_media_id(root: MediaRoot, absolute_path: Path) -> str:
    """Absolute path -> opaque `"<root>:<relative>"` id safe to hand to the browser.

    Replaces exposing `str(path)` (an absolute local filesystem path) in API
    responses — the id encodes which allowed root the file lives under plus
    a path relative to it, with no information about where the repo itself
    sits on disk.
    """
    return f"{root.value}:{RESOLVER.to_id(root, absolute_path)}"


def _from_media_id(media_id: str, allowed_roots: list[MediaRoot], *, must_exist: bool = True) -> Path:
    """Resolves a `_to_media_id()` id back to a real path, validated against
    `allowed_roots`. Raises `PathTraversalError`/`PathNotFoundError` —
    callers should let these propagate to the `SecurityError` errorhandler
    rather than catch them, so the resolved path never leaks into a
    per-endpoint error message.
    """
    if not media_id:
        raise PathTraversalError("id required")
    root_key, sep, relative = media_id.partition(":")
    if not sep:
        raise PathTraversalError(f"Malformed id: {media_id!r}")
    try:
        root = MediaRoot(root_key)
    except ValueError:
        raise PathTraversalError(f"Unknown root in id: {root_key!r}") from None
    if root not in allowed_roots:
        raise PathTraversalError(f"Root {root_key!r} not allowed for this operation")
    return RESOLVER.resolve(root, relative, must_exist=must_exist)


def _is_valid_media_file(path: Path) -> bool:
    """Confirms `path`'s actual content is audio/video, not just its
    extension — a renamed `.exe` saved as `.mp3` would otherwise be
    accepted. Same ffprobe invocation pattern/timeout as
    `media/compressor.py::get_video_info`; never trusts the client-sent
    MIME type, which `request.files` doesn't even expose here."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)]
    try:
        result = run_ffprobe(cmd, retry_on_timeout=False)
        streams = json.loads(result.stdout).get("streams", [])
        return any(s.get("codec_type") in ("audio", "video") for s in streams)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("[UPLOAD] ffprobe validation failed for %s: %s", path.name, e)
        return False


def _ensure_folders() -> None:
    for folder in (VIDEO_COMPRESS, AUDIO_BASE, VIDEOS_BASE, TRANSCRIPTIONS_BASE):
        folder.mkdir(parents=True, exist_ok=True)


def _load_projects() -> list[dict]:
    if not PROJECTS_PATH.exists():
        return []
    try:
        return json.loads(PROJECTS_PATH.read_text(encoding="utf-8")).get("projects", [])
    except Exception as e:
        logger.error("[PROJECTS] Error loading projects.json: %s", e)
        return []


def _save_projects(projects: list[dict]) -> bool:
    try:
        data = {"projects": projects}
        _atomic_write_text(PROJECTS_PATH, json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        logger.error("[PROJECTS] Error saving projects.json: %s", e)
        return False


def _find_matching_project(filename: str) -> dict | None:
    name_lower = filename.lower()
    for project in _load_projects():
        rules = project.get("match", {})
        for prefix in rules.get("prefix", []):
            if name_lower.startswith(prefix.lower()):
                return project
        for keyword in rules.get("filename_contains", []):
            if keyword.lower() in name_lower:
                return project
    return None


def _reserve_upload_destination(directory: Path, filename: str) -> Path:
    original = directory / filename
    candidate = original
    counter = 1
    while True:
        try:
            descriptor = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        except FileExistsError:
            candidate = original.with_name(f"{original.stem}_{counter:02d}{original.suffix}")
            counter += 1
            continue
        os.close(descriptor)
        return candidate


def _project_overrides_path() -> Path:
    # Derived from ROOT on every access (not a module constant) so tests that
    # monkeypatch ROOT get an isolated overrides file.
    return ROOT / "project_overrides.json"


def _load_project_overrides() -> dict[str, str]:
    """Persisted `media_id -> project_name` manual assignments.

    Reloaded from disk on every access: the file is tiny, and a dashboard
    restart (or an external edit) must never be masked by a stale cache.
    """
    path = _project_overrides_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        overrides = data.get("overrides", {})
        if isinstance(overrides, dict):
            return {str(k): str(v) for k, v in overrides.items()}
    except Exception as e:
        logger.error("[PROJECTS] Error loading project_overrides.json: %s", e)
    return {}


def _save_project_overrides(overrides: dict[str, str]) -> bool:
    try:
        _atomic_write_text(
            _project_overrides_path(),
            json.dumps({"overrides": overrides}, indent=2, ensure_ascii=False),
        )
        return True
    except Exception as e:
        logger.error("[PROJECTS] Error saving project_overrides.json: %s", e)
        return False


def _snapshot_text_file(path: Path) -> tuple[bool, str]:
    """Capture enough state to restore a small text persistence file exactly."""
    if not path.exists():
        return False, ""
    return True, path.read_text(encoding="utf-8")


def _restore_text_snapshot(path: Path, snapshot: tuple[bool, str]) -> None:
    """Restore a text file snapshot using the same atomic write primitive."""
    existed, content = snapshot
    if existed:
        _atomic_write_text(path, content)
    else:
        path.unlink(missing_ok=True)


def _rollback_text_snapshots(snapshots: dict[Path, tuple[bool, str]]) -> bool:
    """Best-effort rollback for a multi-file logical transaction.

    Returns False if any rollback write itself fails. Callers still fail the
    request; rollback failures are logged at CRITICAL because manual recovery
    may be required.
    """
    ok = True
    for snapshot_path, snapshot in snapshots.items():
        try:
            _restore_text_snapshot(snapshot_path, snapshot)
        except Exception:
            ok = False
            logger.critical("[ATOMICITY] Rollback failed for %s", snapshot_path.name, exc_info=True)
    return ok


def _effective_project(media_id: str, filename: str) -> tuple[dict | None, str]:
    """Resolves the project shown/used for a file.

    Priority: manual override > auto-detected (filename rules) > none. A
    manual override whose project no longer exists in projects.json is
    dropped (and treated as no project) rather than silently falling back to
    auto-detection — the owner explicitly chose that project.
    """
    overrides = _load_project_overrides()
    if media_id and media_id in overrides:
        override_name = overrides[media_id]
        for project in _load_projects():
            if project.get("name") == override_name:
                return project, "manual"
        overrides.pop(media_id, None)
        _save_project_overrides(overrides)
        return None, "none"
    project = _find_matching_project(filename)
    if project:
        return project, "auto"
    return None, "none"


def _count_files(folder: Path, extensions: set[str] | None = None, recursive: bool = True) -> int:
    if not folder.exists():
        return 0
    files = folder.rglob("*") if recursive else folder.iterdir()
    files = [f for f in files if f.is_file()]
    if extensions:
        files = [f for f in files if f.suffix.lower() in extensions]
    return len(files)


def _detect_language(filename: str, project: dict | None) -> str:
    """Displayed language: es_/en_ prefix > project.language > auto."""
    name_lower = filename.lower()
    if name_lower.startswith("es_"):
        return "es"
    if name_lower.startswith("en_"):
        return "en"
    if project and project.get("language"):
        return project["language"]
    return "auto"


def _file_status(path: Path) -> str:
    try:
        if not PROCESSED_DB.exists():
            return "pending"
        db = json.loads(PROCESSED_DB.read_text(encoding="utf-8"))
        size = path.stat().st_size
        mtime = int(path.stat().st_mtime)
        with open(path, "rb") as f:
            chunk = f.read(8192)
        content = f"{size}_{mtime}_{__import__('hashlib').md5(chunk).hexdigest()}"
        file_hash = __import__("hashlib").sha256(content.encode()).hexdigest()[:16]
        if file_hash in db:
            return db[file_hash].get("status", "processed")
        if str(path.absolute()) in db:
            return db[str(path.absolute())].get("status", "processed")
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix().casefold()
        suffix = f"/{relative}"
        for key, entry in db.items():
            if not isinstance(entry, dict):
                continue
            stored_path = str(entry.get("path") or key).replace("\\", "/").casefold()
            if stored_path.endswith(suffix):
                return entry.get("status", "processed")
        return "pending"
    except Exception:
        return "pending"


def _user_video_state(path: Path) -> str:
    status = _file_status(path).lower()
    if status in {"completed", "processed", "success", "auto_detected", "existing_transcription"}:
        return "COMPLETED"
    if status in {"failed", "error", "failed_routed"}:
        return "FAILED"
    if status in {"processing", "running"}:
        return "PROCESSING_MEDIA"
    return "READY"


def _resolve_transcription(media_path: Path) -> dict | None:
    """Finds the transcription matching an audio/video file."""
    try:
        rel = media_path.relative_to(VIDEOS_BASE)
        output_folder = TRANSCRIPTIONS_BASE / rel.parent
    except ValueError:
        try:
            rel = media_path.relative_to(AUDIO_BASE)
            output_folder = TRANSCRIPTIONS_BASE / rel.parent
        except ValueError:
            output_folder = TRANSCRIPTIONS_BASE

    candidates = [
        output_folder / f"{media_path.stem}.txt",
        output_folder / f"{media_path.stem}_timestamps.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return {
                "id": _to_media_id(MediaRoot.TRANSCRIPTIONS, candidate),
                "size": candidate.stat().st_size,
                "modified": datetime.fromtimestamp(candidate.stat().st_mtime).isoformat(),
            }
    return None


def _count_words(text: str) -> int:
    return len(text.split())


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _format_media_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hrs}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"


def _probe_media_duration(media_path: Path) -> float | None:
    try:
        stat = media_path.stat()
    except OSError:
        return None
    cache_key = (str(media_path.resolve()), stat.st_size, stat.st_mtime_ns)
    new_future = None
    with _MEDIA_DURATION_CACHE_LOCK:
        if cache_key in _MEDIA_DURATION_CACHE:
            return _MEDIA_DURATION_CACHE[cache_key]
        if cache_key not in _MEDIA_DURATION_FUTURES:
            new_future = _MEDIA_DURATION_EXECUTOR.submit(_probe_media_duration_sync, media_path)
            _MEDIA_DURATION_FUTURES[cache_key] = new_future
    if new_future is not None:
        new_future.add_done_callback(lambda completed, key=cache_key: _cache_media_duration(key, completed))
    return None


def _probe_media_duration_sync(media_path: Path) -> float | None:
    duration_result = None
    try:
        result = run_ffprobe(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=duration", "-of", "json", str(media_path)],
            timeout=5,
            retries=0,
            retry_on_timeout=False,
        )
        data = json.loads(result.stdout or "{}")
        values = [(data.get("format") or {}).get("duration")]
        values.extend(stream.get("duration") for stream in data.get("streams", []))
        for value in values:
            if value is None:
                continue
            duration = float(value)
            if math.isfinite(duration) and duration > 0:
                duration_result = duration
                break
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return duration_result


def _cache_media_duration(cache_key: tuple[str, int, int], future: Future[float | None]) -> None:
    try:
        result = future.result()
    except Exception:
        result = None
    with _MEDIA_DURATION_CACHE_LOCK:
        if len(_MEDIA_DURATION_CACHE) > 512:
            _MEDIA_DURATION_CACHE.clear()
        _MEDIA_DURATION_CACHE[cache_key] = result
        _MEDIA_DURATION_FUTURES.pop(cache_key, None)


def _media_duration_pending(media_path: Path) -> bool:
    try:
        stat = media_path.stat()
    except OSError:
        return False
    cache_key = (str(media_path.resolve()), stat.st_size, stat.st_mtime_ns)
    with _MEDIA_DURATION_CACHE_LOCK:
        return cache_key in _MEDIA_DURATION_FUTURES


def _delete_action(user_state: str, *, capture_active: bool = False) -> tuple[bool, str | None]:
    state = (user_state or "READY").upper()
    if capture_active or state == "CAPTURING":
        return False, "Stop the recording before deleting"
    if state in {"UPLOADING", "QUEUED", "PROCESSING", "PROCESSING_MEDIA", "GENERATING_DOCUMENTATION", "CANCEL_REQUESTED"}:
        return False, "Stop processing before deleting"
    return True, None


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def _parse_segments(segments_path: Path, text: str = "", duration: float = 0) -> list[dict]:
    if segments_path.exists():
        try:
            data = json.loads(segments_path.read_text(encoding="utf-8"))
            return data.get("segments", [])
        except Exception:
            pass
    # Fallback: a single segment with the whole text
    if text:
        return [{"start": 0.0, "end": duration, "text": text}]
    return []


def _resolve_frames(media_path: Path) -> dict | None:
    """Finds the frames folder and mapping JSON matching a video."""
    try:
        rel = media_path.relative_to(VIDEOS_BASE)
        output_folder = TRANSCRIPTIONS_BASE / rel.parent
    except ValueError:
        try:
            rel = media_path.relative_to(AUDIO_BASE)
            output_folder = TRANSCRIPTIONS_BASE / rel.parent
        except ValueError:
            output_folder = TRANSCRIPTIONS_BASE

    # KeyframeExtractor saves to: CarpetaTranscripciones/<project>/<stem>_Frames/<stem>/
    frames_parent = output_folder / f"{media_path.stem}_Frames" / media_path.stem
    mapping_file = frames_parent / "frame_mapping.json"
    if not mapping_file.exists():
        return None
    try:
        data = json.loads(mapping_file.read_text(encoding="utf-8"))
        frames = data.get("frames", [])
        for frame in frames:
            frame_id = _to_media_id(MediaRoot.TRANSCRIPTIONS, frames_parent / frame["frame_file"])
            frame["url"] = f"/frame?id={quote(frame_id, safe='')}"
        return {
            "frames": frames,
            "count": len(frames),
        }
    except Exception as e:
        logger.warning("[FRAMES] Error reading mapping: %s", e)
        return None


def _documentation_dirs(media_path: Path) -> Path | None:
    """Same `frames_parent` convention as `_resolve_frames`, without requiring
    frame_mapping.json to exist (manual/ai-package live alongside it)."""
    try:
        rel = media_path.relative_to(VIDEOS_BASE)
        output_folder = TRANSCRIPTIONS_BASE / rel.parent
    except ValueError:
        try:
            rel = media_path.relative_to(AUDIO_BASE)
            output_folder = TRANSCRIPTIONS_BASE / rel.parent
        except ValueError:
            return None
    return output_folder / f"{media_path.stem}_Frames" / media_path.stem


def _resolve_documentation(media_path: Path, root: MediaRoot) -> dict | None:
    """Reports whether the video-to-documentation engine already produced a
    manual/AI package for this source video, without loading their content
    (kept cheap since this runs once per row in `/api/files`).

    V2 surfacing (PLAN WP-17): distinguishes evidence-only output from a
    semantic-manual-ready result so the UI can label the documentation state
    without a redesign — the existing "Open generated documentation" action
    already opens MANUAL.md, which IS the semantic manual whenever synthesis
    succeeded, and the Evidence Timeline stays separately discoverable under
    the frames directory."""
    frames_parent = _documentation_dirs(media_path)
    if frames_parent is None:
        return None
    manual_meta = frames_parent / "manual" / "metadata.json"
    ai_manifest = frames_parent / "ai-package" / "manifest.json"
    has_manual = manual_meta.exists()
    has_ai_package = ai_manifest.exists()
    if not has_manual and not has_ai_package:
        return None
    has_semantic_manual = (frames_parent / "manual" / "knowledge-document.json").exists()
    has_evidence = (frames_parent / "evidence" / "evidence.jsonl").exists()
    if has_semantic_manual:
        documentation_status = "semantic_manual_ready"
    elif has_evidence:
        documentation_status = "evidence_only"
    else:
        documentation_status = "legacy_manual"
    return {
        "has_manual": has_manual,
        "has_ai_package": has_ai_package,
        "has_semantic_manual": has_semantic_manual,
        "has_evidence_timeline": has_evidence,
        "documentation_status": documentation_status,
        "media_id": _to_media_id(root, media_path),
    }


def _media_recorded_datetime(media_path: Path, root: MediaRoot, modified_at: float) -> datetime:
    """Capture recorded_at wins; legacy/ordinary media falls back to mtime."""
    if root is MediaRoot.VIDEOS:
        try:
            relative = media_path.relative_to(VIDEOS_BASE)
            if len(relative.parts) == 4 and relative.parts[0] == "live_capture" and relative.parts[2] in {"chunks", "final"}:
                from transcript_pipeline.live_capture.pipeline import parse_chunk_index

                service = _get_capture_service()
                session = service.store.load_session(relative.parts[1])
                index = parse_chunk_index(media_path)
                chunk = session.get_chunk(index) if index is not None else None
                recorded_at = (chunk.recorded_at if chunk else None) or session.recorded_at
                if recorded_at:
                    return datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
                created_at = chunk.created_at if chunk else session.created_at
                return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.fromtimestamp(modified_at).astimezone()


def _is_test_capture_session(session: capture_models.Session) -> bool:
    return session.is_test_session or bool(re.search(r"\b(synthetic|fixture|e2e test)\b", session.title, re.IGNORECASE))


def _capture_user_status(session: capture_models.Session) -> str:
    states = [chunk.state for chunk in session.chunks]
    if capture_models.ChunkState.CANCEL_REQUESTED in states:
        return "CANCEL_REQUESTED"
    if capture_models.ChunkState.PROCESSING in states:
        return "PROCESSING"
    if capture_models.ChunkState.FAILED in states:
        return "FAILED"
    if capture_models.ChunkState.CANCELLED in states:
        return "CANCELLED"
    if states and all(state is capture_models.ChunkState.PROCESSED for state in states):
        return "COMPLETED"
    if capture_models.ChunkState.FINALIZED in states:
        return "QUEUED"
    return "CAPTURING" if session.status is capture_models.SessionStatus.ACTIVE else session.status.value


def _frame_media_url(frames_parent: Path, relative_to_frames_parent: str) -> str:
    """URL for a raw frame file (relative to frames_parent, where
    KeyframeExtractor wrote it — NOT manual_dir, whose assets/ only holds
    copies made for MANUAL.md/ai-package)."""
    frame_id = _to_media_id(MediaRoot.TRANSCRIPTIONS, frames_parent / relative_to_frames_parent)
    return f"/doc-asset?id={quote(frame_id, safe='')}"


# ── Endpoints ────────────────────────────────────────────────────────────
@app.route("/")
def index() -> str:
    addresses = lan_access.advertised_lan_ipv4_addresses(SETTINGS.lan_hosts) if SETTINGS.lan_access else []
    setup_url = f"http://{addresses[0]}:{_lan_http_port()}/setup" if addresses else ""
    return render_template(
        "dashboard.html",
        dashboard_token=_DASHBOARD_TOKEN,
        build_revision=BUILD_REVISION,
        upload_concurrency=SETTINGS.upload_concurrency,
        mobile_setup_url=setup_url,
    )


@app.route("/setup")
@app.route("/setup/")
def mobile_setup() -> Any:
    host = _hostname_only(request.host or "")
    if not SETTINGS.lan_access or not lan_access.is_private_ipv4(host) or host not in _LAN_HOST_ALLOWLIST:
        return jsonify({"ok": False, "error": "Mobile setup is available only at this computer's LAN IP."}), 404
    secure_url = f"https://{host}:{_lan_https_port()}/"
    if request.cookies.get("whisper_secure_setup") == "1":
        return redirect(secure_url, code=302)
    response = make_response(render_template("mobile_setup.html", secure_url=secure_url))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/setup/certificate")
def mobile_setup_certificate() -> Any:
    if not SETTINGS.lan_access:
        return jsonify({"ok": False, "error": "LAN access is disabled."}), 404
    ca_path = lan_access.default_runtime_dir() / lan_access.CA_FILE_NAME
    if not ca_path.is_file():
        return jsonify({"ok": False, "error": "Whisper LAN root certificate is not configured."}), 503
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.x509.oid import NameOID

    try:
        root = x509.load_pem_x509_certificate(ca_path.read_bytes())
    except ValueError:
        return jsonify({"ok": False, "error": "Whisper LAN root certificate is invalid."}), 503
    common_names = root.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    try:
        is_ca = root.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        is_ca = False
    if not is_ca or not common_names or common_names[0].value != "Whisper LAN Local CA":
        return jsonify({"ok": False, "error": "Whisper LAN root certificate is invalid."}), 503
    public_root = root.public_bytes(serialization.Encoding.DER)
    return send_file(
        io.BytesIO(public_root),
        mimetype="application/pkix-cert",
        as_attachment=True,
        download_name="Whisper-LAN-Local-CA.cer",
        max_age=0,
    )


@app.route("/setup/qr.svg")
def mobile_setup_qr() -> Any:
    addresses = lan_access.advertised_lan_ipv4_addresses(SETTINGS.lan_hosts) if SETTINGS.lan_access else []
    if not addresses:
        return jsonify({"ok": False, "error": "No LAN address is available."}), 404
    import qrcode
    from qrcode.image.svg import SvgPathImage

    qr = qrcode.QRCode(box_size=6, border=4)
    qr.add_data(f"http://{addresses[0]}:{_lan_http_port()}/setup")
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    response = make_response(image.to_string())
    response.headers["Content-Type"] = "image/svg+xml"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.after_request
def prevent_stale_browser_assets(response) -> Any:
    response.headers["X-Whisper-Build"] = BUILD_REVISION
    if request.method == "GET":
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/api/status")
def api_status() -> Any:
    state = dict(_run_state)
    worker = _get_processing_worker()
    jobs = worker.store.list_jobs()
    active_jobs = [job for job in jobs if job.get("status") in {"ACTIVE", "CANCEL_REQUESTED"}]
    active_job = max(active_jobs, key=lambda job: job.get("started_at") or "") if active_jobs else None
    state["worker"] = worker.status()
    state["running"] = active_job is not None
    if active_job is not None:
        state["mode"] = active_job.get("mode")
        state["started_at"] = active_job.get("started_at")
        state["finished_at"] = None
        owns_job = (
            active_job.get("worker_pid") == os.getpid()
            and active_job.get("worker_host") == socket.gethostname()
        )
        if not owns_job:
            state["stage"] = None
            state["stages"] = {}
            state["log_tail"] = ""
    return jsonify(state)


@app.route("/api/worker/jobs/<job_id>/cancel", methods=["POST"])
def api_worker_cancel_job(job_id: str) -> Any:
    store = _get_processing_worker().store
    if not store.cancel(job_id):
        return jsonify({"ok": False, "error": "Processing job was not found."}), 404
    job = next(item for item in store.list_jobs() if item["id"] == job_id)
    return jsonify({"ok": True, "state": job["status"]})


@app.route("/api/health")
def api_health() -> Any:
    """Backend liveness used by the UI's ONLINE indicator.

    Same-origin relative call: the phone reaches the same server that serves
    the page, so this is the authoritative "the backend is up" signal — never
    inferred from a hardcoded loopback URL.
    """
    return jsonify({"ok": True, "status": "ONLINE", "service": "whisper-dashboard"})


@app.route("/api/network")
def api_network() -> Any:
    """Advertised LAN endpoints/setup for the phone, built from real request data.

    URLs are assembled from the detected/configured LAN hosts and the actual
    serving scheme — no loopback literal is hardcoded into a client-facing
    URL. Empty list when LAN access is disabled.
    """
    lan_access_enabled = bool(SETTINGS.lan_access)
    https_active = bool(request.is_secure)
    https_available = lan_access_enabled and _lan_https_available()
    port = (_lan_https_port() if https_available else _lan_http_port()) if lan_access_enabled else SETTINGS.dashboard_port
    scheme = "https" if https_available else ("https" if https_active else "http")

    advertised: list[str] = []
    if lan_access_enabled:
        seen: set[str] = set()
        hosts = [*SETTINGS.lan_hosts, *lan_access.advertised_lan_ipv4_addresses(SETTINGS.lan_hosts)]
        for host in hosts:
            normalized = lan_access.normalize_host(host)
            if not normalized or normalized in seen or normalized in {"localhost", "127.0.0.1"}:
                continue
            seen.add(normalized)
            advertised.append(f"{scheme}://{normalized}:{port}/")

    certificate = SETTINGS.dashboard_cert_file or (lan_access.default_runtime_dir() / lan_access.CERT_FILE_NAME)
    fingerprint = None
    if certificate.is_file():
        try:
            fingerprint = lan_access.certificate_fingerprint(certificate)
        except Exception:
            fingerprint = None

    return jsonify(
        {
            "ok": True,
            "lan_access": lan_access_enabled,
            "https": https_active,
            "https_available": https_available,
            "port": port,
            "http_port": _lan_http_port() if lan_access_enabled else None,
            "https_port": _lan_https_port() if lan_access_enabled else None,
            "urls": advertised,
            "health_path": "/api/health",
            "cert_fingerprint_sha256": fingerprint,
            "setup_doc": "docs/ops/MOBILE_LAN_ACCESS.md",
        }
    )


@app.route("/api/folders")
def api_folders() -> Any:
    _ensure_folders()
    return jsonify(
        {
            "folders": [
                {
                    "name": "Video_compress",
                    "count": _count_files(VIDEO_COMPRESS, SUPPORTED_MEDIA, recursive=False),
                },
                {
                    "name": "Videos",
                    "count": _count_files(VIDEOS_BASE, SUPPORTED_MEDIA),
                },
                {
                    "name": "audio",
                    "count": _count_files(AUDIO_BASE, SUPPORTED_MEDIA),
                },
                {
                    "name": "CarpetaTranscripciones",
                    "count": _count_files(TRANSCRIPTIONS_BASE, {".txt"}),
                },
            ]
        }
    )


@app.route("/api/files")
def api_files() -> Any:
    _ensure_folders()
    media_files: list[dict] = []
    listed_capture_sessions: set[str] = set()
    listed_logical_videos: set[tuple[str, str]] = set()

    for base, root in ((VIDEOS_BASE, MediaRoot.VIDEOS), (AUDIO_BASE, MediaRoot.AUDIO)):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_MEDIA:
                continue
            relative_parts = path.relative_to(base).parts
            media_kind = "audio" if root is MediaRoot.AUDIO else "video"
            capture_session = None
            if root is MediaRoot.VIDEOS and relative_parts and relative_parts[0] == "live_capture":
                if len(relative_parts) != 4 or relative_parts[2] not in {"chunks", "final"}:
                    continue
                session_id = relative_parts[1]
                try:
                    session = _get_capture_service().get_session(session_id)
                except (ValueError, OSError, capture_errors.ValidationError):
                    continue
                if _is_test_capture_session(session):
                    continue
                if relative_parts[2] == "chunks" and session.final_media:
                    continue
                capture_session = session
                media_kind = session.capture_kind
            media_stat = path.stat()
            media_date = _media_recorded_datetime(path, root, media_stat.st_mtime)
            transcription = _resolve_transcription(path)
            media_id = _to_media_id(root, path)
            project, project_source = _effective_project(media_id, path.name)
            from transcript_pipeline.pipeline_metrics import get_metrics

            user_state = _user_video_state(path)
            if media_id in _doc_generation_inflight:
                user_state = "GENERATING_DOCUMENTATION"
            elif media_id in _reprocess_inflight:
                user_state = "PROCESSING_MEDIA"
            file_row = {
                    "media_id": media_id,
                    "relative": str(path.relative_to(ROOT)),
                    "name": path.name,
                    "size": media_stat.st_size,
                    "date": media_date.astimezone().isoformat(timespec="seconds"),
                    "date_epoch": media_date.timestamp(),
                    "status": _file_status(path),
                    "user_state": user_state,
                    "media_kind": media_kind,
                    "timings": get_metrics(project.get("name") if project else None, path.name),
                    "language": _detect_language(path.name, project),
                    "project": project.get("name") if project else None,
                    "project_source": project_source,
                    "transcription": transcription,
                    "documentation": _resolve_documentation(path, root),
                }
            if capture_session is not None:
                file_row["project"] = capture_session.project_id
                file_row["project_source"] = "capture_session"
                file_row["capture_session_id"] = capture_session.session_id
                file_row["capture_kind"] = capture_session.capture_kind
                file_row["capture_source"] = capture_session.capture_source
                file_row["capture_status"] = _capture_user_status(capture_session)
                file_row["user_state"] = file_row["capture_status"]
                file_row["duration_sec"] = (capture_session.final_media or {}).get("durationSec")
            if file_row.get("duration_sec") is None:
                file_row["duration_sec"] = _probe_media_duration(path)
                file_row["duration_pending"] = _media_duration_pending(path)
            else:
                file_row["duration_pending"] = False
            duration = file_row.get("duration_sec")
            file_row["duration"] = _format_media_duration(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0 else None
            capture_active = capture_session is not None and capture_session.status is capture_models.SessionStatus.ACTIVE
            file_row["delete_allowed"], file_row["delete_reason"] = _delete_action(
                str(file_row.get("user_state") or file_row.get("status") or ""), capture_active=capture_active
            )
            if (root is MediaRoot.VIDEOS and capture_session is not None and relative_parts
                    and relative_parts[0] == "live_capture" and relative_parts[2] == "chunks"):
                chunk_id = path.stem
                logical_rows = []
                all_logical_rows = []
                if session.capture_mode == "playlist":
                    try:
                        playlist = _get_playlist_service().list(session_id)
                        all_logical_rows = [
                            logical for logical in playlist.get("logicalVideos", [])
                            if logical.get("status") == "CONFIRMED"
                        ]
                        logical_rows = [
                            logical for logical in all_logical_rows
                            if chunk_id in logical.get("processingChunkIds", [])
                            and (session_id, str(logical.get("id"))) not in listed_logical_videos
                        ]
                    except (ValueError, OSError, capture_errors.ValidationError):
                        logger.exception("Could not list logical videos for %s", session_id)
                for logical in logical_rows:
                    logical_row = dict(file_row)
                    logical_row["logical_video"] = {
                        key: logical.get(key) for key in (
                            "id", "title", "category", "sessionNumber", "recordedAt", "confidence",
                            "startOffsetMs", "endOffsetMs", "processingChunkIds", "projectId",
                        )
                    }
                    logical_row["logical_session_id"] = session_id
                    logical_row["logical_video_count"] = len(all_logical_rows)
                    logical_row["capture_status"] = _capture_user_status(session)
                    logical_row["status"] = logical_row["capture_status"]
                    logical_row["name"] = f"{logical.get('title') or session.title}{path.suffix}"
                    logical_row["project"] = session.project_id
                    logical_row["logical_read_only"] = True
                    listed_logical_videos.add((session_id, str(logical.get("id"))))
                    displayed_at = logical.get("recordedAt")
                    if displayed_at:
                        try:
                            parsed = datetime.fromisoformat(str(displayed_at).replace(" UTC", "+00:00"))
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            logical_row["date_epoch"] = parsed.timestamp()
                            logical_row["date"] = parsed.astimezone().isoformat(timespec="seconds")
                        except ValueError:
                            pass
                    media_files.append(logical_row)
                if not all_logical_rows and session_id not in listed_capture_sessions:
                    file_row["name"] = f"{session.title}{path.suffix}"
                    file_row["project"] = session.project_id
                    file_row["capture_session_id"] = session_id
                    file_row["capture_status"] = _capture_user_status(session)
                    file_row["status"] = file_row["capture_status"]
                    file_row["logical_read_only"] = True
                    file_row["capture_session_fallback"] = True
                    media_files.append(file_row)
                listed_capture_sessions.add(session_id)
                continue
            if (root is MediaRoot.VIDEOS and capture_session is not None and relative_parts
                    and relative_parts[0] == "live_capture" and relative_parts[2] == "final"):
                logical_videos = []
                if capture_session.capture_mode == "playlist":
                    try:
                        logical_videos = [
                            item for item in _get_playlist_service().list(session_id).get("logicalVideos", [])
                            if item.get("status") == "CONFIRMED"
                        ]
                    except (ValueError, OSError, capture_errors.ValidationError):
                        logger.exception("Could not list logical videos for %s", session_id)
                for logical in logical_videos:
                    logical_row = dict(file_row)
                    logical_row["logical_video"] = {
                        key: logical.get(key) for key in (
                            "id", "title", "category", "sessionNumber", "recordedAt", "confidence",
                            "startOffsetMs", "endOffsetMs", "processingChunkIds", "projectId",
                        )
                    }
                    logical_row["logical_session_id"] = session_id
                    logical_row["logical_video_count"] = len(logical_videos)
                    logical_row["name"] = f"{logical.get('title') or capture_session.title}{path.suffix}"
                    logical_row["project"] = capture_session.project_id
                    logical_row["logical_read_only"] = True
                    displayed_at = logical.get("recordedAt")
                    if displayed_at:
                        try:
                            parsed = datetime.fromisoformat(str(displayed_at).replace(" UTC", "+00:00"))
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            logical_row["date_epoch"] = parsed.timestamp()
                            logical_row["date"] = parsed.astimezone().isoformat(timespec="seconds")
                        except ValueError:
                            pass
                    media_files.append(logical_row)
                if not logical_videos and session_id not in listed_capture_sessions:
                    file_row["name"] = f"{capture_session.title}{path.suffix}"
                    file_row["project"] = capture_session.project_id
                    file_row["capture_session_id"] = capture_session.session_id
                    file_row["capture_status"] = _capture_user_status(capture_session)
                    file_row["status"] = file_row["capture_status"]
                    if capture_session.capture_mode == "playlist":
                        file_row["logical_read_only"] = True
                        file_row["capture_session_fallback"] = True
                    media_files.append(file_row)
                listed_capture_sessions.add(session_id)
                continue
            media_files.append(file_row)

    sort_by = request.args.get("sort_by", "date").lower()
    direction = request.args.get("order", "desc").lower()
    reverse = direction != "asc"
    if sort_by == "name":
        media_files.sort(key=lambda item: item["name"].lower(), reverse=reverse)
    elif sort_by == "duration":
        media_files.sort(key=lambda item: (item.get("duration_sec") is not None,
                                           item.get("duration_sec") or 0), reverse=reverse)
    else:
        media_files.sort(key=lambda item: (item["date_epoch"], item["name"].lower()), reverse=reverse)
    return jsonify({"files": media_files})


@app.route("/api/compression/provenance")
def api_compression_provenance() -> Any:
    """Auditable compression retention: sizes saved and cleanup outcome."""
    from transcript_pipeline.media.optimize import CLEANUP_PENDING, ProvenanceStore

    store = ProvenanceStore(ROOT / "compression_provenance.json")
    records = []
    for record in store.list():
        state = record.get("cleanupState")
        records.append({
            "source_relative": record.get("sourceRelative"),
            "output_relative": record.get("outputRelative"),
            "source_size": record.get("sourceSize"),
            "output_size": record.get("outputSize"),
            "bytes_saved": record.get("bytesSaved"),
            "source_duration": record.get("sourceDuration"),
            "output_duration": record.get("outputDuration"),
            "cleanup_state": state,
            "reason": record.get("reason"),
            "updated_at": record.get("updatedAt"),
            "retry_allowed": state == CLEANUP_PENDING,
        })
    return jsonify({"ok": True, "records": records})


@app.route("/api/compression/retry-cleanup", methods=["POST"])
def api_compression_retry_cleanup() -> Any:
    """Retry source removal for a provenance-matched optimized output only."""
    from transcript_pipeline.media.optimize import CLEANUP_PENDING, ProvenanceStore, retry_source_cleanup

    payload = request.get_json(force=True) or {}
    output_relative = payload.get("output_relative")
    if not isinstance(output_relative, str) or not output_relative:
        return jsonify({"ok": False, "error": "output_relative is required"}), 400
    store = ProvenanceStore(ROOT / "compression_provenance.json")
    record = store.load().get(output_relative)
    if record is None:
        return jsonify({"ok": False, "error": "unknown provenance record"}), 404
    # Only a cleanup that is still pending may be retried. A record whose source
    # is already gone or was intentionally retained must never be removed here,
    # even when its recorded hashes still match the files on disk.
    if record.get("cleanupState") != CLEANUP_PENDING:
        return jsonify({
            "ok": False,
            "error": "cleanup is not pending for this record",
            "cleanup_state": record.get("cleanupState"),
        }), 409
    state = retry_source_cleanup(output_relative, base_path=ROOT, provenance=store)
    record = store.load().get(output_relative, {})
    return jsonify({
        "ok": True,
        "cleanup_state": state,
        "reason": record.get("reason"),
        "retry_allowed": state == "CLEANUP_PENDING",
    })


@app.route("/api/projects")
def api_projects() -> Any:
    return jsonify({"projects": _load_projects()})


@app.route("/api/projects", methods=["POST"])
def api_projects_update() -> Any:
    payload = request.get_json(force=True) or {}
    action = payload.get("action")
    projects = _load_projects()
    original_overrides = _load_project_overrides()

    new_projects = list(projects)
    new_overrides = dict(original_overrides)

    if action == "create":
        new_project = payload.get("project")
        errors = validate_project(new_project)
        if errors or not isinstance(new_project, dict):
            return jsonify({"ok": False, "error": "; ".join(errors) or "Invalid project"}), 400
        if any(p["name"] == new_project["name"] for p in projects):
            return jsonify({"ok": False, "error": "Project already exists"}), 400
        new_projects.append(new_project)

    elif action == "update":
        name = payload.get("name")
        updated = payload.get("project")
        if not name:
            return jsonify({"ok": False, "error": "Incomplete data"}), 400
        if not any(p.get("name") == name for p in projects):
            return jsonify({"ok": False, "error": "Project not found"}), 404
        errors = validate_project(updated)
        if errors or not isinstance(updated, dict):
            return jsonify({"ok": False, "error": "; ".join(errors) or "Invalid project"}), 400
        updated_name = updated.get("name")
        if not isinstance(updated_name, str):
            return jsonify({"ok": False, "error": "Invalid project name"}), 400
        if updated_name != name and any(p.get("name") == updated_name for p in projects):
            return jsonify({"ok": False, "error": "Project already exists"}), 400

        new_projects = [updated if p["name"] == name else p for p in projects]
        if updated_name != name:
            new_overrides = {
                media_id: (updated_name if project_name == name else project_name)
                for media_id, project_name in original_overrides.items()
            }

    elif action == "delete":
        deleted_name = payload.get("name")
        if not deleted_name or not any(p.get("name") == deleted_name for p in projects):
            return jsonify({"ok": False, "error": "Project not found"}), 404
        new_projects = [p for p in projects if p["name"] != deleted_name]
        new_overrides = {
            media_id: project_name
            for media_id, project_name in original_overrides.items()
            if project_name != deleted_name
        }

    else:
        return jsonify({"ok": False, "error": "Unknown action"}), 400

    projects_snapshot = _snapshot_text_file(PROJECTS_PATH)
    overrides_path = _project_overrides_path()
    overrides_snapshot = _snapshot_text_file(overrides_path)
    snapshots = {
        PROJECTS_PATH: projects_snapshot,
        overrides_path: overrides_snapshot,
    }

    try:
        if not _save_projects(new_projects):
            raise OSError("projects persistence failed")
        if new_overrides != original_overrides and not _save_project_overrides(new_overrides):
            raise OSError("project override persistence failed")
    except Exception:
        rollback_ok = _rollback_text_snapshots(snapshots)
        logger.exception("[PROJECTS] Atomic project operation failed; rollback_ok=%s", rollback_ok)
        return jsonify({"ok": False, "error": "Could not save project changes safely"}), 500

    return jsonify({"ok": True, "projects": new_projects})


@app.route("/api/upload", methods=["POST"])
def api_upload() -> Any:
    upload_started = time.perf_counter()
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file sent"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400

    project_id = (request.form.get("project_id") or request.form.get("project") or "").strip()
    filename = secure_filename(Path(file.filename).name)
    if not filename:
        return jsonify({"ok": False, "error": "Invalid filename"}), 400
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_MEDIA:
        return jsonify({"ok": False, "error": f"Unsupported format: {ext}"}), 400

    chosen_project = None
    if project_id:
        for project in _load_projects():
            if project.get("id") == project_id or project.get("name") == project_id:
                chosen_project = project
                break
        if chosen_project is None:
            return jsonify({"ok": False, "error": "Selected project does not exist", "project_id": project_id}), 400

    upload_id = (request.form.get("upload_id") or "").strip()
    if upload_id:
        if len(upload_id) > 128:
            return jsonify({"ok": False, "error": "Invalid upload id"}), 400
        from transcript_pipeline.upload_idempotency import find_upload

        previous = find_upload(upload_id, chosen_project.get("name") if chosen_project else project_id, VIDEO_COMPRESS)
        if previous:
            return jsonify({"ok": True, "name": previous["name"], "project_id": project_id or None,
                            "duplicate": True})

    # If the file has no recognizable prefix and a project was chosen, apply its first prefix
    if chosen_project:
        rules = chosen_project.get("match", {})
        prefixes = rules.get("prefix", [])
        if prefixes and not _find_matching_project(filename):
            prefix = prefixes[0]
            filename = f"{prefix}{filename}" if not filename.lower().startswith(prefix.lower()) else filename

    VIDEO_COMPRESS.mkdir(parents=True, exist_ok=True)
    destination = _reserve_upload_destination(VIDEO_COMPRESS, filename)

    try:
        file.save(str(destination))
    except Exception:
        destination.unlink(missing_ok=True)
        logger.exception("[UPLOAD] Error saving %s", filename)
        return jsonify({"ok": False, "error": "Could not process upload"}), 500

    if not _is_valid_media_file(destination):
        destination.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": "Uploaded file is not a valid media file"}), 400

    logger.info("[UPLOAD] %s → %s", filename, destination)
    from transcript_pipeline.pipeline_metrics import record_stage

    upload_seconds = time.perf_counter() - upload_started
    record_stage(chosen_project.get("name") if chosen_project else project_id, destination.name, "upload", upload_seconds)
    if upload_id:
        from transcript_pipeline.upload_idempotency import remember_upload

        remember_upload(upload_id, chosen_project.get("name") if chosen_project else project_id,
                        VIDEO_COMPRESS, destination.name, destination.stat().st_size)
    return jsonify({"ok": True, "name": destination.name, "project_id": project_id or None,
                    "upload_duration_seconds": round(upload_seconds, 3)})


@app.route("/api/run/<mode>", methods=["POST"])
def api_run(mode: str) -> Any:
    if mode not in ("full", "compress", "transcribe"):
        return jsonify({"ok": False, "error": "Invalid mode"}), 400

    worker = _get_processing_worker()
    with _run_lock:
        if _run_state["running"]:
            return jsonify({"ok": False, "error": "A run is already in progress"}), 409
        if any(job.get("status") in {"QUEUED", "PENDING", "ACTIVE", "CANCEL_REQUESTED"}
               for job in worker.store.list_jobs()):
            return jsonify({"ok": False, "error": "A processing job is already queued or active."}), 409
        _run_state.update(
            {
                "running": True,
                "mode": mode,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "error": None,
                "log_tail": "",
                "stage": "upload",
                "stages": _fresh_stages(),
            }
        )
    try:
        job = worker.store.enqueue(mode)
        if app.config.get("TESTING"):
            worker.run_pending_once()
        else:
            worker.start()
    except Exception:
        _run_state.update(running=False, error="Could not queue processing job")
        logger.exception("[WORKER] Could not queue Run Full job")
        return jsonify({"ok": False, "error": "Whisper could not queue this run. Check server storage and retry."}), 500
    return jsonify({"ok": True, "mode": mode, "job_id": job["id"], "state": job["status"]})


@app.route("/api/logs")
def api_logs() -> Any:
    lines: list[str] = []
    for log_file in ("dashboard.log", "master_process.log", "simple_scan.log"):
        # LOG_DIR is canonical since the data-root split; ROOT keeps working
        # as a legacy fallback for logs written flat before it.
        path = next(
            (c for c in (LOG_DIR / log_file, ROOT / log_file) if c.exists()),
            None,
        )
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                lines.extend([f"[{log_file}] {line}" for line in text.splitlines()[-200:]])
            except Exception:
                pass
    lines = lines[-300:]
    return jsonify({"logs": lines})


@app.route("/api/transcription")
def api_transcription() -> Any:
    resolved = _from_media_id(request.args.get("id", ""), [MediaRoot.TRANSCRIPTIONS])
    try:
        text = resolved.read_text(encoding="utf-8", errors="ignore")
        folder = resolved.parent
        stem = resolved.stem
        segments_path = folder / f"{stem}_segments.json"
        metadata_path = folder / f"{stem}_metadata.json"
        metadata = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        segments = _parse_segments(segments_path, text, metadata.get("duration", 0))
        return jsonify({
            "ok": True,
            "text": text,
            "segments": segments,
            "insights": {
                "language": metadata.get("language") or "unknown",
                "duration": metadata.get("duration", 0),
                "duration_formatted": _format_duration(metadata.get("duration", 0)),
                "word_count": _count_words(text),
                "model": "whisper-large-v3",
                "processing_time": metadata.get("processing_time", 0),
                "processing_time_formatted": f"{metadata.get('processing_time', 0):.1f} sec",
            }
        })
    except Exception:
        logger.exception("[TRANSCRIPTION] Error reading %s", resolved)
        return jsonify({"ok": False, "error": "Could not read transcription"}), 500


@app.route("/stream")
def stream_media() -> Any:
    """Serves audio/video files under Videos/, audio/, or Video_compress/ for the player."""
    target = _from_media_id(
        request.args.get("id", ""), [MediaRoot.AUDIO, MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS]
    )
    return send_from_directory(str(target.parent), target.name)


@app.route("/api/video/black-intervals", methods=["POST"])
def api_video_black_intervals() -> Any:
    payload = request.get_json(force=True) or {}
    target = _from_media_id(payload.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS])
    if target.suffix.lower() not in VIDEO_EXTS:
        return jsonify({"ok": False, "error": "Choose a video file"}), 400
    try:
        scan = detect_black_intervals(
            target,
            darkness_threshold=float(payload.get("darkness_threshold", 0.05)),
            minimum_duration_seconds=float(payload.get("minimum_duration_seconds", 2.0)),
        )
    except (RuntimeError, ValueError, subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("[VIDEO_CUT] Black-frame scan failed for %s: %s", target.name, exc)
        return jsonify({"ok": False, "error": "Could not scan this video"}), 422
    return jsonify({"ok": True, **scan})


@app.route("/api/video/remove-black", methods=["POST"])
def api_video_remove_black() -> Any:
    payload = request.get_json(force=True) or {}
    target = _from_media_id(payload.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS])
    if target.suffix.lower() not in VIDEO_EXTS:
        return jsonify({"ok": False, "error": "Choose a video file"}), 400
    intervals = payload.get("intervals")
    if not isinstance(intervals, list) or not intervals or len(intervals) > 1000:
        return jsonify({"ok": False, "error": "No valid black intervals were selected"}), 400
    if payload.get("auto") is True and payload.get("confidence") != "high":
        return jsonify({"ok": False, "status": "NEEDS_REVIEW", "error": "Low confidence; review detected ranges first"}), 409
    try:
        output = trim_black_intervals(target, intervals)
        return jsonify({"ok": True, "name": output.name})
    except FileExistsError:
        return jsonify({"ok": False, "error": "A trimmed copy already exists"}), 409
    except (RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("[VIDEO_CUT] Trim failed for %s: %s", target.name, exc)
        return jsonify({"ok": False, "error": "Could not create a trimmed copy"}), 422


@app.route("/api/video/edit", methods=["POST"])
def api_video_edit() -> Any:
    """Queue a reviewed edit; identical retries share one job and derivative."""
    payload = request.get_json(force=True) or {}
    try:
        target = _from_media_id(payload.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS])
        if target.suffix.lower() not in VIDEO_EXTS:
            return jsonify({"ok": False, "error": "Choose a video file"}), 400
        cuts = payload.get("cuts", [])
        crop = payload.get("crop")
        if not isinstance(cuts, list) or len(cuts) > 1000 or (crop is not None and not isinstance(crop, dict)):
            return jsonify({"ok": False, "error": "Invalid edit specification"}), 400
        start = float(payload.get("trim_start", 0))
        end = payload.get("trim_end")
        end = None if end is None else float(end)
        if not math.isfinite(start) or (end is not None and not math.isfinite(end)):
            return jsonify({"ok": False, "error": "Trim bounds must be finite"}), 400
        validate_video_edit_spec(target, cuts, trim_start=start, trim_end=end, crop=crop)
        canonical = json.dumps({"path": str(target.resolve()), "mtime": target.stat().st_mtime_ns, "size": target.stat().st_size,
                                "cuts": cuts, "trim_start": start, "trim_end": end, "crop": crop}, sort_keys=True)
        key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        source_key = str(target.resolve())
        with _VIDEO_EDIT_JOBS_LOCK:
            existing_id = _VIDEO_EDIT_KEYS.get(key)
            if existing_id and existing_id in _VIDEO_EDIT_JOBS:
                existing_job = _VIDEO_EDIT_JOBS[existing_id]
                if existing_job.get("status") != "FAILED":
                    return jsonify({"ok": True, "job_id": existing_id, **existing_job})
                _VIDEO_EDIT_KEYS.pop(key, None)
            active_id = _VIDEO_EDIT_SOURCE_JOBS.get(source_key)
            active_job = _VIDEO_EDIT_JOBS.get(active_id or "")
            if active_job and active_job.get("status") in {"PROCESSING", "VALIDATING"}:
                return jsonify({"ok": False, "error": "An edit for this source is already processing"}), 409
            output = target.with_name(f"{target.stem}_edited.mp4")
            if output.exists():
                return jsonify({"ok": False, "error": "An edited copy already exists; no duplicate was created"}), 409
            job_id = secrets.token_urlsafe(18)
            _VIDEO_EDIT_KEYS[key] = job_id
            _VIDEO_EDIT_SOURCE_JOBS[source_key] = job_id
            _VIDEO_EDIT_JOBS[job_id] = {"status": "PROCESSING", "progress": 5, "message": "Processing", "source": target.name}

        def update(status: str, progress: int) -> None:
            with _VIDEO_EDIT_JOBS_LOCK:
                job = _VIDEO_EDIT_JOBS.get(job_id)
                if job:
                    job.update(status=status, progress=progress, message="Validating" if status == "VALIDATING" else "Processing")

        def run_edit() -> None:
            try:
                output_path, provenance = apply_video_edits(target, cuts, trim_start=start, trim_end=end, crop=crop, progress=update)
                with _VIDEO_EDIT_JOBS_LOCK:
                    _VIDEO_EDIT_JOBS[job_id].update(status="COMPLETED", progress=100, message="Completed", ok=True,
                        name=output_path.name, duration_seconds=provenance["output_duration_seconds"],
                        provenance=output_path.with_suffix(".provenance.json").name, validated=provenance["validated"])
            except Exception as exc:
                logger.exception("[VIDEO_EDIT] Edit failed for %s", target.name)
                with _VIDEO_EDIT_JOBS_LOCK:
                    _VIDEO_EDIT_JOBS[job_id].update(status="FAILED", progress=100, message=str(exc) or "Edit failed", ok=False)
                    if _VIDEO_EDIT_SOURCE_JOBS.get(source_key) == job_id:
                        _VIDEO_EDIT_SOURCE_JOBS.pop(source_key, None)
        _VIDEO_EDIT_EXECUTOR.submit(run_edit)
        return jsonify({"ok": True, "job_id": job_id, "status": "PROCESSING"}), 202
    except (RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError, FileNotFoundError, SecurityError) as exc:
        return jsonify({"ok": False, "error": str(exc) or "Invalid edit specification"}), 400


@app.route("/api/video/edit-jobs/<job_id>", methods=["GET"])
def api_video_edit_job(job_id: str) -> Any:
    with _VIDEO_EDIT_JOBS_LOCK:
        job = _VIDEO_EDIT_JOBS.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "Edit job not found"}), 404
        return jsonify({"ok": True, **job})

@app.route("/api/video/black-borders", methods=["POST"])
def api_video_black_borders() -> Any:
    payload = request.get_json(force=True) or {}
    target = _from_media_id(payload.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS])
    if target.suffix.lower() not in VIDEO_EXTS:
        return jsonify({"ok": False, "error": "Choose a video file"}), 400
    try:
        result = detect_black_borders(target, darkness_threshold=float(payload.get("darkness_threshold", 0.05)))
    except (RuntimeError, ValueError, subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("[VIDEO_CROP] Border scan failed for %s: %s", target.name, exc)
        return jsonify({"ok": False, "error": "Could not scan video borders"}), 422
    return jsonify({"ok": True, **result})


@app.route("/api/video/crop-black-borders", methods=["POST"])
def api_video_crop_black_borders() -> Any:
    payload = request.get_json(force=True) or {}
    target = _from_media_id(payload.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS])
    if target.suffix.lower() not in VIDEO_EXTS:
        return jsonify({"ok": False, "error": "Choose a video file"}), 400
    crop = payload.get("crop")
    if not isinstance(crop, dict):
        return jsonify({"ok": False, "error": "No border crop was provided"}), 400
    if payload.get("auto") is True and payload.get("confidence") != "high":
        return jsonify({"ok": False, "status": "NEEDS_REVIEW", "error": "Low confidence; review the crop first"}), 409
    try:
        output = crop_black_borders(target, crop)
        return jsonify({"ok": True, "name": output.name})
    except FileExistsError:
        return jsonify({"ok": False, "error": "A cropped copy already exists"}), 409
    except (RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("[VIDEO_CROP] Crop failed for %s: %s", target.name, exc)
        return jsonify({"ok": False, "error": "Could not create a cropped copy"}), 422


@app.route("/api/transcription", methods=["POST"])
def api_transcription_save() -> Any:
    payload = request.get_json(force=True) or {}
    text = payload.get("text", "")
    media_id = str(payload.get("media_id") or "")
    tx_id = str(payload.get("id") or "")
    if not isinstance(text, str):
        return jsonify({"ok": False, "error": "text must be a string"}), 400
    media_target = None
    if tx_id:
        resolved = _from_media_id(tx_id, [MediaRoot.TRANSCRIPTIONS])
        filename = resolved.name
    else:
        if not media_id:
            return jsonify({"ok": False, "error": "media_id required to add a transcription"}), 400
        if not text.strip():
            return jsonify({"ok": False, "error": "transcription cannot be empty"}), 400
        media_target = _from_media_id(media_id, [MediaRoot.VIDEOS, MediaRoot.AUDIO])
        try:
            relative = media_target.relative_to(VIDEOS_BASE)
        except ValueError:
            relative = media_target.relative_to(AUDIO_BASE)
        resolved = TRANSCRIPTIONS_BASE / relative.parent / f"{media_target.stem}.txt"
        if resolved.exists():
            return jsonify({"ok": False, "error": "A transcription already exists"}), 409
        filename = media_target.name
    override_project: str | None = None
    if media_id:
        media_target = media_target or _from_media_id(media_id, [MediaRoot.VIDEOS, MediaRoot.AUDIO], must_exist=False)
        filename = media_target.name
        raw_project = payload.get("project")
        normalized = raw_project.strip() if isinstance(raw_project, str) else ""
        if normalized and normalized.lower() != "auto":
            if not any(p.get("name") == normalized for p in _load_projects()):
                return jsonify({"ok": False, "error": f"Project not found: {normalized}"}), 400
            override_project = normalized

    segments_path = resolved.parent / f"{resolved.stem}_segments.json"
    segments_content: str | None = None
    if segments_path.exists():
        try:
            segments_data = json.loads(segments_path.read_text(encoding="utf-8"))
            segments_data["text"] = text
            segments_content = json.dumps(segments_data, indent=2, ensure_ascii=False)
        except Exception:
            logger.exception("[TRANSCRIPTION] Could not prepare segment update for %s", resolved.name)
            return jsonify({"ok": False, "error": "Could not prepare transcription update"}), 500

    overrides_path = _project_overrides_path()
    snapshots: dict[Path, tuple[bool, str]] = {resolved: _snapshot_text_file(resolved)}
    if segments_path.exists():
        snapshots[segments_path] = _snapshot_text_file(segments_path)
    if media_id:
        snapshots[overrides_path] = _snapshot_text_file(overrides_path)

    new_overrides = _load_project_overrides() if media_id else {}
    if media_id:
        if override_project is not None:
            new_overrides[media_id] = override_project
        else:
            new_overrides.pop(media_id, None)

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(resolved, text)
        if segments_content is not None:
            _atomic_write_text(segments_path, segments_content)
        if media_id and not _save_project_overrides(new_overrides):
            raise OSError("project override persistence failed")
    except Exception:
        rollback_ok = _rollback_text_snapshots(snapshots)
        logger.exception("[TRANSCRIPTION] Atomic Edit File save failed; rollback_ok=%s", rollback_ok)
        return jsonify({"ok": False, "error": "Could not save Edit File changes safely"}), 500

    effective, project_source = _effective_project(media_id, filename)
    return jsonify(
        {
            "ok": True,
            "project": effective.get("name") if effective else None,
            "project_source": project_source,
        }
    )


@app.route("/api/file", methods=["DELETE"])
def api_delete_file() -> Any:
    deleted_id = request.args.get("id", "")
    target = _from_media_id(
        deleted_id,
        [MediaRoot.AUDIO, MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS, MediaRoot.TRANSCRIPTIONS],
    )

    try:
        relative = target.relative_to(VIDEOS_BASE)
    except ValueError:
        relative = None
    if relative is not None and len(relative.parts) >= 3 and relative.parts[0] == "live_capture":
        session_id = relative.parts[1]
        try:
            _get_capture_service().delete_session(session_id, confirmed=request.args.get("confirm") == "true")
        except capture_errors.InvalidTransitionError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except capture_errors.ValidationError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "capture_session_deleted": True})

    overrides_path = _project_overrides_path()
    overrides_snapshot = _snapshot_text_file(overrides_path)
    overrides = _load_project_overrides()
    had_override = bool(deleted_id and deleted_id in overrides)

    # A stale manual assignment is worse than an aborted delete: persist the
    # override cleanup before the destructive filesystem operation. If the
    # delete itself then fails, restore the previous override snapshot.
    if had_override:
        updated_overrides = dict(overrides)
        updated_overrides.pop(deleted_id, None)
        if not _save_project_overrides(updated_overrides):
            return jsonify({"ok": False, "error": "Could not persist project cleanup"}), 500

    try:
        transcription = _resolve_transcription(target)
        project, _source = _effective_project(deleted_id, target.name)
        target.unlink()
        try:
            from transcript_pipeline.pipeline_metrics import remove_metrics

            remove_metrics(project.get("name") if project else None, target.name)
        except Exception:
            logger.exception("[DELETE] Could not clean up timing metadata for %s", target.name)
        if target.is_relative_to(VIDEO_COMPRESS):
            try:
                from transcript_pipeline.upload_idempotency import remove_upload_records

                remove_upload_records(VIDEO_COMPRESS, target.name)
            except Exception:
                logger.exception("[DELETE] Could not clean up upload idempotency metadata for %s", target.name)
        if transcription:
            tx_folder = _from_media_id(transcription["id"], [MediaRoot.TRANSCRIPTIONS]).parent
            stem = target.stem
            for child in tx_folder.iterdir():
                if child.is_file() and child.stem.startswith(stem):
                    try:
                        child.unlink()
                    except Exception as e:
                        logger.warning("[DELETE] Could not delete %s: %s", child, e)

        try:
            if PROCESSED_DB.exists():
                db = json.loads(PROCESSED_DB.read_text(encoding="utf-8"))
                keys = [k for k, v in db.items() if v.get("path") == str(target.absolute()) or v.get("name") == target.name]
                for k in keys:
                    del db[k]
                _atomic_write_text(PROCESSED_DB, json.dumps(db, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.warning("[DELETE] Could not clean up DB: %s", e)

        return jsonify({"ok": True})
    except Exception:
        if had_override:
            try:
                _restore_text_snapshot(overrides_path, overrides_snapshot)
            except Exception:
                logger.critical("[DELETE] Could not restore project override after delete failure", exc_info=True)
        logger.exception("[DELETE] Error deleting %s", target)
        return jsonify({"ok": False, "error": "Could not delete file"}), 500


@app.route("/api/frames")
def api_frames() -> Any:
    target = _from_media_id(
        request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO]
    )
    info = _resolve_frames(target)
    if info is None:
        # Valid media whose keyframe extraction never ran is a normal state,
        # not an error — a 404 here made the browser log a network error on
        # every frames-tab open for frame-less media.
        return jsonify({"ok": True, "frames": [], "count": 0})
    return jsonify({"ok": True, **info})


@app.route("/frame")
def serve_frame() -> Any:
    """Serves frame images under CarpetaTranscripciones/."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.TRANSCRIPTIONS])
    return send_from_directory(str(target.parent), target.name)


@app.route("/api/documentation")
def api_documentation() -> Any:
    """Human manual + AI package summary for a source video (US-001 §3.6)."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None:
        return jsonify({"ok": False, "error": "No documentation available"}), 404

    manual_dir = frames_parent / "manual"
    ai_dir = frames_parent / "ai-package"
    manual_md_path = manual_dir / "MANUAL.md"
    manifest_path = ai_dir / "manifest.json"

    if not manual_md_path.exists() and not manifest_path.exists():
        return jsonify({"ok": False, "error": "No documentation available"}), 404

    def asset_url(relative_to_manual_dir: str) -> str:
        asset_id = _to_media_id(MediaRoot.TRANSCRIPTIONS, manual_dir / relative_to_manual_dir)
        return f"/doc-asset?id={quote(asset_id, safe='')}"

    manual_pdf_path = manual_dir / "MANUAL.pdf"
    manual_pdf_available = manual_pdf_path.exists()
    manual_pdf_url = asset_url("MANUAL.pdf") if manual_pdf_available else None
    manual_pdf_error = None
    if not manual_pdf_available:
        # Surface WHY the PDF is absent instead of silently pretending the
        # human bundle is complete: the engine records the outcome of its
        # PDF attempt in metadata.json ("ok" / "failed" / "missing").
        pdf_state = None
        metadata_path = manual_dir / "metadata.json"
        if metadata_path.exists():
            try:
                pdf_state = json.loads(metadata_path.read_text(encoding="utf-8")).get("manual_pdf")
            except Exception:
                pdf_state = None
        if pdf_state == "failed":
            manual_pdf_error = "MANUAL.pdf generation failed — see server logs."
        elif pdf_state == "missing":
            manual_pdf_error = "reportlab not installed — install the [pdf] extra to generate MANUAL.pdf."
        else:
            manual_pdf_error = "MANUAL.pdf not generated."

    manual_md = None
    if manual_md_path.exists():
        raw_md = manual_md_path.read_text(encoding="utf-8")
        # MANUAL.md references images as "assets/<file>" relative to manual_dir —
        # rewrite each to a servable /doc-asset URL before handing it to the client.
        manual_md = re.sub(r"assets/([\w.\-]+)", lambda m: asset_url(m.group(0)), raw_md)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None

    def ai_package_url(filename: str) -> str | None:
        path = ai_dir / filename
        if not path.exists():
            return None
        asset_id = _to_media_id(MediaRoot.TRANSCRIPTIONS, path)
        return f"/doc-asset?id={quote(asset_id, safe='')}"

    ai_package_files = {
        "manifest": ai_package_url("manifest.json"),
        "chunks": ai_package_url("chunks.jsonl"),
        "knowledge": ai_package_url("knowledge.md"),
    } if manifest_path.exists() else None

    steps_payload = []
    if (manual_dir / "steps.json").exists():
        _, steps = load_steps(manual_dir)
        for step in steps:
            step_dict = step.to_dict()
            if step.frame_ref:
                step_dict["frame_url"] = _frame_media_url(frames_parent, step.frame_ref)
            steps_payload.append(step_dict)

    return jsonify({
        "ok": True,
        "manual_markdown": manual_md,
        "manifest": manifest,
        "steps": steps_payload,
        "ai_package_files": ai_package_files,
        "manual_pdf_url": manual_pdf_url,
        "manual_pdf_available": manual_pdf_available,
        "manual_pdf_error": manual_pdf_error,
    })


@app.route("/api/documentation/step", methods=["PATCH"])
def api_documentation_update_step() -> Any:
    """Human review edit (US-001 §4.8): edit a step's title/instruction, or
    toggle its reviewed flag, and regenerate both bundles — no re-transcription."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None or not (frames_parent / "manual" / "steps.json").exists():
        return jsonify({"ok": False, "error": "No documentation available"}), 404

    payload = request.get_json(silent=True) or {}
    step_id = payload.get("step_id")
    if not step_id:
        return jsonify({"ok": False, "error": "step_id required"}), 400

    try:
        updated = update_step(
            frames_parent / "manual", frames_parent / "ai-package", frames_parent, step_id,
            title=payload.get("title"), instruction=payload.get("instruction"), reviewed=payload.get("reviewed"),
        )
        if updated.get("frame_ref"):
            updated["frame_url"] = _frame_media_url(frames_parent, updated["frame_ref"])
        return jsonify({"ok": True, "step": updated})
    except KeyError:
        return jsonify({"ok": False, "error": f"step {step_id!r} not found"}), 404


@app.route("/api/documentation/step", methods=["DELETE"])
def api_documentation_remove_step() -> Any:
    """Human review removal (US-001 §4.8): delete an invalid step and
    regenerate both bundles — no re-transcription."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None or not (frames_parent / "manual" / "steps.json").exists():
        return jsonify({"ok": False, "error": "No documentation available"}), 404

    step_id = request.args.get("step_id", "")
    if not step_id:
        return jsonify({"ok": False, "error": "step_id required"}), 400

    try:
        result = remove_step(frames_parent / "manual", frames_parent / "ai-package", frames_parent, step_id)
        return jsonify({"ok": True, **result})
    except KeyError:
        return jsonify({"ok": False, "error": f"step {step_id!r} not found"}), 404


@app.route("/api/documentation/regenerate", methods=["POST"])
def api_documentation_regenerate() -> Any:
    """Explicit regenerate (US-001 §14 DoD): rebuild MANUAL.md/ai-package
    from the current steps.json without touching frame_mapping.json or
    re-transcribing — useful after hand-editing steps.json directly."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None or not (frames_parent / "manual" / "steps.json").exists():
        return jsonify({"ok": False, "error": "No documentation available"}), 404

    result = regenerate_from_steps(frames_parent / "manual", frames_parent / "ai-package", frames_parent, target.name)
    return jsonify({"ok": True, **result})


@app.route("/api/documentation/v2/regenerate", methods=["POST"])
def api_documentation_v2_regenerate() -> Any:
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None or not (frames_parent / "frame_mapping.json").exists():
        return jsonify({"ok": False, "error": "Saved frame mapping is required; reprocess the video first."}), 409
    root = MediaRoot.VIDEOS if VIDEOS_BASE in target.parents else MediaRoot.AUDIO
    media_id = _to_media_id(root, target)
    project, _source = _effective_project(media_id, target.name)
    with _doc_generation_lock:
        if media_id in _doc_generation_inflight:
            return jsonify({"ok": False, "error": "Documentation is already generating for this video."}), 409
        _doc_generation_inflight.add(media_id)
    try:
        from transcript_pipeline.documentation.regenerate_v2 import regenerate_documentation_v2
        from transcript_pipeline.documentation.versioning import regenerate_versioned

        docs_started = time.perf_counter()
        result = regenerate_versioned(
            frames_parent, media_id, regenerate_documentation_v2, project_config=project
        )
        from transcript_pipeline.pipeline_metrics import record_stage

        record_stage(project.get("name") if project else None, target.name, "documentation",
                     time.perf_counter() - docs_started)
        return jsonify({"ok": True, "pipeline": "documentation-v2", "result": result,
                        "documentation": _resolve_documentation(target, root)})
    except Exception as e:
        logger.exception("[DOCS V2] regenerate failed for %s", target.name)
        return jsonify({"ok": False, "error": f"Documentation V2 regeneration failed: {e}"}), 500
    finally:
        with _doc_generation_lock:
            _doc_generation_inflight.discard(media_id)


@app.route("/api/documentation/versions")
def api_documentation_versions() -> Any:
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None:
        return jsonify({"ok": False, "error": "No documentation available"}), 404
    from transcript_pipeline.documentation.versioning import list_versions

    versions = list_versions(frames_parent)
    selected = request.args.get("version", type=int)
    if selected is None:
        return jsonify({"ok": True, "versions": versions})
    version_dir = frames_parent / "documentation_versions" / f"{selected:06d}"
    manifest = version_dir / "version.json"
    manual = version_dir / "manual" / "MANUAL.md"
    if not manifest.is_file():
        return jsonify({"ok": False, "error": "Documentation version not found"}), 404
    return jsonify({"ok": True, "version": json.loads(manifest.read_text(encoding="utf-8")),
                    "manual": manual.read_text(encoding="utf-8") if manual.is_file() else ""})


@app.route("/api/video/reprocess", methods=["POST"])
def api_video_reprocess() -> Any:
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    root = MediaRoot.VIDEOS if VIDEOS_BASE in target.parents else MediaRoot.AUDIO
    media_id = _to_media_id(root, target)
    with _run_lock:
        if media_id in _reprocess_inflight or _run_state["running"] or _reprocess_inflight:
            return jsonify({"ok": False, "error": "Media processing is already active."}), 409
        _reprocess_inflight.add(media_id)

    def run() -> None:
        try:
            from transcript_pipeline.transcription.processor import SimpleScanProcessor

            processor = SimpleScanProcessor()
            if not processor.process_file(target, force=True):
                logger.error("[REPROCESS] pipeline failed for %s", target.name)
        except Exception:
            logger.exception("[REPROCESS] pipeline failed for %s", target.name)
        finally:
            with _run_lock:
                _reprocess_inflight.discard(media_id)

    threading.Thread(target=run, name="whisper-video-reprocess", daemon=True).start()
    return jsonify({"ok": True, "state": "PROCESSING_MEDIA"}), 202


@app.route("/api/documentation/generate", methods=["POST"])
def api_documentation_generate() -> Any:
    """Explicit "Generate Documentation" (US-001 §14 DoD) for a video that has
    no manual/AI package yet. Reuses existing artifacts on disk
    (frame_mapping.json + transcript) — never re-transcribes. Returns 409 with
    an actionable error when the prerequisites are missing, and rejects a
    concurrent duplicate generation for the same media_id."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.VIDEOS, MediaRoot.AUDIO])
    frames_parent = _documentation_dirs(target)
    if frames_parent is None or not (frames_parent / "frame_mapping.json").exists():
        return jsonify({
            "ok": False,
            "error": "No keyframes/frame_mapping.json found — run the pipeline first (RUN Full) to extract frames and align the transcript.",
        }), 409

    root = MediaRoot.VIDEOS if VIDEOS_BASE in target.parents else MediaRoot.AUDIO
    media_id = _to_media_id(root, target)
    project, _source = _effective_project(media_id, target.name)
    with _doc_generation_lock:
        if media_id in _doc_generation_inflight:
            return jsonify({"ok": False, "error": "Documentation is already generating for this video."}), 409
        _doc_generation_inflight.add(media_id)

    try:
        generate_documentation(frames_parent, target.name, project_config=project)
    except Exception as e:
        logger.exception("[DOCS] generate failed for %s", target.name)
        return jsonify({"ok": False, "error": f"Documentation generation failed: {e}"}), 500
    finally:
        with _doc_generation_lock:
            _doc_generation_inflight.discard(media_id)

    return jsonify({"ok": True, "documentation": _resolve_documentation(target, root)})


@app.route("/doc-asset")
def serve_doc_asset() -> Any:
    """Serves manual/ai-package assets (step screenshots) under CarpetaTranscripciones/."""
    target = _from_media_id(request.args.get("id", ""), [MediaRoot.TRANSCRIPTIONS])
    return send_from_directory(str(target.parent), target.name)


# ── Live Capture (W4) ────────────────────────────────────────────────────
# Browser camera capture surfaces the W3 `CaptureService` over the local
# dashboard API. Session IDs are validated against the strict generated-ID
# pattern inside the service; media bytes are accepted only as a raw request
# body for an existing RECORDING chunk, bounded by MAX_CONTENT_LENGTH.

def _session_payload(session: capture_models.Session) -> dict[str, Any]:
    payload = session.to_manifest()
    service = _get_capture_service()
    payload["fragmentCount"] = len(service.list_fragments(session.session_id))
    payload["processingChunkCount"] = len(service.list_processing_chunks(session.session_id))
    return payload


def _parse_crop(value: object) -> capture_models.CropRegion | None:
    """Parses a client crop payload into a validated `CropRegion`.

    `None` (or a missing field) means "no crop" — the API treats it as clear.
    A malformed/out-of-bounds crop raises `capture_errors.ValidationError`,
    which the Live Capture errorhandler already maps to a 400 without echoing
    any path.
    """
    if value is None:
        return None
    return capture_models.CropRegion.from_manifest(value)


def _parse_audio_availability(value: object) -> capture_models.AudioAvailability:
    """Parses a client audio-availability payload (W7).

    Accepts the enum value names (AVAILABLE / MISSING / UNKNOWN) or a
    missing/blank value (which means UNKNOWN). Any other value raises
    `capture_errors.ValidationError` -> 400.
    """
    if value is None or value == "":
        return capture_models.AudioAvailability.UNKNOWN
    if not isinstance(value, str):
        raise capture_errors.ValidationError("audio_availability must be a string")
    try:
        return capture_models.AudioAvailability(value)
    except ValueError as exc:
        raise capture_errors.ValidationError(
            "audio_availability must be AVAILABLE, MISSING, or UNKNOWN"
        ) from exc


@app.route("/api/capture/sessions", methods=["GET"])
def api_capture_list_sessions() -> Any:
    sessions = _get_capture_service().list_sessions()
    return jsonify({"ok": True, "sessions": [_session_payload(s) for s in sessions]})


@app.route("/api/capture/gc-candidates", methods=["GET"])
def api_capture_gc_candidates() -> Any:
    """Lists stale processed media with generated docs; never deletes media."""
    from transcript_pipeline.live_capture.gc import deletion_candidates

    try:
        days = max(1, min(3650, int(request.args.get("retention_days", "90"))))
    except ValueError:
        return jsonify({"ok": False, "error": "retention_days must be an integer"}), 400
    candidates = deletion_candidates(
        VIDEOS_BASE,
        retention_days=days,
        documentation_exists=lambda path: _resolve_documentation(path, MediaRoot.VIDEOS) is not None,
    )
    return jsonify({"ok": True, "candidates": candidates, "deletes_media": False})


@app.route("/api/capture/sessions", methods=["POST"])
def api_capture_create_session() -> Any:
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title required"}), 400
    recorded_at = payload.get("recorded_at")
    if not isinstance(recorded_at, str) or not recorded_at.strip():
        recorded_at = None
    raw_duration = payload.get("chunk_duration_sec")
    try:
        chunk_duration_sec = int(raw_duration) if raw_duration is not None else capture_models.DEFAULT_CHUNK_DURATION_SEC
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "chunk_duration_sec must be an integer"}), 400
    try:
        crop = _parse_crop(payload.get("crop"))
    except capture_errors.ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    try:
        audio_availability = _parse_audio_availability(payload.get("audio_availability"))
    except capture_errors.ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    capture_mode = str(payload.get("capture_mode") or "normal").lower()
    if capture_mode not in {"normal", "playlist"}:
        return jsonify({"ok": False, "error": "capture_mode must be normal or playlist"}), 400
    capture_kind = str(payload.get("capture_kind") or "video").lower()
    if capture_kind not in {"video", "audio"}:
        return jsonify({"ok": False, "error": "capture_kind must be video or audio"}), 400
    capture_source = payload.get("capture_source")
    capture_metadata = payload.get("capture_metadata")
    if capture_metadata is not None and not isinstance(capture_metadata, dict):
        return jsonify({"ok": False, "error": "capture_metadata must be an object"}), 400
    if capture_source is not None and capture_source not in {"environment", "user", "microphone"}:
        return jsonify({"ok": False, "error": "capture_source must be environment, user, microphone or null"}), 400
    if capture_kind == "audio" and capture_mode == "playlist":
        return jsonify({"ok": False, "error": "Audio-only capture does not support playlist mode"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    project_names = {str(project.get("name") or "").strip() for project in _load_projects()}
    project_names.discard("")
    if project_id and project_id not in project_names:
        return jsonify({"ok": False, "error": "project_id must identify an existing Whisper project"}), 400
    if not project_id:
        default_projects = [p for p in _load_projects() if p.get("default") is True and p.get("name")]
        if len(default_projects) == 1:
            project_id = str(default_projects[0]["name"])
    if not project_id:
        return jsonify({"ok": False, "error": "Select an existing Whisper project before recording"}), 400
    session = _get_capture_service().create_session(
        title, chunk_duration_sec=chunk_duration_sec, recorded_at=recorded_at, crop=crop,
        audio_availability=audio_availability, capture_mode=capture_mode, project_id=project_id,
        capture_kind=capture_kind, capture_source=capture_source,
        capture_metadata=capture_metadata,
        is_test_session=bool(payload.get("is_test_session")) and (
            app.testing or bool(app.config.get("CAPTURE_TEST_MODE"))
        ),
    )
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/capture/sessions/<session_id>", methods=["GET"])
def api_capture_get_session(session_id: str) -> Any:
    session = _get_capture_service().get_session(session_id)
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/capture/test-sessions/<session_id>/cleanup", methods=["POST"])
def api_capture_cleanup_test_session(session_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    _get_capture_service().store.delete_test_session(session_id, confirmed=payload.get("confirm") is True)
    return jsonify({"ok": True, "sessionId": session_id, "cleaned": True})


# ── W5 upload fragments ──────────────────────────────────────────────────
# Short browser fragments are transferred incrementally to a *distinct*
# fragment endpoint — never as 15-second processing chunks. Each fragment has
# a stable client ID; the server stores its media + manifest atomically and
# ACKs only after both are durable. Replaying an ID with identical bytes is
# idempotent; different bytes are a conflict.

def _fragment_payload(fragment: capture_models.Fragment) -> dict[str, Any]:
    return fragment.to_manifest()


def _probe_capture_fragment(path: Path) -> dict[str, Any]:
    """Return actual first-fragment streams without trusting browser claims."""
    try:
        result = run_ffprobe(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,channels,sample_rate",
                "-of", "json", str(path),
            ],
            timeout=10,
            retries=0,
            retry_on_timeout=False,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if video is None and audio is None:
            return {"fragmentProbeStatus": "UNKNOWN"}

        def frame_rate(item: dict[str, Any] | None) -> float | None:
            if item is None:
                return None
            raw = item.get("avg_frame_rate") or item.get("r_frame_rate")
            try:
                numerator, denominator = str(raw).split("/", 1)
                value = float(numerator) / float(denominator)
                return round(value, 3) if value > 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                return None

        raw_duration = (data.get("format") or {}).get("duration")
        try:
            duration = float(raw_duration) if isinstance(raw_duration, (int, float, str)) else None
        except (TypeError, ValueError):
            duration = None
        return {
            "fragmentProbeStatus": "VALIDATED",
            "actualVideoStreams": sum(item.get("codec_type") == "video" for item in streams),
            "actualAudioStreams": sum(item.get("codec_type") == "audio" for item in streams),
            "videoCodec": video.get("codec_name") if video else None,
            "audioCodec": audio.get("codec_name") if audio else None,
            "width": video.get("width") if video else None,
            "height": video.get("height") if video else None,
            "fps": frame_rate(video),
            "audioChannels": audio.get("channels") if audio else None,
            "audioSampleRate": audio.get("sample_rate") if audio else None,
            "durationSec": duration,
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"fragmentProbeStatus": "UNKNOWN"}


def _optional_upload_int(raw: object) -> int | None:
    """Parses optional integer upload metadata; blank/absent -> None.

    A non-integer value raises `ValidationError` (-> 400); a negative value is
    left to the service's domain validation.
    """
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(str(raw))
    except (TypeError, ValueError) as exc:
        raise capture_errors.ValidationError("numeric upload metadata must be an integer") from exc


@app.route("/api/capture/sessions/<session_id>/fragments", methods=["POST"])
def api_capture_upload_fragment(session_id: str) -> Any:
    fragment_id = str(request.form.get("fragment_id") or "").strip()
    if not fragment_id:
        return jsonify({"ok": False, "error": "fragment_id required"}), 400
    media = request.files.get("media")
    if media is None:
        return jsonify({"ok": False, "error": "media file required"}), 400
    raw_sequence = request.form.get("sequence")
    if raw_sequence is None:
        return jsonify({"ok": False, "error": "sequence must be an integer"}), 400
    try:
        sequence = int(raw_sequence)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "sequence must be an integer"}), 400
    extension = (
        request.form.get("media_extension")
        or request.form.get("extension")
        or request.headers.get("X-Media-Extension")
        or ".webm"
    )
    max_bytes = app.config.get("MAX_CONTENT_LENGTH") or (SETTINGS.upload_max_mb * 1024 * 1024)
    # W6 recorded-timeline metadata (optional): the fragment's own duration
    # and offset from the capture start drive server-side chunk aggregation.
    try:
        duration_ms = _optional_upload_int(request.form.get("duration_ms"))
        recorded_offset_ms = _optional_upload_int(request.form.get("recorded_offset_ms"))
    except capture_errors.ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    recorded_at = request.form.get("recorded_at") or None
    # Stream straight from the multipart part; the service reads it in bounded
    # blocks and writes atomically — the whole fragment is never buffered.
    fragment = _get_capture_service().upload_fragment(
        session_id,
        fragment_id,
        sequence,
        media.stream,
        media_extension=extension,
        max_bytes=max_bytes,
        duration_ms=duration_ms,
        recorded_offset_ms=recorded_offset_ms,
        recorded_at=recorded_at,
    )
    service = _get_capture_service()
    session = service.get_session(session_id)
    capture_metadata = session.capture_metadata or {}
    capture_status = None
    if len(service.list_fragments(session_id)) == 1 and capture_metadata.get("audioRequested") is not None:
        media_path = service.store.fragment_media_path(session_id, fragment.fragment_id, fragment.media_extension)
        probed = _probe_capture_fragment(media_path)
        service.set_capture_metadata(session_id, {"firstFragmentProbe": probed})
        actual_audio = probed.get("actualAudioStreams")
        if actual_audio is not None:
            availability = capture_models.AudioAvailability.AVAILABLE if actual_audio > 0 else capture_models.AudioAvailability.MISSING
            service.set_audio_availability(session_id, availability)
            if capture_metadata.get("audioRequested") is True and actual_audio == 0:
                capture_status = "AUDIO_CAPTURE_FAILED"
                service.set_capture_metadata(session_id, {"captureStatus": capture_status})
    response = {"ok": True, "fragment": _fragment_payload(fragment)}
    if capture_status:
        response["captureStatus"] = capture_status
        response["warning"] = "Microphone was requested, but the uploaded video fragment contains no audio stream. Recording is stopping."
    return jsonify(response)


@app.route("/api/capture/sessions/<session_id>/fragments", methods=["GET"])
def api_capture_list_fragments(session_id: str) -> Any:
    """Observability read: durable fragments for a session, in order."""
    fragments = _get_capture_service().list_fragments(session_id)
    return jsonify({"ok": True, "fragments": [_fragment_payload(f) for f in fragments]})


@app.route("/api/capture/sessions/<session_id>/title-samples", methods=["POST"])
def api_capture_title_sample(session_id: str) -> Any:
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("ocr_text") or "")
        confidence = payload.get("confidence", 1.0)
        image_available = False
    else:
        payload = request.form
        frame = request.files.get("frame")
        if frame is None:
            return jsonify({"ok": False, "error": "frame required"}), 400
        image = frame.read(2 * 1024 * 1024 + 1)
        if len(image) > 2 * 1024 * 1024:
            return jsonify({"ok": False, "error": "frame exceeds 2 MiB"}), 413
        text, confidence = ocr_title_image(image)
        image_available = bool(text)
    try:
        offset_ms = int(payload.get("offset_ms", 0))
        fragment_sequence = int(payload.get("fragment_sequence", 0))
        result = _get_playlist_service().observe(session_id, text, confidence, offset_ms, fragment_sequence)
    except (TypeError, ValueError, capture_errors.ValidationError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    result["ocrAvailable"] = image_available or app.testing
    return jsonify({"ok": True, **result})


@app.route("/api/capture/sessions/<session_id>/logical-videos", methods=["GET"])
def api_capture_logical_videos(session_id: str) -> Any:
    result = _get_playlist_service().list(session_id)
    return jsonify({"ok": True, **result})


@app.route("/api/capture/sessions/<session_id>/logical-videos/<logical_id>/<action>", methods=["POST"])
def api_capture_review_logical_video(session_id: str, logical_id: str, action: str) -> Any:
    payload = request.get_json(silent=True) or {}
    service = _get_playlist_service()
    if action == "confirm" and logical_id.startswith("review-"):
        result = service.confirm_candidate(session_id, logical_id)
    else:
        result = service.review(session_id, logical_id, action, payload)
    return jsonify({"ok": True, **result})


@app.route("/api/capture/sessions/<session_id>/crop", methods=["PUT"])
def api_capture_set_crop(session_id: str) -> Any:
    """Sets (or clears, with a `null`/absent crop) the session's normalized
    crop region. The crop is validated by `CropRegion` and persists in the
    session manifest — clearing never touches finalized media or source."""
    payload = request.get_json(silent=True) or {}
    try:
        crop = _parse_crop(payload.get("crop"))
    except capture_errors.ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    session = _get_capture_service().set_crop(session_id, crop)
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/capture/sessions/<session_id>/capture-metadata", methods=["PUT"])
def api_capture_set_metadata(session_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    metadata = payload.get("capture_metadata")
    if not isinstance(metadata, dict):
        return jsonify({"ok": False, "error": "capture_metadata must be an object"}), 400
    allowed = {
        "width", "height", "frameRate", "facingMode", "quality", "codec", "videoBitsPerSecond",
        "maxWidth", "maxHeight", "audioRequested", "micPermissionState", "cameraSwitches",
        "orientationChanges", "sourceWidth", "sourceHeight", "cropOutputWidth", "cropOutputHeight",
        "firstFragmentProbe", "captureStatus", "actualVideoStreams", "actualAudioStreams",
        "videoCodec", "audioCodec", "fps", "audioChannels", "audioSampleRate", "durationSec",
    }
    if any(key not in allowed for key in metadata):
        return jsonify({"ok": False, "error": "Unsupported capture metadata field"}), 400
    session = _get_capture_service().set_capture_metadata(session_id, metadata)
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/capture/sessions/<session_id>/source", methods=["PUT"])
def api_capture_set_source(session_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    source = payload.get("capture_source")
    if source not in {"environment", "user", "microphone"}:
        return jsonify({"ok": False, "error": "capture_source must be environment, user or microphone"}), 400
    session = _get_capture_service().set_capture_source(session_id, source)
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/capture/sessions/<session_id>/finalize", methods=["POST"])
def api_capture_finalize_session(session_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    session = _get_capture_service().finalize_session(
        session_id,
        recorded_at=payload.get("recorded_at") or None,
        ended_at=payload.get("ended_at") or None,
        reason=payload.get("reason") or None,
    )
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/capture/sessions/<session_id>/drain", methods=["POST"])
def api_capture_drain_session(session_id: str) -> Any:
    """W6 stop: force-finalize the partial tail, then finalize the session.

    Drains every remaining ACKed fragment into processing chunks (complete
    chunks first, then one partial tail), persists the fragment->chunk map,
    and only then closes the session. An assembly failure never drops
    fragments: the chunk stays retryable and the session still finalizes.
    """
    payload = request.get_json(silent=True) or {}
    service = _get_capture_service()
    try:
        service.drain_processing_chunks(session_id)
        session = service.finalize_session(
            session_id,
            recorded_at=payload.get("recorded_at") or None,
            ended_at=payload.get("ended_at") or None,
            reason=payload.get("reason") or None,
        )
        final_media = service.finalize_session_media(session_id)
    except (capture_errors.AssemblyError, capture_errors.InvalidTransitionError) as exc:
        return jsonify({"ok": False, "error": f"Capture finalization failed: {exc}"}), 422
    return jsonify(
        {
            "ok": True,
            "session": _session_payload(session),
            "finalMedia": final_media,
            "processingChunks": [
                entry.to_manifest() for entry in service.list_processing_chunks(session_id)
            ],
        }
    )


@app.route("/api/capture/sessions/<session_id>/processing-chunks", methods=["GET"])
def api_capture_list_processing_chunks(session_id: str) -> Any:
    """Observability read: durable fragment->processing-chunk map, in order."""
    entries = _get_capture_service().list_processing_chunks(session_id)
    return jsonify({"ok": True, "processingChunks": [e.to_manifest() for e in entries]})


@app.route("/api/capture/sessions/<session_id>/chunks/start", methods=["POST"])
def api_capture_start_chunk(session_id: str) -> Any:
    chunk = _get_capture_service().start_chunk(session_id)
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>/finalize", methods=["POST"])
def api_capture_finalize_chunk(session_id: str, index: int) -> Any:
    # Stream the request body straight to disk in bounded blocks — never
    # request.get_data()/full bytes — so a long chunk cannot exhaust memory.
    # The size limit mirrors Flask's MAX_CONTENT_LENGTH (which no longer
    # applies automatically once the body is read from request.stream).
    max_bytes = app.config.get("MAX_CONTENT_LENGTH") or (SETTINGS.upload_max_mb * 1024 * 1024)
    extension = request.headers.get("X-Media-Extension", ".webm")
    try:
        audio_availability = _parse_audio_availability(request.headers.get("X-Audio-Availability"))
    except capture_errors.ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    chunk = _get_capture_service().finalize_chunk_stream(
        session_id, index, request.stream, media_extension=extension,
        audio_availability=audio_availability,
        recorded_at=request.args.get("recorded_at") or None,
        max_bytes=max_bytes,
    )
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>/cancel-upload", methods=["POST"])
def api_capture_cancel_upload(session_id: str, index: int) -> Any:
    chunk = _get_capture_service().cancel_upload(session_id, index)
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>/retry-upload", methods=["POST"])
def api_capture_retry_upload(session_id: str, index: int) -> Any:
    chunk = _get_capture_service().retry_cancelled_upload(session_id, index)
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>/cancel-processing", methods=["POST"])
def api_capture_cancel_processing(session_id: str, index: int) -> Any:
    chunk = _get_capture_service().cancel_processing(session_id, index)
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/cancel-processing", methods=["POST"])
def api_capture_cancel_session_processing(session_id: str) -> Any:
    service = _get_capture_service()
    session = service.get_session(session_id)
    for chunk in session.chunks:
        if chunk.state in {capture_models.ChunkState.FINALIZED, capture_models.ChunkState.PROCESSING,
                           capture_models.ChunkState.CANCEL_REQUESTED}:
            service.cancel_processing(session_id, chunk.index)
    return jsonify({"ok": True, "session": _session_payload(service.get_session(session_id))})


@app.route("/api/capture/sessions/<session_id>/retry-processing", methods=["POST"])
def api_capture_retry_session_processing(session_id: str) -> Any:
    service = _get_capture_service()
    session = service.get_session(session_id)
    for chunk in session.chunks:
        if chunk.state is capture_models.ChunkState.CANCELLED:
            service.retry_cancelled_processing(session_id, chunk.index)
        elif chunk.state is capture_models.ChunkState.FAILED:
            service.mark_processing(session_id, chunk.index)
    return jsonify({"ok": True, "session": _session_payload(service.get_session(session_id))})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>/retry-processing", methods=["POST"])
def api_capture_retry_processing(session_id: str, index: int) -> Any:
    service = _get_capture_service()
    current = service.store.load_session(session_id).get_chunk(index)
    chunk = (
        service.retry_cancelled_processing(session_id, index)
        if current.state is capture_models.ChunkState.CANCELLED
        else service.mark_processing(session_id, index)
        if current.state is capture_models.ChunkState.FAILED
        else current
    )
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>", methods=["DELETE"])
def api_capture_delete_cancelled_chunk(session_id: str, index: int) -> Any:
    payload = request.get_json(silent=True) or {}
    chunk = _get_capture_service().delete_cancelled_chunk(
        session_id, index, confirmed=payload.get("confirm") is True
    )
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/chunks/<int:index>/detect-audio", methods=["POST"])
def api_capture_detect_chunk_audio(session_id: str, index: int) -> Any:
    """W7: server-side ffprobe detection of a finalized chunk's audio stream.

    Re-probes the persisted media and records AUDIO_MISSING / TRANSCRIPT_REQUIRED
    (or AVAILABLE) on the chunk. Probe failure is non-fatal — it leaves the
    state UNKNOWN and still returns 200 — so documentation never fails because
    audio is absent.
    """
    chunk = _get_capture_service().detect_chunk_audio(session_id, index)
    return jsonify({"ok": True, "chunk": chunk.to_manifest()})


@app.route("/api/capture/sessions/<session_id>/transcript", methods=["POST"])
def api_capture_associate_transcript(session_id: str) -> Any:
    """W8: associate a late, loosely-aligned transcript with a session.

    The transcript is stored as one opaque text block (with only its arrival
    time) — no per-second alignment is ever fabricated. Supplying it marks the
    session/chunks transcript-available and clears TRANSCRIPT_REQUIRED without
    changing any chunk's processing state. Mutating, so the local dashboard
    token is required by `_enforce_local_only`.
    """
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"ok": False, "error": "text required"}), 400
    language = payload.get("language")
    if language is not None and (not isinstance(language, str) or not language.strip()):
        return jsonify({"ok": False, "error": "language must be a non-empty string or omitted"}), 400
    session = _get_capture_service().associate_transcript(
        session_id, text, language=language or None
    )
    return jsonify({"ok": True, "session": _session_payload(session)})


@app.route("/api/metrics")
def api_metrics() -> Any:
    """Operational summary metrics (US-001 §3.3) — replaces implementation-
    centric folder counts as the dashboard's headline numbers. Derived from
    processed_files.json (status) and each output's *_metadata.json
    (duration, processing_time); never fabricated."""
    SUCCESS_STATUSES = {"completed", "completed_routed", "auto_detected", "existing_transcription"}
    FAILURE_STATUSES = {"failed_routed"}

    files_processed = 0
    files_failed = 0
    if PROCESSED_DB.exists():
        try:
            db = json.loads(PROCESSED_DB.read_text(encoding="utf-8"))
            seen_hashes: set[str] = set()
            for entry in db.values():
                dedup_key = entry.get("hash") or entry.get("path", "")
                if dedup_key in seen_hashes:
                    continue
                seen_hashes.add(dedup_key)
                status = entry.get("status", "")
                if status in SUCCESS_STATUSES:
                    files_processed += 1
                elif status in FAILURE_STATUSES:
                    files_failed += 1
        except Exception as e:
            logger.warning("[METRICS] Error reading processed_files.json: %s", e)

    total_duration = 0.0
    total_processing_time = 0.0
    metadata_count = 0
    if TRANSCRIPTIONS_BASE.exists():
        for meta_path in TRANSCRIPTIONS_BASE.rglob("*_metadata.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            total_duration += float(meta.get("duration", 0) or 0)
            total_processing_time += float(meta.get("processing_time", 0) or 0)
            metadata_count += 1

    total_attempts = files_processed + files_failed
    success_rate = (files_processed / total_attempts * 100) if total_attempts else None
    avg_processing_time = (total_processing_time / metadata_count) if metadata_count else None

    return jsonify({
        "files_processed": files_processed,
        "files_failed": files_failed,
        "duration_processed_seconds": total_duration,
        "duration_processed_formatted": _format_duration(total_duration),
        "success_rate_pct": round(success_rate, 1) if success_rate is not None else None,
        "avg_processing_time_seconds": round(avg_processing_time, 1) if avg_processing_time is not None else None,
    })


# ── Pipeline runner ─────────────────────────────────────────────────────
class _ProcessingCancelled(Exception):
    pass


def _run_pipeline(mode: str, *, cancel_check=lambda: False) -> None:
    global _run_state
    logger.info("[RUN] Starting pipeline mode=%s", mode)

    def append_log(msg: str) -> None:
        _run_state["log_tail"] += f"{msg}\n"
        stage = _infer_stage(_run_state["log_tail"])
        if stage:
            _run_state["stage"] = stage

    def run_streaming(cmd: list[str]) -> int:
        """Runs `cmd`, appending each line to log_tail (and re-inferring
        stage) as it arrives, instead of blocking until the whole subprocess
        exits — a long transcription run would otherwise leave the dashboard
        showing a stale log/stage for its entire duration."""
        process = subprocess.Popen(
            # Commands are `python -m <module>`: module resolution goes
            # through the installed package / inherited environment
            # (PYTHONPATH), not cwd. Streaming flags stay unchanged.
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="ignore", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            if cancel_check():
                process.terminate()
                process.wait(timeout=10)
                raise _ProcessingCancelled("Processing cancelled by request")
            append_log(line.rstrip("\n"))
        process.wait()
        return process.returncode

    try:
        if mode in ("full", "compress"):
            if cancel_check():
                raise _ProcessingCancelled("Processing cancelled by request")
            append_log("STEP 1: Compressing videos...")
            returncode = run_streaming([sys.executable, "-m", "transcript_pipeline.media.compressor"])
            if returncode != 0:
                append_log(f"transcript_pipeline.media.compressor exited with code {returncode}")

        if mode in ("full", "transcribe"):
            if cancel_check():
                raise _ProcessingCancelled("Processing cancelled by request")
            append_log("STEP 2: Organization + transcription...")
            returncode = run_streaming([sys.executable, "-m", "transcript_pipeline.pipeline.master"])
            if returncode != 0:
                raise RuntimeError(f"transcript_pipeline.pipeline.master failed (exit code {returncode})")

        append_log("PROCESS FINISHED")
        _mark_all_reached_completed()
    except _ProcessingCancelled as e:
        logger.info("[RUN] %s", e)
        _run_state["error"] = None
        _run_state["log_tail"] += f"{e}\n"
    except Exception as e:
        logger.error("[RUN] Error: %s", e)
        _run_state["error"] = str(e)
        append_log(f"ERROR: {e}")
        _mark_failed_stage()
    finally:
        _run_state["running"] = False
        _run_state["finished_at"] = datetime.now().isoformat()


def _mark_all_reached_completed() -> None:
    """On a clean finish, every stage the run actually reached becomes
    "completed" (the furthest stage was left "running" by _infer_stage)."""
    stages = _run_state.setdefault("stages", _fresh_stages())
    for name in PIPELINE_STAGES:
        entry = stages.setdefault(name, {"status": "pending", "progress": None})
        if entry["status"] == "running":
            entry["status"] = "completed"


def _mark_failed_stage() -> None:
    """Localizes a run failure to the stage that was running when the error
    occurred: that stage becomes "failed", later stages stay "pending"."""
    stages = _run_state.setdefault("stages", _fresh_stages())
    for name in PIPELINE_STAGES:
        entry = stages.setdefault(name, {"status": "pending", "progress": None})
        if entry["status"] == "running":
            entry["status"] = "failed"


def main() -> None:
    # Mobile/LAN mode (W25) is an explicit opt-in (ZMI_LAN_ACCESS=true). While
    # it is off, dashboard_host is guaranteed loopback-only here, or 0.0.0.0
    # when ZMI_CONTAINER_MODE=true (container-internal bind; Compose publishes
    # the port on host loopback only). With LAN mode on, the owner asked for
    # same-Wi-Fi access, so the server binds all interfaces — the Host/Origin
    # allowlist and shared dashboard token still apply to every request.
    _ensure_folders()
    _get_processing_worker().start()
    host = "0.0.0.0" if SETTINGS.lan_access else SETTINGS.dashboard_host
    ssl_context = None
    if SETTINGS.dashboard_cert_file and SETTINGS.dashboard_key_file:
        ssl_context = (str(SETTINGS.dashboard_cert_file), str(SETTINGS.dashboard_key_file))
    # threaded=True: single-threaded serving repeatedly stalled unrelated
    # requests behind a still-open media stream or the browser's own
    # background polling (/api/status, /api/logs every 3s) — reproduced
    # while E2E-testing the DOCS review UI. Local single-user dashboard, no
    # locking on shared JSON files today, but writes are infrequent/
    # user-driven (edit/delete/upload) — the concurrency risk is far smaller
    # than a dev server that can stall client requests indefinitely.
    app.run(
        host=host,
        port=SETTINGS.dashboard_port,
        debug=False,
        threaded=True,
        ssl_context=ssl_context,
    )


if __name__ == "__main__":
    main()
