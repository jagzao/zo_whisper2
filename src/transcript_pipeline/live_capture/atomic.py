"""Atomic filesystem primitives for the Live Capture manifest store.

Same contract as the K'ab ingest primitives: temp-file + fsync +
`os.replace` in the destination directory, so a crash can never leave a
half-written session manifest or chunk media file behind. Readers only
ever observe a previous or a next complete state.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(str(tmp), str(path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(parent)


def stage_stream(parent: Path, prefix: str, source) -> tuple[Path, str, int]:
    """Streams `source` into a temp file in `parent`; returns `(tmp, sha256, size)`.

    The payload is never buffered whole: each block is hashed and written as
    it arrives. The temp file is *not* yet the destination — a caller that
    needs to inspect/validate the bytes (e.g. idempotent fragment replay)
    decides whether to `commit_staged` it or discard it. On any error the
    temp file is removed.
    """
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=str(parent))
    tmp = Path(tmp_name)
    hasher = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as fh:
            for block in source:
                if not block:
                    continue
                hasher.update(block)
                fh.write(block)
                size += len(block)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, hasher.hexdigest(), size


def commit_staged(tmp: Path, path: Path) -> None:
    """Atomically moves a `stage_stream` temp file onto `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(tmp), str(path))
    fsync_dir(path.parent)


def atomic_write_stream(path: Path, source) -> tuple[str, int]:
    """Streams `source` (an iterable of bytes blocks) into a temp file and
    atomically replaces `path`; returns `(sha256_hex, size)`.

    The whole payload is never buffered in memory — each block is hashed and
    written as it arrives, so a caller can finalize an unbounded-length
    upload in bounded memory. On any error the temp file is removed.
    """
    tmp, digest, size = stage_stream(path.parent, f".{path.name}.", source)
    try:
        os.replace(str(tmp), str(path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)
    return digest, size


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def read_json(path: Path) -> Any | None:
    """Reads JSON written by `atomic_write_json`; `None` if absent/unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
