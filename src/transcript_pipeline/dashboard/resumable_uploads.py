"""Persistent bounded-chunk upload sessions for the dashboard."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path
import shutil
from typing import Any

CHUNK_SIZE = 8 * 1024 * 1024
STORAGE_RESERVE_BYTES = 2 * 1024**3
_SESSION_ID = re.compile(r"^[a-f0-9]{32}$")
_ACK_LOCK = threading.Lock()
_FINALIZE_LOCK = threading.Lock()
_CREATE_LOCK = threading.Lock()


class UploadError(ValueError):
    """Invalid or inconsistent resumable upload request."""


class ResumableUploads:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def storage_preflight(self, uploads: list[dict[str, Any]]) -> dict[str, Any]:
        requested = 0
        excluded = set()
        for upload in uploads:
            session_id = upload.get("session_id")
            size = int(upload.get("size", 0))
            if size <= 0:
                raise UploadError("Invalid file size")
            if session_id:
                _, session = self._manifest(str(session_id))
                excluded.add(str(session_id))
                size = int(session.get("size", 0))
                acknowledged = sum(
                    min(CHUNK_SIZE, size - int(index) * CHUNK_SIZE)
                    for index in session.get("chunks", {})
                )
                requested += max(0, size - acknowledged)
            else:
                requested += size
        active = sum(
            max(0, int(session.get("size", 0)) - sum(
                min(CHUNK_SIZE, int(session.get("size", 0)) - int(index) * CHUNK_SIZE)
                for index in session.get("chunks", {})
            ))
            for session in self.list() if session.get("id") not in excluded
        )
        free = shutil.disk_usage(self.root.parent).free
        required = requested + active + STORAGE_RESERVE_BYTES
        return {"ok": free >= required, "free_bytes": free, "required_bytes": required,
                "remaining_upload_bytes": requested + active, "reserve_bytes": STORAGE_RESERVE_BYTES}

    def _dir(self, session_id: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id):
            raise UploadError("Invalid upload session")
        return self.root / session_id

    def _manifest(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        directory = self._dir(session_id)
        try:
            data = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UploadError("Upload session not found or corrupt") from exc
        return directory, data

    @staticmethod
    def _save(path: Path, data: dict[str, Any]) -> None:
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".session-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise

    def create(self, filename: str, size: int, project_id: str = "") -> dict[str, Any]:
        if not filename or Path(filename).name != filename or size <= 0:
            raise UploadError("Invalid filename or file size")
        with _CREATE_LOCK:
            check = self.storage_preflight([{"size": size}])
            if not check["ok"]:
                raise UploadError(self.insufficient_storage_message(check))
            session_id = uuid.uuid4().hex
            directory = self._dir(session_id)
            directory.mkdir()
            data = {"id": session_id, "filename": filename, "size": size, "project_id": project_id,
                    "chunk_size": CHUNK_SIZE, "chunks": {}, "state": "UPLOADING"}
            self._save(directory / "session.json", data)
            return data

    @staticmethod
    def insufficient_storage_message(check: dict[str, Any]) -> str:
        gib = 1024**3
        return f"Insufficient storage: {check['free_bytes'] / gib:.1f} GiB free, {check['required_bytes'] / gib:.1f} GiB required. Free space before uploading."

    def list(self) -> list[dict[str, Any]]:
        sessions = []
        for path in self.root.iterdir():
            if path.is_dir():
                try:
                    _, data = self._manifest(path.name)
                    if data.get("state") in {"UPLOADING", "FINALIZING"}:
                        sessions.append(data)
                except UploadError:
                    continue
        return sessions

    def acknowledge(self, session_id: str, index: int, body: bytes, digest: str) -> dict[str, Any]:
        with _ACK_LOCK:
            return self._acknowledge(session_id, index, body, digest)

    def _acknowledge(self, session_id: str, index: int, body: bytes, digest: str) -> dict[str, Any]:
        directory, data = self._manifest(session_id)
        if data["state"] != "UPLOADING" or index < 0:
            raise UploadError("Upload session is not accepting chunks")
        check = self.storage_preflight([{"session_id": session_id, "size": data["size"]}])
        if not check["ok"]:
            raise UploadError(self.insufficient_storage_message(check))
        expected_count = (data["size"] + CHUNK_SIZE - 1) // CHUNK_SIZE
        if index >= expected_count:
            raise UploadError("Chunk index is outside the file")
        expected_size = min(CHUNK_SIZE, data["size"] - index * CHUNK_SIZE)
        if len(body) > CHUNK_SIZE:
            raise UploadError("Chunk exceeds the configured chunk size")
        actual = hashlib.sha256(body).hexdigest()
        if len(body) != expected_size or actual != digest:
            raise UploadError("Chunk size or SHA-256 does not match")
        old = data["chunks"].get(str(index))
        if old and old != actual:
            raise UploadError("Chunk conflicts with an acknowledged chunk")
        if not old:
            part = directory / f"{index:08d}.part"
            if part.exists():
                existing = hashlib.sha256(part.read_bytes()).hexdigest()
                if existing != actual:
                    part.unlink()
            if not part.exists():
                temporary = directory / f"{index:08d}.{uuid.uuid4().hex}.tmp"
                with temporary.open("xb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, part)
            data["chunks"][str(index)] = actual
            self._save(directory / "session.json", data)
        return {"ok": True, "index": index, "sha256": actual, "received": sorted(map(int, data["chunks"]))}

    def finalize(self, session_id: str, destination: Path, validate_media) -> dict[str, Any]:
        with _FINALIZE_LOCK:
            return self._finalize(session_id, destination, validate_media)

    def _finalize(self, session_id: str, destination: Path, validate_media) -> dict[str, Any]:
        directory, data = self._manifest(session_id)
        if data.get("state") == "COMPLETED":
            return data
        expected_count = (data["size"] + CHUNK_SIZE - 1) // CHUNK_SIZE
        if set(data["chunks"]) != {str(i) for i in range(expected_count)}:
            raise UploadError("Upload is missing acknowledged chunks")
        check = self.storage_preflight([{"session_id": session_id, "size": data["size"]}])
        # Final assembly needs a second complete copy while acknowledged chunks remain in place.
        check["required_bytes"] = data["size"] + check["remaining_upload_bytes"] + STORAGE_RESERVE_BYTES
        check["ok"] = check["free_bytes"] >= check["required_bytes"]
        if not check["ok"]:
            raise UploadError(self.insufficient_storage_message(check))
        data["state"] = "FINALIZING"
        self._save(directory / "session.json", data)
        hasher = hashlib.sha256()
        temporary = directory / "assembled.tmp"
        try:
            with temporary.open("wb") as output:
                for index in range(expected_count):
                    with (directory / f"{index:08d}.part").open("rb") as part:
                        while block := part.read(1024 * 1024):
                            output.write(block)
                            hasher.update(block)
                output.flush()
                os.fsync(output.fileno())
            if temporary.stat().st_size != data["size"] or not validate_media(temporary):
                raise UploadError("Final file size or media validation failed")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination)
            data.update(state="COMPLETED", final_sha256=hasher.hexdigest(), final_name=destination.name)
            self._save(directory / "session.json", data)
            for part in directory.glob("*.part"):
                part.unlink(missing_ok=True)
            return data
        except BaseException:
            temporary.unlink(missing_ok=True)
            data["state"] = "UPLOADING"
            self._save(directory / "session.json", data)
            raise

    def cancel(self, session_id: str) -> None:
        directory = self._dir(session_id)
        if directory.exists():
            import shutil
            shutil.rmtree(directory)

