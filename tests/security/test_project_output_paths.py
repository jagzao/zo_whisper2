"""Attack matrix for `resolve_project_output_path` (WP-02).

`projects.json` is local configuration, but it is edited from the dashboard
and copied between host/container installs. In container mode a copied
config must not become an arbitrary-write primitive: `../` traversal,
Windows/Unix absolute paths, drive-relative paths, NUL bytes, symlink
escapes and sibling-prefix look-alikes of allowed roots must all be
refused. Host mode intentionally keeps the pre-WP-02 legacy behavior for
absolute paths (trusted local config) — the last test pins that decision
so it can't be "fixed" away by accident either.
"""

from __future__ import annotations

import os

import pytest

from transcript_pipeline.projects import resolve_project_output_path
from transcript_pipeline.security.exceptions import PathTraversalError


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    return root


# ── Relative branch: traversal is mode-independent ────────────────────


@pytest.mark.parametrize("container_mode", [False, True])
class TestRelativeTraversalRejected:
    def test_simple_parent_traversal(self, data_root, container_mode):
        with pytest.raises(PathTraversalError):
            resolve_project_output_path("../outside", data_root, container_mode)

    def test_deeply_nested_traversal(self, data_root, container_mode):
        # "../" segments buried behind real segments — resolve() must still
        # land outside data_root and be rejected.
        with pytest.raises(PathTraversalError):
            resolve_project_output_path("a/b/../../../x", data_root, container_mode)


# ── Malformed input ────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["", "exports\x00", None, 42])
def test_empty_null_byte_and_non_str_rejected(data_root, bad):
    with pytest.raises(PathTraversalError):
        resolve_project_output_path(bad, data_root, True)


# ── Absolute paths in container mode ──────────────────────────────────


def test_unix_rooted_path_rejected_in_container_mode(data_root):
    # Works on POSIX ("/etc/passwd" is absolute) and on Windows (pathlib
    # resolves a root-only path against the CWD drive → still outside
    # data_root) — no platform skip needed.
    with pytest.raises(PathTraversalError):
        resolve_project_output_path("/etc/passwd", data_root, True)


@pytest.mark.skipif(os.name != "nt", reason="drive-qualified strings are plain relative names on POSIX")
@pytest.mark.parametrize("raw", ["C:/Windows/win.ini", r"C:\Windows\win.ini"])
def test_windows_drive_absolute_rejected_in_container_mode(data_root, raw):
    with pytest.raises(PathTraversalError):
        resolve_project_output_path(raw, data_root, True)


@pytest.mark.skipif(os.name != "nt", reason="drive-relative syntax does not exist on POSIX")
@pytest.mark.parametrize("container_mode", [False, True])
def test_drive_relative_path_rejected_in_both_modes(data_root, container_mode):
    # "C:foo" anchors to the CWD *of drive C* — an ambiguous escape that
    # no containment check can reason about, so it is refused outright
    # (same policy as SafePathResolver.resolve), even in host mode.
    with pytest.raises(PathTraversalError):
        resolve_project_output_path("C:foo", data_root, container_mode)


# ── Symlinks ───────────────────────────────────────────────────────────


def test_symlink_escape_rejected(data_root, tmp_path):
    outside = tmp_path / "outside_target"
    outside.mkdir()
    link = data_root / "escape_link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    # resolve() follows the symlink before the containment check, so the
    # candidate is the outside target and must be refused.
    with pytest.raises(PathTraversalError):
        resolve_project_output_path("escape_link", data_root, True)


def test_symlink_inside_data_root_allowed(data_root):
    real_dir = data_root / "real"
    real_dir.mkdir()
    link = data_root / "alias"
    try:
        link.symlink_to(real_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    resolved = resolve_project_output_path("alias", data_root, True)
    assert resolved == real_dir.resolve()


# ── Containment boundary precision ────────────────────────────────────


def test_sibling_prefix_of_allowed_root_rejected(tmp_path):
    # "…/exports_evil" string-prefixes "…/exports" — a naive startswith
    # guard would accept it; normcase + os.sep boundary must not.
    allowed = tmp_path / "exports"
    allowed.mkdir()
    evil = tmp_path / "exports_evil"
    evil.mkdir()
    with pytest.raises(PathTraversalError):
        resolve_project_output_path(str(evil), tmp_path / "data", True, allowed_roots=(allowed,))


# ── Host mode: intentional legacy behavior ────────────────────────────


def test_host_mode_absolute_outside_data_root_accepted(tmp_path):
    """Documents AC 6: absolute output_path is trusted local config on the
    host — identical to pre-WP-02 behavior, no containment, no mkdir."""
    outside = tmp_path / "legacy_exports"
    outside.mkdir()
    resolved = resolve_project_output_path(str(outside), tmp_path / "data", False)
    assert resolved == outside.resolve()

    missing_nested = tmp_path / "legacy2" / "deep"
    resolved = resolve_project_output_path(str(missing_nested), tmp_path / "data", False)
    assert resolved == missing_nested.resolve()
    assert not missing_nested.exists()
