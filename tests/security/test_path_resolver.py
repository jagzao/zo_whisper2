import pytest

from transcript_pipeline.security import (
    MediaRoot,
    PathNotFoundError,
    PathTraversalError,
    SafePathResolver,
)


@pytest.fixture
def roots(tmp_path):
    transcriptions = tmp_path / "CarpetaTranscripciones"
    videos = tmp_path / "Videos"
    transcriptions.mkdir()
    videos.mkdir()
    (transcriptions / "legit.txt").write_text("hello", encoding="utf-8")
    # A sibling directory whose name is prefixed by the allowed root's name —
    # this is exactly the string that a naive `startswith(str(root))` guard
    # would incorrectly accept.
    (tmp_path / "CarpetaTranscripciones_evil").mkdir()
    (tmp_path / "CarpetaTranscripciones_evil" / "secret.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("nope", encoding="utf-8")
    return SafePathResolver(
        {
            MediaRoot.TRANSCRIPTIONS: transcriptions,
            MediaRoot.VIDEOS: videos,
        }
    )


def test_resolve_legitimate_file(roots):
    resolved = roots.resolve(MediaRoot.TRANSCRIPTIONS, "legit.txt")
    assert resolved.name == "legit.txt"
    assert resolved.read_text(encoding="utf-8") == "hello"


def test_resolve_nested_legitimate_file(roots, tmp_path):
    nested = tmp_path / "CarpetaTranscripciones" / "proj" / "nested.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("x", encoding="utf-8")
    resolved = roots.resolve(MediaRoot.TRANSCRIPTIONS, "proj/nested.txt")
    assert resolved == nested.resolve()


def test_simple_traversal_rejected(roots):
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "../outside.txt")


def test_deeply_nested_traversal_rejected(roots):
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "a/b/../../../outside.txt")


def test_windows_absolute_path_rejected(roots):
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, r"C:\Windows\win.ini")


def test_unix_style_absolute_path_rejected(roots):
    # No drive letter, but rooted — pathlib's `/` operator would otherwise
    # reset to the base's drive root and escape `base` entirely.
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "/etc/passwd")


def test_drive_relative_path_rejected(roots):
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "C:outside.txt")


def test_null_byte_rejected(roots):
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "legit.txt\x00.png")


def test_sibling_prefix_root_rejected(roots, tmp_path):
    # str(candidate).startswith(str(root)) would wrongly accept this because
    # "CarpetaTranscripciones_evil" string-prefixes "CarpetaTranscripciones".
    evil = tmp_path / "CarpetaTranscripciones_evil" / "secret.txt"
    with pytest.raises(PathTraversalError):
        roots.resolve_within_any([MediaRoot.TRANSCRIPTIONS], str(evil))


def test_case_variation_still_matches_root(roots, tmp_path):
    # NTFS is case-insensitive; a same-directory reference with different
    # casing must still be accepted (this is not a bypass, it's the same file).
    legit = tmp_path / "CarpetaTranscripciones" / "legit.txt"
    resolved = roots.resolve_within_any(
        [MediaRoot.TRANSCRIPTIONS], str(legit).upper()
    )
    assert resolved.name.lower() == "legit.txt"


def test_missing_file_raises_not_found(roots):
    with pytest.raises(PathNotFoundError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "does_not_exist.txt")


def test_must_exist_false_allows_missing_file(roots):
    resolved = roots.resolve(MediaRoot.TRANSCRIPTIONS, "new_file.txt", must_exist=False)
    assert resolved.name == "new_file.txt"


def test_symlink_escape_rejected(roots, tmp_path):
    transcriptions = tmp_path / "CarpetaTranscripciones"
    link = transcriptions / "escape_link"
    try:
        link.symlink_to(tmp_path / "outside.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(PathTraversalError):
        roots.resolve(MediaRoot.TRANSCRIPTIONS, "escape_link")


def test_resolve_within_any_accepts_first_matching_root(roots, tmp_path):
    video_file = tmp_path / "Videos" / "clip.mp4"
    video_file.write_text("data", encoding="utf-8")
    resolved = roots.resolve_within_any(
        [MediaRoot.TRANSCRIPTIONS, MediaRoot.VIDEOS], str(video_file)
    )
    assert resolved == video_file.resolve()


def test_resolve_within_any_rejects_path_outside_all_roots(roots, tmp_path):
    with pytest.raises(PathTraversalError):
        roots.resolve_within_any(
            [MediaRoot.TRANSCRIPTIONS, MediaRoot.VIDEOS], str(tmp_path / "outside.txt")
        )


def test_to_id_roundtrip(roots, tmp_path):
    legit = tmp_path / "CarpetaTranscripciones" / "legit.txt"
    media_id = roots.to_id(MediaRoot.TRANSCRIPTIONS, legit)
    assert media_id == "legit.txt"
    assert roots.resolve(MediaRoot.TRANSCRIPTIONS, media_id) == legit.resolve()
