"""Validated media optimization with auditable provenance and safe cleanup.

The raw source is never removed until a staged optimized output is proven to be
a playable container with a video stream, a finite positive duration within
`max(2s, 5%)` of the source, the same audio presence the source had, a nonzero
size, and a meaningful size reduction. Only then is the output published
atomically, re-probed, hash-verified and recorded in provenance before the
exact provenance-linked source is unlinked.

Every failure path retains the source. Provenance stores only relative
identifiers plus hashes/sizes/durations, never a machine-specific absolute path
as the sole identity. Cleanup outcome is always classified so callers can show
`OPTIMIZED_SOURCE_REMOVED`, `OPTIMIZED_SOURCE_RETAINED`, `CLEANUP_PENDING` or
`FAILED` without guessing.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from transcript_pipeline.config import DATA_ROOT
from transcript_pipeline.media.utils import run_ffprobe
from transcript_pipeline.settings import SETTINGS

# Initial acceptance: at least 1% smaller before the source may be removed.
MIN_SIZE_REDUCTION_RATIO = 0.01
# Duration must stay within this absolute floor or relative fraction.
_DURATION_TOLERANCE_FLOOR_SEC = 2.0
_DURATION_TOLERANCE_FRACTION = 0.05
# Bounds a truly hung ffmpeg, not normal H.265 encoding time.
_ENCODE_TIMEOUT_SECONDS = 2 * 60 * 60
PROVENANCE_FILENAME = "compression_provenance.json"

# H.265/hvc1 is only legal inside an MP4 container. The source extension (e.g.
# `.webm`) must therefore never be carried over to the optimized output: every
# optimization is published as MP4, keeping the source stem for discovery.
OPTIMIZED_SUFFIX = ".mp4"

_READ_BLOCK = 64 * 1024

OPTIMIZED_SOURCE_REMOVED = "OPTIMIZED_SOURCE_REMOVED"
OPTIMIZED_SOURCE_RETAINED = "OPTIMIZED_SOURCE_RETAINED"
CLEANUP_PENDING = "CLEANUP_PENDING"
FAILED = "FAILED"

# Final states that mean the source is confirmed gone.
_SOURCE_REMOVED_STATES = frozenset({OPTIMIZED_SOURCE_REMOVED})


@dataclass(frozen=True)
class Probe:
    """Independent read of a media file's container/stream facts."""

    path: Path
    ok: bool
    has_video: bool
    has_audio: bool | None
    duration: float | None
    size_bytes: int


@dataclass(frozen=True)
class CompressionResult:
    """Outcome of one optimize attempt, with auditable provenance."""

    source: Path
    output: Path | None
    cleanup_state: str
    reason: str | None
    source_size: int
    output_size: int | None
    source_duration: float | None
    output_duration: float | None
    source_sha256: str | None
    output_sha256: str | None

    @property
    def bytes_saved(self) -> int:
        if self.output_size is None:
            return 0
        return max(0, self.source_size - self.output_size)

    @property
    def succeeded(self) -> bool:
        return self.cleanup_state in (OPTIMIZED_SOURCE_REMOVED, OPTIMIZED_SOURCE_RETAINED, CLEANUP_PENDING)

    def to_record(self, base_path: Path) -> dict:
        return {
            "sourceRelative": _relative(self.source, base_path),
            "outputRelative": _relative(self.output, base_path) if self.output else None,
            "sourceSha256": self.source_sha256,
            "outputSha256": self.output_sha256,
            "sourceSize": self.source_size,
            "outputSize": self.output_size,
            "sourceDuration": self.source_duration,
            "outputDuration": self.output_duration,
            "bytesSaved": self.bytes_saved,
            "cleanupState": self.cleanup_state,
            "reason": self.reason,
            "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


def _relative(path: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(os.fspath(path), os.fspath(base))).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _contained_path(ref: str | None, base: Path) -> Path | None:
    """Resolve `ref` against `base` only when it is a strict descendant.

    Absolute references, `..` traversal and symlink escapes that leave `base`
    are rejected, so callers never read or unlink outside `base`. Containment is
    validated on real paths, but the returned path is the lexical, normalized
    `base / ref` (not its resolved target): unlinking a provenance-recorded
    symlink removes the link itself and never the file it points at. Returns None
    when the reference is empty, is `base` itself, or escapes `base`.
    """
    if not ref:
        return None
    ref_path = Path(ref)
    if ref_path.is_absolute():
        return None
    if any(part == os.pardir for part in ref_path.parts):
        return None
    base_real = Path(os.path.realpath(base))
    lexical = Path(os.path.normpath(os.path.join(os.fspath(base_real), os.fspath(ref_path))))
    resolved = Path(os.path.realpath(lexical))
    try:
        relative = resolved.relative_to(base_real)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return lexical


def _resolves_within(path: Path, root: Path, *, allow_root: bool = False) -> bool:
    """True when `path` resolves to a descendant of `root` (equal only if allowed).

    Compares real paths so `..` traversal and symlink escapes are rejected: a
    link or junction pointing outside `root` resolves outside and fails.
    """
    root_real = Path(os.path.realpath(root))
    path_real = Path(os.path.realpath(path))
    try:
        relative = path_real.relative_to(root_real)
    except ValueError:
        return False
    return allow_root or bool(relative.parts)


def _contained_under(ref: str | None, base: Path, root: Path) -> Path | None:
    """Resolve `ref` under `base` and require the result to stay within `root`.

    Combines relative containment with a real-path root check so a record may
    only name a source under `base/Video_compress` or an output under
    `base/Videos`. Other in-root files, `..` traversal and symlink escapes are
    rejected before any read or unlink.
    """
    resolved = _contained_path(ref, base)
    if resolved is None or not _resolves_within(resolved, root):
        return None
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(_READ_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def default_prober(path: Path) -> Probe:
    """ffprobe-backed probe; never raises — an unreadable file is `ok=False`."""
    path = Path(path)
    size = 0
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = run_ffprobe(cmd)
        data = json.loads(result.stdout or "{}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return Probe(path=path, ok=False, has_video=False, has_audio=None, duration=None, size_bytes=size)

    streams = data.get("streams", [])
    if not streams:
        return Probe(path=path, ok=False, has_video=False, has_audio=None, duration=None, size_bytes=size)

    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)

    duration = None
    values = [(data.get("format") or {}).get("duration")]
    values.extend(stream.get("duration") for stream in streams)
    for value in values:
        if value is None:
            continue
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            duration = candidate
            break

    return Probe(
        path=path,
        ok=True,
        has_video=has_video,
        has_audio=has_audio,
        duration=duration,
        size_bytes=size,
    )


def encode_h265(source: Path, output: Path, *, crf: int = 25) -> bool:
    """Encodes `source` to H.265 at `output`. Returns False on any failure."""
    clamped = max(24, min(26, crf))
    cmd = [
        "ffmpeg", "-i", str(source),
        "-c:v", "libx265",
        "-preset", "slow",
        "-crf", str(clamped),
        "-tag:v", "hvc1",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-f", "mp4",
        "-y", str(output),
    ]
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        )
    except FileNotFoundError:
        return False
    try:
        _stdout, _stderr = process.communicate(timeout=_ENCODE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return False
    return process.returncode == 0 and Path(output).is_file()


def duration_tolerance(source_duration: float) -> float:
    return max(_DURATION_TOLERANCE_FLOOR_SEC, source_duration * _DURATION_TOLERANCE_FRACTION)


def validate_candidate(
    source: Probe,
    candidate: Probe,
    *,
    min_reduction_ratio: float = MIN_SIZE_REDUCTION_RATIO,
) -> str | None:
    """Returns a human-readable reason when the candidate must not replace the
    source, or None when it is a safe, smaller, complete optimization."""
    if not candidate.ok or not candidate.has_video:
        return "optimized output is not a playable video container"
    if candidate.size_bytes <= 0:
        return "optimized output is empty"
    if candidate.duration is None:
        return "optimized output has no finite positive duration"
    if source.duration is not None:
        tolerance = duration_tolerance(source.duration)
        if abs(candidate.duration - source.duration) > tolerance:
            return (
                f"optimized duration {candidate.duration:.3f}s differs from source "
                f"{source.duration:.3f}s by more than {tolerance:.3f}s"
            )
    if source.has_audio is True and candidate.has_audio is False:
        return "optimized output dropped the source audio stream"
    if source.size_bytes > 0:
        ratio = 1.0 - (candidate.size_bytes / source.size_bytes)
        if ratio < min_reduction_ratio:
            return (
                f"optimized output is not meaningfully smaller "
                f"({ratio * 100:.1f}% < {min_reduction_ratio * 100:.1f}% required)"
            )
    return None


def _unique_destination(final_path: Path) -> Path:
    if not final_path.exists():
        return final_path
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    index = 2
    candidate = final_path.with_name(f"{final_path.stem}_{stamp}{final_path.suffix}")
    while candidate.exists():
        candidate = final_path.with_name(f"{final_path.stem}_{stamp}_{index}{final_path.suffix}")
        index += 1
    return candidate


class ProvenanceStore:
    """JSON registry of compression provenance, keyed by output relative path."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, records: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def upsert(self, record: dict) -> dict:
        records = self.load()
        key = record["outputRelative"] or record["sourceRelative"]
        records[key] = record
        self.save(records)
        return record

    def list(self) -> list[dict]:
        return list(self.load().values())

    def find_by_source(self, source_relative: str, source_sha256: str) -> dict | None:
        for record in self.load().values():
            if record.get("sourceRelative") == source_relative and record.get("sourceSha256") == source_sha256:
                return record
        return None


def optimize_media(
    source: Path,
    destination_dir: Path,
    *,
    base_path: Path | None = None,
    prober=None,
    compressor=None,
    provenance: ProvenanceStore | None = None,
    provenance_path: Path | None = None,
    min_reduction_ratio: float = MIN_SIZE_REDUCTION_RATIO,
    remove_source: bool = True,
    crf: int | None = None,
) -> CompressionResult:
    """Compress `source` into `destination_dir` only after full validation.

    Order: probe source -> encode to a same-filesystem staging file -> validate
    staged output -> publish atomically -> re-probe/hash-verify published ->
    persist provenance -> unlink only the linked source. Any failure before the
    final unlink retains the source and removes only our own staging artifact.
    """
    source = Path(source)
    destination_dir = Path(destination_dir)
    prober = prober or default_prober
    if compressor is None:
        _crf = SETTINGS.video_compress_crf if crf is None else crf
        compressor = lambda src, dst: encode_h265(src, dst, crf=_crf)  # noqa: E731
    base = Path(base_path) if base_path is not None else DATA_ROOT
    store = provenance or ProvenanceStore(provenance_path or (base / PROVENANCE_FILENAME))

    # Fail closed before any probe/encode: only a source strictly inside
    # base/Video_compress and a destination inside base/Videos may proceed.
    # Real-path resolution rejects `..` traversal and symlink/junction escapes.
    if not _resolves_within(source, base / "Video_compress") or not _resolves_within(source, base):
        return _rejected(source, "source is outside the allowed Video_compress directory")
    if not _resolves_within(destination_dir, base / "Videos", allow_root=True) or not _resolves_within(
        destination_dir, base
    ):
        return _rejected(source, "destination is outside the allowed Videos directory")

    if not source.is_file():
        return CompressionResult(
            source=source, output=None, cleanup_state=FAILED, reason="source file is missing",
            source_size=0, output_size=None, source_duration=None, output_duration=None,
            source_sha256=None, output_sha256=None,
        )

    source_probe = prober(source)
    if not source_probe.ok or not source_probe.has_video:
        return CompressionResult(
            source=source, output=None, cleanup_state=FAILED,
            reason="source is not a valid video with a readable stream",
            source_size=source_probe.size_bytes, output_size=None,
            source_duration=source_probe.duration, output_duration=None,
            source_sha256=None, output_sha256=None,
        )

    # Fail closed before encoding: without a finite positive duration and a
    # nonzero size there is no trustworthy baseline to validate the optimized
    # output against, so no encoder is ever started.
    if source_probe.size_bytes <= 0:
        return CompressionResult(
            source=source, output=None, cleanup_state=FAILED,
            reason="source media is empty (zero size)",
            source_size=source_probe.size_bytes, output_size=None,
            source_duration=source_probe.duration, output_duration=None,
            source_sha256=None, output_sha256=None,
        )
    if source_probe.duration is None or not math.isfinite(source_probe.duration) or source_probe.duration <= 0:
        return CompressionResult(
            source=source, output=None, cleanup_state=FAILED,
            reason="source media has no finite positive duration",
            source_size=source_probe.size_bytes, output_size=None,
            source_duration=source_probe.duration, output_duration=None,
            source_sha256=None, output_sha256=None,
        )

    source_sha = sha256_file(source)
    source_relative = _relative(source, base)

    existing = store.find_by_source(source_relative, source_sha)
    if existing is not None and existing.get("cleanupState") in _SOURCE_REMOVED_STATES:
        # Identical source bytes already published and cleaned up: idempotent.
        return _result_from_record(source, existing, base, source_probe)

    destination_dir.mkdir(parents=True, exist_ok=True)
    # The source suffix is kept in the staging name only to keep two same-stem
    # sources (e.g. clip.mp4 and clip.webm) from sharing one staging file; the
    # published output itself always uses OPTIMIZED_SUFFIX.
    staging = destination_dir / f".{source.stem}{source.suffix}.optimized{OPTIMIZED_SUFFIX}"

    output_path: Path | None = None
    output_sha: str | None = None
    output_probe: Probe | None = None

    existing_output = str(existing.get("outputRelative") or "") if existing else ""
    existing_sha = str(existing.get("outputSha256") or "") if existing else ""
    if existing_output and existing_sha:
        candidate = base / existing_output
        if candidate.is_file() and sha256_file(candidate) == existing_sha:
            # A matching hash proves the bytes are the ones we produced, not that
            # they are still a valid optimization. Re-validate before reuse: an
            # output that no longer validates must not stand in for the source.
            existing_probe = prober(candidate)
            if validate_candidate(
                source_probe, existing_probe, min_reduction_ratio=min_reduction_ratio
            ) is None:
                output_path = candidate
                output_sha = existing_sha
                output_probe = existing_probe

    if output_path is None:
        staging.unlink(missing_ok=True)
        try:
            produced = bool(compressor(source, staging))
        except Exception as exc:  # noqa: BLE001 - every encoder failure retains the source
            staging.unlink(missing_ok=True)
            return _failed(source, source_probe, source_sha, f"encoder failed: {exc}")
        if not produced or not staging.is_file() or staging.stat().st_size == 0:
            staging.unlink(missing_ok=True)
            return _failed(source, source_probe, source_sha, "encoder produced no output")

        candidate_probe = prober(staging)
        reason = validate_candidate(source_probe, candidate_probe, min_reduction_ratio=min_reduction_ratio)
        if reason is not None:
            staging.unlink(missing_ok=True)
            return _failed(source, source_probe, source_sha, reason, output_duration=candidate_probe.duration)

        staging_sha = sha256_file(staging)
        final_path = _unique_destination(destination_dir / f"{source.stem}{OPTIMIZED_SUFFIX}")
        try:
            os.replace(staging, final_path)
        except OSError as exc:
            staging.unlink(missing_ok=True)
            return _failed(source, source_probe, source_sha, f"atomic publish failed: {exc}")

        published_probe = prober(final_path)
        published_reason = validate_candidate(source_probe, published_probe, min_reduction_ratio=min_reduction_ratio)
        published_sha = sha256_file(final_path)
        if published_reason is not None or published_sha != staging_sha:
            final_path.unlink(missing_ok=True)
            return _failed(
                source, source_probe, source_sha,
                published_reason or "published output hash does not match staged output",
                output_duration=published_probe.duration,
            )
        output_path = final_path
        output_sha = published_sha
        output_probe = published_probe

    assert output_path is not None and output_sha is not None and output_probe is not None

    if not remove_source:
        result = CompressionResult(
            source=source, output=output_path, cleanup_state=OPTIMIZED_SOURCE_RETAINED,
            reason="optimized output published; source retained by policy",
            source_size=source_probe.size_bytes, output_size=output_probe.size_bytes,
            source_duration=source_probe.duration, output_duration=output_probe.duration,
            source_sha256=source_sha, output_sha256=output_sha,
        )
        store.upsert(result.to_record(base))
        return result

    # Persist provenance BEFORE unlinking: a persistence failure must leave the
    # source in place. The record is first written as CLEANUP_PENDING so an
    # interrupted/unregistered cleanup is always recoverable.
    pending = CompressionResult(
        source=source, output=output_path, cleanup_state=CLEANUP_PENDING,
        reason="optimized output published; source cleanup pending",
        source_size=source_probe.size_bytes, output_size=output_probe.size_bytes,
        source_duration=source_probe.duration, output_duration=output_probe.duration,
        source_sha256=source_sha, output_sha256=output_sha,
    )
    try:
        store.upsert(pending.to_record(base))
    except Exception as exc:  # noqa: BLE001 - unregistered output must not remove the source
        return CompressionResult(
            source=source, output=output_path, cleanup_state=FAILED,
            reason=f"provenance persistence failed; source retained: {exc}",
            source_size=source_probe.size_bytes, output_size=output_probe.size_bytes,
            source_duration=source_probe.duration, output_duration=output_probe.duration,
            source_sha256=source_sha, output_sha256=output_sha,
        )

    # Re-verify the source bytes immediately before unlinking: if anything
    # rewrote the source after the pre-encode hash was captured, the published
    # output no longer corresponds to it and the source must survive.
    try:
        source_intact = sha256_file(source) == source_sha
    except OSError:
        source_intact = False
    if not source_intact:
        result = replace(
            pending,
            reason="source bytes changed during optimization; source retained",
        )
        _try_upsert(store, result.to_record(base))
        return result

    try:
        source.unlink()
    except OSError as exc:
        result = replace(pending, reason=f"optimized output published; source removal failed: {exc}")
        _try_upsert(store, result.to_record(base))
        return result

    result = replace(pending, cleanup_state=OPTIMIZED_SOURCE_REMOVED, reason=None)
    _try_upsert(store, result.to_record(base))
    return result


def _try_upsert(store: ProvenanceStore, record: dict) -> None:
    try:
        store.upsert(record)
    except Exception:  # noqa: BLE001 - state is already durable enough to recover on retry
        pass


def retry_source_cleanup(
    output_relative: str,
    *,
    base_path: Path | None = None,
    provenance: ProvenanceStore | None = None,
    prober=None,
) -> str:
    """Retry unlinking the exact provenance-linked source.

    Refuses unless the persisted record names a source under `base/Video_compress`
    and an output under `base/Videos`, both proven present with the recorded
    hashes and with the output still a valid optimization of the source. Only
    then is the exact source unlinked. Returns the resulting cleanup state; on any
    mismatch the record is left `CLEANUP_PENDING` and the source untouched.
    """
    prober = prober or default_prober
    base = Path(base_path) if base_path is not None else DATA_ROOT
    store = provenance or ProvenanceStore(base / PROVENANCE_FILENAME)
    records = store.load()
    record = records.get(output_relative)
    if record is None:
        return FAILED

    # Only a cleanup still recorded as pending may proceed. A source already
    # removed or intentionally retained must never be unlinked here, even when
    # its recorded hashes still match the files on disk. This guard lives in the
    # function, not only in the HTTP endpoint, so every caller inherits it.
    if record.get("cleanupState") != CLEANUP_PENDING:
        return str(record.get("cleanupState") or FAILED)

    output_ref = record.get("outputRelative")
    source_ref = record.get("sourceRelative")
    if not output_ref or not source_ref:
        return FAILED

    # Fail closed: only a source strictly under base/Video_compress and an output
    # under base/Videos may be touched. Real-path resolution rejects other
    # in-root files, `..` traversal and symlink escapes without any read/unlink.
    output_path = _contained_under(output_ref, base, base / "Videos")
    source_path = _contained_under(source_ref, base, base / "Video_compress")
    if output_path is None or source_path is None:
        return FAILED
    if (not output_path.is_file() or record.get("outputSha256") != sha256_file(output_path)):
        record["cleanupState"] = CLEANUP_PENDING
        record["reason"] = "published output is missing or changed; cleanup not attempted"
        records[output_relative] = record
        store.save(records)
        return CLEANUP_PENDING
    if not source_path.is_file():
        record["cleanupState"] = OPTIMIZED_SOURCE_REMOVED
        record["reason"] = None
        records[output_relative] = record
        store.save(records)
        return OPTIMIZED_SOURCE_REMOVED
    if record.get("sourceSha256") != sha256_file(source_path):
        record["cleanupState"] = CLEANUP_PENDING
        record["reason"] = "source bytes changed since optimization; cleanup not attempted"
        records[output_relative] = record
        store.save(records)
        return CLEANUP_PENDING

    # Re-probe both files immediately before the unlink: a source whose published
    # output no longer validates (missing stream, truncated, no longer smaller)
    # must survive even though the recorded hashes still match.
    invalid_reason = validate_candidate(prober(source_path), prober(output_path))
    if invalid_reason is not None:
        record["cleanupState"] = CLEANUP_PENDING
        record["reason"] = f"published output is not a valid optimization: {invalid_reason}"
        records[output_relative] = record
        store.save(records)
        return CLEANUP_PENDING

    # Re-read the source bytes immediately before the unlink. Probing and
    # validation were separate steps; anything that rewrote the source between
    # the recorded hash and now means the published output no longer corresponds
    # to it, so the source must survive and cleanup stays pending.
    try:
        source_intact = sha256_file(source_path) == record.get("sourceSha256")
    except OSError:
        source_intact = False
    if not source_intact:
        record["cleanupState"] = CLEANUP_PENDING
        record["reason"] = "source bytes changed during cleanup; cleanup not attempted"
        records[output_relative] = record
        store.save(records)
        return CLEANUP_PENDING

    try:
        source_path.unlink()
    except OSError as exc:
        record["cleanupState"] = CLEANUP_PENDING
        record["reason"] = f"source removal failed: {exc}"
        records[output_relative] = record
        store.save(records)
        return CLEANUP_PENDING

    record["cleanupState"] = OPTIMIZED_SOURCE_REMOVED
    record["reason"] = None
    records[output_relative] = record
    store.save(records)
    return OPTIMIZED_SOURCE_REMOVED


def _rejected(source: Path, reason: str) -> CompressionResult:
    return CompressionResult(
        source=source, output=None, cleanup_state=FAILED, reason=reason,
        source_size=0, output_size=None, source_duration=None, output_duration=None,
        source_sha256=None, output_sha256=None,
    )


def _failed(
    source: Path,
    source_probe: Probe,
    source_sha: str,
    reason: str,
    *,
    output_duration: float | None = None,
) -> CompressionResult:
    return CompressionResult(
        source=source, output=None, cleanup_state=FAILED, reason=reason,
        source_size=source_probe.size_bytes, output_size=None,
        source_duration=source_probe.duration, output_duration=output_duration,
        source_sha256=source_sha, output_sha256=None,
    )


def _result_from_record(source: Path, record: dict, base: Path, source_probe: Probe) -> CompressionResult:
    output_ref = record.get("outputRelative")
    return CompressionResult(
        source=source,
        output=_contained_path(output_ref, base) if output_ref else None,
        cleanup_state=record.get("cleanupState", FAILED),
        reason=record.get("reason"),
        source_size=record.get("sourceSize", source_probe.size_bytes),
        output_size=record.get("outputSize"),
        source_duration=record.get("sourceDuration", source_probe.duration),
        output_duration=record.get("outputDuration"),
        source_sha256=record.get("sourceSha256"),
        output_sha256=record.get("outputSha256"),
    )


def as_dict(result: CompressionResult, base_path: Path | None = None) -> dict:
    data = asdict(result)
    data["source"] = str(result.source)
    data["output"] = str(result.output) if result.output else None
    data["bytesSaved"] = result.bytes_saved
    data["succeeded"] = result.succeeded
    if base_path is not None:
        data.update(result.to_record(base_path))
    return data


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: python -m transcript_pipeline.media.optimize <source> <destination_dir>")
        return 2
    result = optimize_media(Path(argv[0]), Path(argv[1]))
    print(json.dumps(as_dict(result), indent=2))
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
