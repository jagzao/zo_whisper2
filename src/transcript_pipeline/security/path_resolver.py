"""Central filesystem boundary for the dashboard.

Every endpoint that reads, writes, or deletes a file under one of the
pipeline's data folders must go through `SafePathResolver` instead of
building a `Path` by hand. A previous version of the dashboard checked
`str(path.resolve()).startswith(str(root.resolve()))` per-endpoint; that
is bypassable (`C:\\whisper` is a string-prefix of `C:\\whisper_evil`) and
was missing entirely on two endpoints. This module is the single place
that decides whether a path is inside an allowed root.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from transcript_pipeline.security.exceptions import PathNotFoundError, PathTraversalError


class MediaRoot(str, Enum):
    AUDIO = "audio"
    VIDEOS = "videos"
    VIDEO_COMPRESS = "video_compress"
    TRANSCRIPTIONS = "transcriptions"


class SafePathResolver:
    """Resolves and validates paths against a fixed set of allowed roots."""

    def __init__(self, roots: dict[MediaRoot, Path]):
        self._roots: dict[MediaRoot, Path] = {
            root: path.resolve(strict=False) for root, path in roots.items()
        }

    def resolve(self, root: MediaRoot, relative: str, *, must_exist: bool = True) -> Path:
        """Resolves a project-relative id (e.g. from a future `media_id`) under `root`."""
        if not relative or "\x00" in relative:
            raise PathTraversalError(f"Invalid path segment: {relative!r}")
        candidate_pure = Path(relative)
        if candidate_pure.is_absolute() or candidate_pure.drive or candidate_pure.root:
            # Covers not just drive-qualified absolute paths ("C:\..."), but also
            # drive-less rooted paths ("/etc/passwd") and drive-relative paths
            # ("C:foo") — pathlib's `/` operator resets to the drive root for the
            # former when joined, silently escaping `base` despite is_absolute()
            # being False for both.
            raise PathTraversalError(f"Absolute path not allowed: {relative!r}")

        base = self._roots[root]
        candidate = (base / relative).resolve(strict=False)
        if not self._is_within(candidate, base):
            raise PathTraversalError(f"{relative!r} escapes root {root.value!r}")
        if must_exist and not candidate.exists():
            raise PathNotFoundError(str(candidate))
        return candidate

    def resolve_within_any(
        self, roots: list[MediaRoot], raw_path: str, *, must_exist: bool = True
    ) -> Path:
        """Validates a client-supplied absolute path against a set of allowed roots.

        Kept for the dashboard's existing `?path=<absolute>` contract (see
        `docs/adr/` for the migration plan to opaque ids) — the client still
        sends an absolute path, but it is only ever trusted once proven to
        resolve inside one of the explicitly allowed roots.
        """
        if not raw_path or "\x00" in raw_path:
            raise PathTraversalError(f"Invalid path: {raw_path!r}")

        candidate = Path(raw_path).resolve(strict=False)
        for root in roots:
            base = self._roots[root]
            if self._is_within(candidate, base):
                if must_exist and not candidate.exists():
                    raise PathNotFoundError(str(candidate))
                return candidate
        raise PathTraversalError(f"{raw_path!r} is outside allowed roots")

    def to_id(self, root: MediaRoot, absolute_path: Path) -> str:
        """Absolute path -> opaque, forward-slash relative id for exposing to the frontend."""
        resolved = absolute_path.resolve(strict=False)
        base = self._roots[root]
        if not self._is_within(resolved, base):
            raise PathTraversalError(f"{absolute_path} is outside root {root.value!r}")
        return resolved.relative_to(base).as_posix()

    @staticmethod
    def _is_within(candidate: Path, base: Path) -> bool:
        # normcase folds case and separators on Windows (NTFS is case-insensitive);
        # without it, "C:\whisper" would string-prefix-match "C:\whisper_evil".
        # candidate/base are already resolve()d, so symlinks pointing outside
        # `base` are caught here too (resolve() follows them to their real target).
        candidate_s = os.path.normcase(str(candidate))
        base_s = os.path.normcase(str(base))
        return candidate_s == base_s or candidate_s.startswith(base_s + os.sep)
