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

import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

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
from transcript_pipeline.logging_setup import configure_logging
from transcript_pipeline.media.utils import run_ffprobe
from transcript_pipeline.projects import validate_project
from transcript_pipeline.security import (
    MediaRoot,
    PathNotFoundError,
    PathTraversalError,
    SafePathResolver,
    SecurityError,
)
from transcript_pipeline.settings import SETTINGS
from transcript_pipeline.dashboard.queue_store import QueueStore

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
UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024
_upload_sessions_lock = threading.Lock()

RUN_ID = configure_logging("dashboard.log")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = SETTINGS.upload_max_mb * 1024 * 1024

# Host and Origin checks allow loopback plus explicitly configured LAN hosts.
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"} | {
    host.strip().lower()
    for host in os.environ.get("DASHBOARD_ALLOWED_HOSTS", "").split(",")
    if host.strip()
}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Generated fresh per process, never persisted, never logged — the frontend
# reads it from the page it was served (see index()) and echoes it back on
# every mutating request via X-Local-Dashboard-Token.
_DASHBOARD_TOKEN = secrets.token_urlsafe(32)

# media_ids currently being documented (in-memory concurrency guard so a
# second "Generate Documentation" for the same video is rejected, not queued).
_doc_generation_lock = threading.Lock()
_doc_generation_inflight: set[str] = set()


def _hostname_only(host_header: str) -> str:
    """Strips the port from a Host/Origin-style host, IPv6-bracket aware."""
    host_header = host_header.strip().lower()
    if host_header.startswith("["):
        return host_header.split("]")[0].lstrip("[")
    if host_header.count(":") == 1:
        return host_header.rsplit(":", 1)[0]
    return host_header


@app.before_request
def _enforce_local_only() -> Any:
    host = _hostname_only(request.host or "")
    if host not in _LOCAL_HOSTNAMES:
        logger.warning("[SECURITY] Rejected request with non-local Host: %s", request.host)
        return jsonify({"ok": False, "error": "Forbidden"}), 403

    if request.method in _MUTATING_METHODS:
        origin = request.headers.get("Origin")
        if origin and (urlparse(origin).hostname or "").lower() not in _LOCAL_HOSTNAMES:
            logger.warning("[SECURITY] Rejected %s with non-local Origin: %s", request.method, origin)
            return jsonify({"ok": False, "error": "Forbidden"}), 403

        token = request.headers.get("X-Local-Dashboard-Token", "")
        if not secrets.compare_digest(token, _DASHBOARD_TOKEN):
            logger.warning("[SECURITY] Rejected %s with missing/invalid dashboard token", request.method)
            return jsonify({"ok": False, "error": "Forbidden"}), 403

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


# ── Global run state ─────────────────────────────────────────────────────
_run_lock = threading.Lock()
_queue_worker_active = False
_run_state: dict[str, Any] = {
    "running": False,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "log_tail": "",
    "stage": None,
    "stages": {},
    "queued": False,
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
        return "pending"
    except Exception:
        return "pending"


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
            project, _ = _effective_project(
                _to_media_id(MediaRoot.VIDEO_COMPRESS, media_path), media_path.name
            )
            subfolder = project.get("videos_subfolder") if project else None
            output_folder = TRANSCRIPTIONS_BASE
            if isinstance(subfolder, str) and subfolder.strip():
                candidate = (TRANSCRIPTIONS_BASE / subfolder).resolve()
                root = TRANSCRIPTIONS_BASE.resolve()
                if root in candidate.parents:
                    output_folder = candidate

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
    (kept cheap since this runs once per row in `/api/files`)."""
    frames_parent = _documentation_dirs(media_path)
    if frames_parent is None:
        return None
    manual_meta = frames_parent / "manual" / "metadata.json"
    ai_manifest = frames_parent / "ai-package" / "manifest.json"
    has_manual = manual_meta.exists()
    has_ai_package = ai_manifest.exists()
    if not has_manual and not has_ai_package:
        return None
    return {
        "has_manual": has_manual,
        "has_ai_package": has_ai_package,
        "media_id": _to_media_id(root, media_path),
    }


def _frame_media_url(frames_parent: Path, relative_to_frames_parent: str) -> str:
    """URL for a raw frame file (relative to frames_parent, where
    KeyframeExtractor wrote it — NOT manual_dir, whose assets/ only holds
    copies made for MANUAL.md/ai-package)."""
    frame_id = _to_media_id(MediaRoot.TRANSCRIPTIONS, frames_parent / relative_to_frames_parent)
    return f"/doc-asset?id={quote(frame_id, safe='')}"


# ── Endpoints ────────────────────────────────────────────────────────────
@app.route("/")
def index() -> str:
    return render_template("dashboard.html", dashboard_token=_DASHBOARD_TOKEN)


@app.route("/api/status")
def api_status() -> Any:
    return jsonify({**_run_state, "queue": _queue_store().snapshot()})


@app.route("/api/events")
def api_events() -> Any:
    try:
        after = max(0, int(request.args.get("after", "0")))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid event cursor"}), 400
    return jsonify({"events": _queue_store().events_after(after)})


def _queue_store() -> QueueStore:
    return QueueStore(ROOT / "processing_queue.sqlite3")


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

    for base, root in (
        (VIDEO_COMPRESS, MediaRoot.VIDEO_COMPRESS),
        (VIDEOS_BASE, MediaRoot.VIDEOS),
        (AUDIO_BASE, MediaRoot.AUDIO),
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_MEDIA:
                continue
            transcription = _resolve_transcription(path)
            media_id = _to_media_id(root, path)
            project, project_source = _effective_project(media_id, path.name)
            if project is None and root == MediaRoot.VIDEOS:
                project = next(
                    (
                        candidate
                        for candidate in _load_projects()
                        if any(
                            folder.lower() in str(path.parent).lower()
                            for folder in candidate.get("match", {}).get("folder_contains", [])
                        )
                    ),
                    None,
                )
                if project:
                    project_source = "auto"
            media_files.append(
                {
                    "media_id": media_id,
                    "relative": str(path.relative_to(ROOT)),
                    "name": path.name,
                    "size": path.stat().st_size,
                    "status": _file_status(path),
                    "language": _detect_language(path.name, project),
                    "project": project.get("name") if project else None,
                    "project_source": project_source,
                    "transcription": transcription,
                    "documentation": _resolve_documentation(path, root),
                }
            )

    media_files.sort(key=lambda x: x["name"].lower())
    return jsonify({"files": media_files})


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
        if not isinstance(updated_name, str) or not updated_name:
            return jsonify({"ok": False, "error": "Project name is required"}), 400
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
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file sent"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400

    project_id = request.form.get("project", "").strip()
    filename = secure_filename(Path(file.filename).name)
    if not filename:
        return jsonify({"ok": False, "error": "Invalid filename"}), 400
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_MEDIA:
        return jsonify({"ok": False, "error": f"Unsupported format: {ext}"}), 400

    chosen_project = None
    if project_id:
        for project in _load_projects():
            if project.get("name") == project_id:
                chosen_project = project
                break

    # If the file has no recognizable prefix and a project was chosen, apply its first prefix
    if chosen_project:
        rules = chosen_project.get("match", {})
        prefixes = rules.get("prefix", [])
        if prefixes and not _find_matching_project(filename):
            prefix = prefixes[0]
            filename = f"{prefix}{filename}" if not filename.lower().startswith(prefix.lower()) else filename

    upload_id = uuid.uuid4().hex
    session_paths = _upload_session_paths(upload_id)
    assert session_paths is not None
    metadata_path, temp_path = session_paths
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with _upload_sessions_lock:
        filename = _available_upload_filename(filename)
        _write_upload_session(metadata_path, {
            "filename": filename,
            "project": project_id,
            "received": 0,
            "created_at": datetime.now().timestamp(),
        })
    try:
        file.save(str(temp_path))
        with temp_path.open("rb") as uploaded:
            os.fsync(uploaded.fileno())
    except Exception:
        temp_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        logger.exception("[UPLOAD] Error saving %s", filename)
        return jsonify({"ok": False, "error": "Could not process upload"}), 500

    if not _is_valid_media_file(temp_path):
        temp_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": "Uploaded file is not a valid media file"}), 400

    with _upload_sessions_lock:
        session = _read_upload_session(metadata_path) or {}
        session.update({
            "size": temp_path.stat().st_size,
            "received": temp_path.stat().st_size,
            "ready_for_processing": True,
        })
        _write_upload_session(metadata_path, session)
    _queue_store().record_event("upload_ready", {"upload_id": upload_id, "name": filename})

    logger.info("[UPLOAD] %s uploaded; waiting for processing approval", filename)
    return jsonify({"ok": True, "name": filename, "processing": "awaiting_approval", "upload_id": upload_id})


def _upload_session_paths(upload_id: str) -> tuple[Path, Path] | None:
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
        return None
    root = ROOT / ".upload_sessions"
    return root / f"{upload_id}.json", root / f"{upload_id}.part"


def _read_upload_session(metadata_path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_upload_session(metadata_path: Path, session: dict[str, Any]) -> None:
    temporary = metadata_path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(json.dumps(session))
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(metadata_path)


def _reconcile_upload_offset(metadata_path: Path, data_path: Path, session: dict[str, Any]) -> int:
    committed = max(0, min(int(session.get("received", 0)), int(session.get("size", 0))))
    actual = data_path.stat().st_size if data_path.exists() else 0
    recovered = min(committed, actual)
    if actual != recovered:
        with data_path.open("r+b") as output:
            output.truncate(recovered)
            output.flush()
            os.fsync(output.fileno())
    if recovered != session.get("received"):
        session["received"] = recovered
        _write_upload_session(metadata_path, session)
        _queue_store().record_event("upload_offset_recovered", {"upload_id": metadata_path.stem, "offset": recovered})
    return recovered


def _available_upload_filename(filename: str) -> str:
    root = VIDEO_COMPRESS if Path(filename).suffix.lower() in VIDEO_EXTS else AUDIO_BASE
    reserved = {path.name.lower() for path in root.iterdir() if path.is_file()} if root.exists() else set()
    sessions_root = ROOT / ".upload_sessions"
    for metadata_path in sessions_root.glob("*.json"):
        session = _read_upload_session(metadata_path)
        if session and not session.get("complete"):
            name = session.get("filename")
            if isinstance(name, str):
                reserved.add(name.lower())
    candidate = filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while candidate.lower() in reserved:
        candidate = f"{stem}_{counter:02d}{suffix}"
        counter += 1
    return candidate


@app.route("/api/upload-sessions", methods=["POST"])
def api_create_upload_session() -> Any:
    payload = request.get_json(silent=True) or {}
    original_name = payload.get("filename")
    size = payload.get("size")
    project_id = payload.get("project", "")
    if not isinstance(original_name, str) or not original_name.strip():
        return jsonify({"ok": False, "error": "Filename is required"}), 400
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return jsonify({"ok": False, "error": "Invalid file size"}), 400
    if size > app.config["MAX_CONTENT_LENGTH"]:
        return jsonify({"ok": False, "error": "File too large"}), 413

    filename = secure_filename(Path(original_name).name)
    ext = Path(filename).suffix.lower()
    if not filename or ext not in SUPPORTED_MEDIA:
        return jsonify({"ok": False, "error": f"Unsupported format: {ext}"}), 400

    chosen_project = next(
        (project for project in _load_projects() if project.get("name") == project_id), None
    ) if project_id else None
    if chosen_project:
        prefixes = chosen_project.get("match", {}).get("prefix", [])
        if prefixes and not _find_matching_project(filename):
            prefix = prefixes[0]
            if not filename.lower().startswith(prefix.lower()):
                filename = f"{prefix}{filename}"

    upload_id = uuid.uuid4().hex
    paths = _upload_session_paths(upload_id)
    assert paths is not None
    metadata_path, data_path = paths
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now().timestamp() - 7 * 24 * 60 * 60
    with _upload_sessions_lock:
        for expired in metadata_path.parent.glob("*.json"):
            try:
                if expired.stat().st_mtime < cutoff:
                    expired.with_suffix(".part").unlink(missing_ok=True)
                    expired.unlink(missing_ok=True)
            except OSError:
                logger.warning("[UPLOAD] Could not clean stale upload session %s", expired.name)
        filename = _available_upload_filename(filename)
        data_path.touch()
        _write_upload_session(metadata_path, {
            "filename": filename,
            "size": size,
            "project": project_id,
            "received": 0,
            "created_at": datetime.now().timestamp(),
        })
        _queue_store().record_event("upload_created", {"upload_id": upload_id, "name": filename, "size": size})
    logger.info("[UPLOAD] Started resumable upload %s (%s bytes)", upload_id, size)
    return jsonify({"ok": True, "upload_id": upload_id, "offset": 0, "chunk_size": UPLOAD_CHUNK_BYTES})


@app.route("/api/upload-sessions/<upload_id>", methods=["GET"])
def api_upload_session_status(upload_id: str) -> Any:
    if not secrets.compare_digest(
        request.headers.get("X-Local-Dashboard-Token", ""), _DASHBOARD_TOKEN
    ):
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    paths = _upload_session_paths(upload_id)
    if not paths:
        return jsonify({"ok": False, "error": "Upload session not found"}), 404
    metadata_path, data_path = paths
    with _upload_sessions_lock:
        session = _read_upload_session(metadata_path)
        if session and not session.get("complete") and not session.get("ready_for_processing"):
            _reconcile_upload_offset(metadata_path, data_path, session)
    if not session:
        return jsonify({"ok": False, "error": "Upload session not found"}), 404
    return jsonify({
        "ok": True,
        "offset": session.get("received", 0),
        "size": session.get("size", 0),
        "complete": session.get("complete", False),
        "ready_for_processing": session.get("ready_for_processing", False),
        "name": session.get("saved_name") or session.get("filename"),
    })


@app.route("/api/upload-sessions/<upload_id>", methods=["PUT"])
def api_upload_session_chunk(upload_id: str) -> Any:
    paths = _upload_session_paths(upload_id)
    if not paths:
        return jsonify({"ok": False, "error": "Upload session not found"}), 404
    metadata_path, data_path = paths
    content_range = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", request.headers.get("Content-Range", ""))
    if not content_range:
        return jsonify({"ok": False, "error": "Content-Range is required"}), 400
    start, end, total = map(int, content_range.groups())
    if request.content_length is None or request.content_length > UPLOAD_CHUNK_BYTES:
        return jsonify({"ok": False, "error": "Invalid upload chunk size"}), 413
    chunk = request.get_data(cache=False)
    if not chunk or len(chunk) != end - start + 1:
        return jsonify({"ok": False, "error": "Incomplete upload chunk"}), 400

    with _upload_sessions_lock:
        session = _read_upload_session(metadata_path)
        if not session:
            return jsonify({"ok": False, "error": "Upload session not found"}), 404
        received = _reconcile_upload_offset(metadata_path, data_path, session)
        if session.get("complete") or session.get("ready_for_processing"):
            return jsonify({"ok": False, "error": "Upload session is complete"}), 409
        if total != session.get("size") or start < 0 or end >= total:
            return jsonify({"ok": False, "error": "Upload range does not match file"}), 400
        if start < received and end < received:
            return jsonify({"ok": True, "offset": received})
        if start != received or len(chunk) > UPLOAD_CHUNK_BYTES:
            return jsonify({"ok": False, "error": "Upload offset mismatch", "offset": received}), 409
        try:
            with data_path.open("r+b") as output:
                output.seek(start)
                output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        except OSError:
            logger.exception("[UPLOAD] Failed writing resumable chunk %s", upload_id)
            return jsonify({"ok": False, "error": "Could not save upload chunk"}), 500
        session["received"] = end + 1
        _write_upload_session(metadata_path, session)
        return jsonify({"ok": True, "offset": end + 1})


@app.route("/api/upload-sessions/<upload_id>/complete", methods=["POST"])
def api_complete_upload_session(upload_id: str) -> Any:
    paths = _upload_session_paths(upload_id)
    if not paths:
        return jsonify({"ok": False, "error": "Upload session not found"}), 404
    metadata_path, data_path = paths
    with _upload_sessions_lock:
        session = _read_upload_session(metadata_path)
        if not session:
            return jsonify({"ok": False, "error": "Upload session not found"}), 404
        if session.get("complete"):
            return jsonify({"ok": True, "name": session["saved_name"], "processing": "queued", "upload_id": upload_id})
        if session.get("ready_for_processing"):
            return jsonify({"ok": True, "name": session["filename"], "processing": "awaiting_approval", "upload_id": upload_id})
        _reconcile_upload_offset(metadata_path, data_path, session)
        if session.get("received") != session.get("size") or not data_path.is_file():
            return jsonify({"ok": False, "error": "Upload is incomplete", "offset": session.get("received", 0)}), 409
        if data_path.stat().st_size != session["size"] or not _is_valid_media_file(data_path):
            data_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            return jsonify({"ok": False, "error": "Uploaded file is not a valid media file"}), 400

        filename = session["filename"]
        session["ready_for_processing"] = True
        _write_upload_session(metadata_path, session)
        _queue_store().record_event("upload_ready", {"upload_id": upload_id, "name": filename})
    logger.info("[UPLOAD] Completed resumable upload %s; awaiting processing approval", upload_id)
    return jsonify({"ok": True, "name": filename, "processing": "awaiting_approval", "upload_id": upload_id})


@app.route("/api/run/<mode>", methods=["POST"])
def api_run(mode: str) -> Any:
    if mode not in ("full", "compress", "transcribe"):
        return jsonify({"ok": False, "error": "Invalid mode"}), 400

    if mode == "full":
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "Invalid upload batch"}), 400
        upload_ids = payload.get("upload_ids")
        if upload_ids is not None and (
            not isinstance(upload_ids, list)
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value) for value in upload_ids)
        ):
            return jsonify({"ok": False, "error": "Invalid upload batch"}), 400
        _promote_ready_uploads(set(upload_ids) if upload_ids is not None else None)
    processing = _schedule_pipeline(mode)
    return jsonify({"ok": True, "mode": mode, "processing": processing})


def _prepare_pipeline_run(mode: str) -> None:
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
            "queued": False,
        }
    )


def _schedule_pipeline(mode: str) -> str:
    global _queue_worker_active
    with _run_lock:
        _, created = _queue_store().enqueue(mode)
        running = _queue_worker_active
        if not running:
            _queue_worker_active = True
            threading.Thread(target=_drain_pipeline_queue, daemon=True).start()
        else:
            _run_state["queued"] = True
    return "queued" if running or not created else "started"


def _drain_pipeline_queue() -> None:
    global _queue_worker_active
    store = _queue_store()
    while True:
        with _run_lock:
            claimed = store.claim()
            if claimed is None:
                _queue_worker_active = False
                _run_state["queued"] = False
                return
            job_id, mode = claimed
            _prepare_pipeline_run(mode)
        _run_pipeline(mode, job_id)


def _start_recovered_queue() -> None:
    global _queue_worker_active
    with _run_lock:
        if _queue_worker_active:
            return
        _queue_worker_active = True
        threading.Thread(target=_drain_pipeline_queue, daemon=True).start()


def _promote_ready_uploads(upload_ids: set[str] | None = None) -> list[str]:
    promoted: list[str] = []
    sessions_root = ROOT / ".upload_sessions"
    with _upload_sessions_lock:
        for metadata_path in sessions_root.glob("*.json"):
            if upload_ids is not None and metadata_path.stem not in upload_ids:
                continue
            session = _read_upload_session(metadata_path)
            if not session or session.get("complete"):
                continue
            data_path = metadata_path.with_suffix(".part")
            filename = session.get("saved_name") if session.get("promoting") else session.get("filename")
            if session.get("promoting") and isinstance(filename, str):
                destination_root = VIDEO_COMPRESS if Path(filename).suffix.lower() in VIDEO_EXTS else AUDIO_BASE
                destination = destination_root / filename
                if destination.is_file():
                    session["complete"] = True
                    session["ready_for_processing"] = False
                    _write_upload_session(metadata_path, session)
                    continue
            elif not session.get("ready_for_processing"):
                continue
            if not isinstance(filename, str) or not data_path.is_file():
                continue
            destination_root = VIDEO_COMPRESS if Path(filename).suffix.lower() in VIDEO_EXTS else AUDIO_BASE
            destination_root.mkdir(parents=True, exist_ok=True)
            destination = destination_root / filename
            stem, suffix = destination.stem, destination.suffix
            counter = 1
            while destination.exists():
                destination = destination_root / f"{stem}_{counter:02d}{suffix}"
                counter += 1
            session["promoting"] = True
            session["saved_name"] = destination.name
            _write_upload_session(metadata_path, session)
            try:
                data_path.replace(destination)
            except OSError:
                logger.exception("[UPLOAD] Could not queue %s for processing", filename)
                continue
            session["complete"] = True
            session["ready_for_processing"] = False
            session.pop("promoting", None)
            _write_upload_session(metadata_path, session)
            _queue_store().record_event("upload_approved", {"upload_id": metadata_path.stem, "name": destination.name})
            promoted.append(destination.name)
    return promoted


def _has_pending_media() -> bool:
    succeeded = {"completed", "completed_routed", "auto_detected", "existing_transcription", "processed"}
    roots = ((VIDEO_COMPRESS, False), (VIDEOS_BASE, True), (AUDIO_BASE, True))
    for folder, recursive in roots:
        if not folder.exists():
            continue
        candidates = folder.rglob("*") if recursive else folder.iterdir()
        if any(
            path.is_file()
            and path.suffix.lower() in SUPPORTED_MEDIA
            and _file_status(path) not in succeeded
            for path in candidates
        ):
            return True
    return False


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


@app.route("/api/transcription", methods=["POST"])
def api_transcription_save() -> Any:
    payload = request.get_json(force=True) or {}
    text = payload.get("text", "")
    resolved = _from_media_id(payload.get("id", ""), [MediaRoot.TRANSCRIPTIONS])

    media_id = str(payload.get("media_id") or "")
    filename = resolved.name
    override_project: str | None = None
    if media_id:
        media_target = _from_media_id(
            media_id,
            [MediaRoot.VIDEO_COMPRESS, MediaRoot.VIDEOS, MediaRoot.AUDIO],
            must_exist=False,
        )
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
    snapshots: dict[Path, tuple[bool, str]] = {
        resolved: _snapshot_text_file(resolved),
    }
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


@app.route("/api/file/project", methods=["POST"])
def api_file_project() -> Any:
    payload = request.get_json(force=True) or {}
    media_id = payload.get("media_id")
    raw_project = payload.get("project")
    if not isinstance(media_id, str) or not media_id:
        return jsonify({"ok": False, "error": "Media file is required"}), 400
    if raw_project is not None and not isinstance(raw_project, str):
        return jsonify({"ok": False, "error": "Invalid project"}), 400

    target = _from_media_id(
        media_id,
        [MediaRoot.VIDEO_COMPRESS, MediaRoot.VIDEOS, MediaRoot.AUDIO],
    )
    project_name = raw_project.strip() if raw_project else ""
    if project_name and not any(p.get("name") == project_name for p in _load_projects()):
        return jsonify({"ok": False, "error": f"Project not found: {project_name}"}), 400

    overrides_path = _project_overrides_path()
    snapshot = _snapshot_text_file(overrides_path)
    overrides = _load_project_overrides()
    if project_name:
        overrides[media_id] = project_name
    else:
        overrides.pop(media_id, None)
    if not _save_project_overrides(overrides):
        _restore_text_snapshot(overrides_path, snapshot)
        return jsonify({"ok": False, "error": "Could not save project assignment"}), 500

    effective, source = _effective_project(media_id, target.name)
    return jsonify({
        "ok": True,
        "project": effective.get("name") if effective else None,
        "project_source": source,
    })


@app.route("/api/file", methods=["DELETE"])
def api_delete_file() -> Any:
    deleted_id = request.args.get("id", "")
    target = _from_media_id(
        deleted_id,
        [MediaRoot.AUDIO, MediaRoot.VIDEOS, MediaRoot.VIDEO_COMPRESS, MediaRoot.TRANSCRIPTIONS],
    )

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
        target.unlink()
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
    if not info:
        return jsonify({"ok": False, "error": "No frames available"}), 404
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
def _run_pipeline(mode: str, job_id: int | None = None) -> None:
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
            append_log(line.rstrip("\n"))
        process.wait()
        return process.returncode

    try:
        if mode in ("full", "compress"):
            append_log("STEP 1: Compressing videos...")
            returncode = run_streaming([sys.executable, "-m", "transcript_pipeline.media.compressor"])
            if returncode != 0:
                raise RuntimeError(f"transcript_pipeline.media.compressor failed (exit code {returncode})")

        if mode in ("full", "transcribe"):
            append_log("STEP 2: Organization + transcription...")
            returncode = run_streaming([sys.executable, "-m", "transcript_pipeline.pipeline.master"])
            if returncode != 0:
                raise RuntimeError(f"transcript_pipeline.pipeline.master failed (exit code {returncode})")

        append_log("PROCESS FINISHED")
        _mark_all_reached_completed()
    except Exception as e:
        logger.error("[RUN] Error: %s", e)
        _run_state["error"] = str(e)
        append_log(f"ERROR: {e}")
        _mark_failed_stage()
    finally:
        if job_id is not None:
            _queue_store().finish(job_id, _run_state.get("error"))
        with _run_lock:
            _run_state["running"] = False
            _run_state["finished_at"] = datetime.now().isoformat()
            _run_state["queued"] = bool(_queue_store().snapshot()["counts"].get("queued", 0))


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
    # Container binding may use 0.0.0.0; Compose publishes only to the
    # trusted LAN, with request Host/Origin protections still enforced.
    _ensure_folders()
    _queue_store().recover()
    if _has_pending_media():
        logger.info("[RUN] Resuming pending media from data root")
        _schedule_pipeline("full")
    elif _queue_store().snapshot()["counts"].get("queued", 0):
        logger.info("[RUN] Resuming durable processing queue")
        _start_recovered_queue()
    # threaded=True: single-threaded serving repeatedly stalled unrelated
    # requests behind a still-open media stream or the browser's own
    # background polling (/api/status, /api/logs every 3s) — reproduced
    # while E2E-testing the DOCS review UI. Local single-user dashboard, no
    # locking on shared JSON files today, but writes are infrequent/
    # user-driven (edit/delete/upload) — the concurrency risk is far smaller
    # than a dev server that can stall client requests indefinitely.
    app.run(host=SETTINGS.dashboard_host, port=SETTINGS.dashboard_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
