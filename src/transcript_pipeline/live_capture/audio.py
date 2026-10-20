"""Audio-state logic for Live Capture (W7).

Pure, deterministic mapping from the two independent audio observations —
the browser's audio-track presence and ffprobe's media-stream presence — to
the persisted `AudioAvailability` and the derived `transcript_required`
flag. No I/O lives here: callers supply the observed facts, so the logic is
trivially unit-testable without ffprobe or a real MediaStream.

A confirmed absence from *either* source dominates (video-only is valid and
must never be upgraded to AVAILABLE); a confirmed presence wins over
UNKNOWN; anything else stays UNKNOWN. Transcript is *required* only when
audio is missing and no transcript has arrived yet — a video-only capture
is usable and documentable without audio, it just needs a separately
supplied transcript.
"""

from __future__ import annotations

from transcript_pipeline.live_capture.errors import ValidationError
from transcript_pipeline.live_capture.models import AudioAvailability


def audio_availability_from_track_count(audio_track_count: int | None) -> AudioAvailability:
    """Maps an observed browser audio-track count to availability.

    ``None`` means track presence was never determined (UNKNOWN). Zero audio
    tracks means video-only (MISSING). One or more means AVAILABLE.
    """
    if audio_track_count is None:
        return AudioAvailability.UNKNOWN
    if isinstance(audio_track_count, bool) or not isinstance(audio_track_count, int) or audio_track_count < 0:
        raise ValidationError("audio track count must be a nonnegative integer or null")
    return AudioAvailability.AVAILABLE if audio_track_count > 0 else AudioAvailability.MISSING


def resolve_audio_availability(
    track_present: bool | None,
    stream_present: bool | None,
) -> AudioAvailability:
    """Combines independent detections into a single availability.

    A confirmed absence (``False``) from either source yields MISSING — a
    missing audio track cannot be contradicted by a stale ffprobe result.
    A confirmed presence (``True``) yields AVAILABLE when nothing is
    confirmed absent. Both unknown yields UNKNOWN.
    """
    if track_present is False or stream_present is False:
        return AudioAvailability.MISSING
    if track_present is True or stream_present is True:
        return AudioAvailability.AVAILABLE
    return AudioAvailability.UNKNOWN


def transcript_required(
    audio_availability: AudioAvailability,
    transcript_available: bool,
) -> bool:
    """True when a capture has no audio to transcribe and no transcript yet.

    This is the durable derivation for the TRANSCRIPT_REQUIRED state: it
    never claims a transcript exists when it does not, and it stops being
    required the moment a transcript arrives.
    """
    return audio_availability is AudioAvailability.MISSING and not transcript_available
