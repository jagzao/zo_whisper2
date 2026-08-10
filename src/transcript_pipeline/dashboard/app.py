#!/usr/bin/env python3
"""
Dashboard UI to control the transcription pipeline.

Features:
- Displays input/output folders.
- Shows the audio/video file -> transcription relationship.
- Drop area to upload files to Video_compress/ with a project prefix.
- Project CRUD (projects.json).
- RUN button to execute compress_and_move + master_processor.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

from transcript_pipeline.config import PROJECT_ROOT, load_env

load_env()

ROOT = PROJECT_ROOT
VIDEO_COMPRESS = ROOT / "Video_compress"
AUDIO_BASE = ROOT / "audio"
VIDEOS_BASE = ROOT / "Videos"
TRANSCRIPTIONS_BASE = ROOT / "CarpetaTranscripciones"
PROJECTS_PATH = ROOT / "projects.json"
PROCESSED_DB = ROOT / "processed_files.json"

SUPPORTED_MEDIA = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "dashboard.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")

# ── Global run state ─────────────────────────────────────────────────────
_run_state: dict[str, Any] = {
    "running": False,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "log_tail": "",
}


def _python_exe() -> str:
    """Resolves which Python interpreter to use, same logic as RUN_MAX_QUALITY.bat."""
    candidates = [
        ROOT / "watcher" / "venv" / "Scripts" / "python.exe",
        Path(r"C:\ProgramData\miniconda3\python.exe"),
        Path.home() / "miniconda3" / "python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "python"


PYTHON_EXE = _python_exe()


# ── File helpers ──────────────────────────────────────────────────────────
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
        PROJECTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
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
            output_folder = TRANSCRIPTIONS_BASE

    candidates = [
        output_folder / f"{media_path.stem}.txt",
        output_folder / f"{media_path.stem}_timestamps.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            segments_path = candidate.parent / f"{media_path.stem}_segments.json"
            metadata_path = candidate.parent / f"{media_path.stem}_metadata.json"
            return {
                "path": str(candidate),
                "segments_path": str(segments_path) if segments_path.exists() else None,
                "metadata_path": str(metadata_path) if metadata_path.exists() else None,
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
            frame["url"] = f"/frame/{output_folder.relative_to(ROOT).as_posix()}/{media_path.stem}_Frames/{media_path.stem}/{frame['frame_file']}"
        return {
            "folder": str(frames_parent),
            "mapping": data,
            "frames": frames,
            "count": len(frames),
        }
    except Exception as e:
        logger.warning("[FRAMES] Error reading mapping: %s", e)
        return None


# ── Endpoints ────────────────────────────────────────────────────────────
@app.route("/")
def index() -> str:
    return render_template("dashboard.html")


@app.route("/api/status")
def api_status() -> dict:
    return jsonify(_run_state)


@app.route("/api/folders")
def api_folders() -> dict:
    _ensure_folders()
    return jsonify(
        {
            "folders": [
                {
                    "name": "Video_compress",
                    "path": str(VIDEO_COMPRESS),
                    "count": _count_files(VIDEO_COMPRESS, SUPPORTED_MEDIA, recursive=False),
                },
                {
                    "name": "Videos",
                    "path": str(VIDEOS_BASE),
                    "count": _count_files(VIDEOS_BASE, SUPPORTED_MEDIA),
                },
                {
                    "name": "audio",
                    "path": str(AUDIO_BASE),
                    "count": _count_files(AUDIO_BASE, SUPPORTED_MEDIA),
                },
                {
                    "name": "CarpetaTranscripciones",
                    "path": str(TRANSCRIPTIONS_BASE),
                    "count": _count_files(TRANSCRIPTIONS_BASE, {".txt"}),
                },
            ]
        }
    )


@app.route("/api/files")
def api_files() -> dict:
    _ensure_folders()
    media_files: list[dict] = []

    for base in (VIDEOS_BASE, AUDIO_BASE):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_MEDIA:
                continue
            transcription = _resolve_transcription(path)
            project = _find_matching_project(path.name)
            media_files.append(
                {
                    "path": str(path),
                    "relative": str(path.relative_to(ROOT)),
                    "name": path.name,
                    "size": path.stat().st_size,
                    "status": _file_status(path),
                    "language": _detect_language(path.name, project),
                    "project": project.get("name") if project else None,
            "transcription": transcription,
            "frames": _resolve_frames(path),
        }
    )

    media_files.sort(key=lambda x: x["name"].lower())
    return jsonify({"files": media_files})


@app.route("/api/projects")
def api_projects() -> dict:
    return jsonify({"projects": _load_projects()})


@app.route("/api/projects", methods=["POST"])
def api_projects_update() -> dict:
    payload = request.get_json(force=True) or {}
    action = payload.get("action")
    projects = _load_projects()

    if action == "create":
        new_project = payload.get("project")
        if not new_project or not new_project.get("name"):
            return jsonify({"ok": False, "error": "Project name required"}), 400
        if any(p["name"] == new_project["name"] for p in projects):
            return jsonify({"ok": False, "error": "Project already exists"}), 400
        projects.append(new_project)

    elif action == "update":
        name = payload.get("name")
        updated = payload.get("project")
        if not name or not updated:
            return jsonify({"ok": False, "error": "Incomplete data"}), 400
        projects = [updated if p["name"] == name else p for p in projects]

    elif action == "delete":
        name = payload.get("name")
        projects = [p for p in projects if p["name"] != name]

    else:
        return jsonify({"ok": False, "error": "Unknown action"}), 400

    if _save_projects(projects):
        return jsonify({"ok": True, "projects": projects})
    return jsonify({"ok": False, "error": "Could not save projects.json"}), 500


@app.route("/api/upload", methods=["POST"])
def api_upload() -> dict:
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file sent"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400

    project_id = request.form.get("project", "").strip()
    filename = Path(file.filename).name
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

    VIDEO_COMPRESS.mkdir(parents=True, exist_ok=True)
    destination = VIDEO_COMPRESS / filename
    counter = 1
    stem = destination.stem
    suffix = destination.suffix
    while destination.exists():
        destination = VIDEO_COMPRESS / f"{stem}_{counter:02d}{suffix}"
        counter += 1

    try:
        file.save(str(destination))
        logger.info("[UPLOAD] %s → %s", filename, destination)
        return jsonify({"ok": True, "path": str(destination), "name": destination.name})
    except Exception as e:
        logger.error("[UPLOAD] Error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/run/<mode>", methods=["POST"])
def api_run(mode: str) -> dict:
    global _run_state
    if _run_state["running"]:
        return jsonify({"ok": False, "error": "A run is already in progress"}), 409

    if mode not in ("full", "compress", "transcribe"):
        return jsonify({"ok": False, "error": "Invalid mode"}), 400

    _run_state.update(
        {
            "running": True,
            "mode": mode,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
            "log_tail": "",
        }
    )
    threading.Thread(target=_run_pipeline, args=(mode,), daemon=True).start()
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/logs")
def api_logs() -> dict:
    lines: list[str] = []
    for log_file in ("dashboard.log", "master_process.log", "simple_scan.log"):
        path = ROOT / log_file
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                lines.extend([f"[{log_file}] {line}" for line in text.splitlines()[-200:]])
            except Exception:
                pass
    lines = lines[-300:]
    return jsonify({"logs": lines})


@app.route("/api/transcription")
def api_transcription() -> dict:
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return jsonify({"ok": False, "error": "Transcription not found"}), 404
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        folder = Path(path).parent
        stem = Path(path).stem
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
            "metadata": metadata,
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
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/stream/<path:filename>")
def stream_media(filename: str) -> Any:
    """Serves audio/video files under Videos/ or audio/ for the player."""
    safe_path = filename.replace("/", os.sep).replace("\\", os.sep)
    target = ROOT / safe_path
    target_resolved = target.resolve()
    root_resolved = ROOT.resolve()
    if not str(target_resolved).startswith(str(root_resolved)) or not target.exists():
        return jsonify({"ok": False, "error": "Not found"}), 404
    return send_from_directory(str(target.parent), target.name)


@app.route("/api/transcription", methods=["POST"])
def api_transcription_save() -> dict:
    payload = request.get_json(force=True) or {}
    path = payload.get("path", "")
    text = payload.get("text", "")
    if not path or not Path(path).exists():
        return jsonify({"ok": False, "error": "Transcription not found"}), 404
    try:
        Path(path).write_text(text, encoding="utf-8")
        # Update text inside segments.json if it exists
        segments_path = Path(path).parent / f"{Path(path).stem}_segments.json"
        if segments_path.exists():
            try:
                data = json.loads(segments_path.read_text(encoding="utf-8"))
                data["text"] = text
                segments_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/file", methods=["DELETE"])
def api_delete_file() -> dict:
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400
    target = Path(path)
    if not target.exists() or not str(target.resolve()).startswith(str(ROOT.resolve())):
        return jsonify({"ok": False, "error": "File not found or not allowed"}), 404
    try:
        transcription = _resolve_transcription(target)
        target.unlink()
        if transcription:
            tx_folder = Path(transcription["path"]).parent
            stem = target.stem
            for child in tx_folder.iterdir():
                if child.is_file() and child.stem.startswith(stem):
                    try:
                        child.unlink()
                    except Exception as e:
                        logger.warning("[DELETE] Could not delete %s: %s", child, e)
        # Clean up processed_files.json
        try:
            if PROCESSED_DB.exists():
                db = json.loads(PROCESSED_DB.read_text(encoding="utf-8"))
                keys = [k for k, v in db.items() if v.get("path") == str(target.absolute()) or v.get("name") == target.name]
                for k in keys:
                    del db[k]
                PROCESSED_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("[DELETE] Could not clean up DB: %s", e)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/frames")
def api_frames() -> dict:
    path = request.args.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "Path required"}), 400
    target = Path(path)
    if not target.exists() or not str(target.resolve()).startswith(str(ROOT.resolve())):
        return jsonify({"ok": False, "error": "File not found"}), 404
    info = _resolve_frames(target)
    if not info:
        return jsonify({"ok": False, "error": "No frames available"}), 404
    return jsonify({"ok": True, **info})


@app.route("/frame/<path:filename>")
def serve_frame(filename: str) -> Any:
    """Serves frame images under CarpetaTranscripciones/."""
    safe_path = filename.replace("/", os.sep).replace("\\", os.sep)
    target = TRANSCRIPTIONS_BASE / safe_path
    target_resolved = target.resolve()
    root_resolved = ROOT.resolve()
    if not str(target_resolved).startswith(str(root_resolved)) or not target.exists():
        return jsonify({"ok": False, "error": "Frame not found"}), 404
    return send_from_directory(str(target.parent), target.name)


# ── Pipeline runner ─────────────────────────────────────────────────────
def _run_pipeline(mode: str) -> None:
    global _run_state
    logger.info("[RUN] Starting pipeline mode=%s", mode)

    def append_log(msg: str) -> None:
        _run_state["log_tail"] += f"{msg}\n"

    try:
        if mode in ("full", "compress"):
            append_log("STEP 1: Compressing videos...")
            result = subprocess.run(
                [PYTHON_EXE, "compress_and_move.py"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            append_log(result.stdout)
            if result.returncode != 0:
                append_log(result.stderr)

        if mode in ("full", "transcribe"):
            append_log("STEP 2: Organization + transcription...")
            result = subprocess.run(
                [PYTHON_EXE, "master_processor.py"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            append_log(result.stdout)
            if result.returncode != 0:
                append_log(result.stderr)
                raise RuntimeError("master_processor.py failed")

        append_log("PROCESS FINISHED")
    except Exception as e:
        logger.error("[RUN] Error: %s", e)
        _run_state["error"] = str(e)
        append_log(f"ERROR: {e}")
    finally:
        _run_state["running"] = False
        _run_state["finished_at"] = datetime.now().isoformat()


def main() -> None:
    _ensure_folders()
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
