from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaptureSource(str, Enum):
    BROWSER_CAMERA = "BROWSER_CAMERA"
    ANDROID_COMPANION = "ANDROID_COMPANION"


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    PROCESSING = "PROCESSING"
    WAITING_FOR_EXTERNAL_TRANSCRIPT = "WAITING_FOR_EXTERNAL_TRANSCRIPT"
    DOCUMENTING = "DOCUMENTING"
    COMPLETE = "COMPLETE"
    RECOVERABLE = "RECOVERABLE"
    FAILED = "FAILED"


class SegmentStatus(str, Enum):
    RECEIVING = "RECEIVING"
    SEALED = "SEALED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED = "FAILED"


class AudioStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    AUDIO_STREAM_PRESENT = "AUDIO_STREAM_PRESENT"
    NO_AUDIO_STREAM = "NO_AUDIO_STREAM"
    NO_SPEECH_DETECTED = "NO_SPEECH_DETECTED"
    TRANSCRIPT_AVAILABLE = "TRANSCRIPT_AVAILABLE"


@dataclass(frozen=True)
class ROI:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if not all(0 <= value <= 1 for value in (self.x, self.y, self.width, self.height)):
            raise ValueError("ROI coordinates must be normalized to [0, 1]")
        if self.width <= 0 or self.height <= 0 or self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("ROI must have positive dimensions and fit within the source frame")


@dataclass
class CaptureConfig:
    logicalSegmentSeconds: int = 600
    uploadTimesliceSeconds: int = 5
    roi: ROI | None = None
    audioEnabled: bool = True
    preferredVideoDeviceId: str | None = None
    preferredAudioDeviceId: str | None = None
    mimeType: str | None = None
    sourceWidth: int | None = None
    sourceHeight: int | None = None
    outputWidth: int | None = None
    outputHeight: int | None = None
    fps: float | None = None

    def __post_init__(self) -> None:
        if not 300 <= self.logicalSegmentSeconds <= 900:
            raise ValueError("logical segment duration must be between 5 and 15 minutes")
        if not 1 <= self.uploadTimesliceSeconds <= 30:
            raise ValueError("upload timeslice must be between 1 and 30 seconds")


@dataclass
class CaptureSession:
    sessionId: str
    title: str
    captureConfig: CaptureConfig = field(default_factory=CaptureConfig)
    projectName: str | None = None
    captureSource: CaptureSource = CaptureSource.BROWSER_CAMERA
    status: SessionStatus = SessionStatus.CREATED
    createdAt: str = field(default_factory=utc_now)
    startedAt: str | None = None
    stoppedAt: str | None = None
    updatedAt: str = field(default_factory=utc_now)
    lastViewedAt: str | None = None
    transcriptState: str = "NONE"
    documentationState: str = "NOT_STARTED"
    sourceMediaState: str = "PRESENT"
    segmentCount: int = 0
    totalRecordedSeconds: float = 0.0
    totalReceivedBytes: int = 0
    activeTranscriptId: str | None = None
    completedAt: str | None = None
    error: str | None = None
    schemaVersion: int = 1

    def __post_init__(self) -> None:
        self.sessionId = str(UUID(self.sessionId))
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("session title is required")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["captureSource"] = self.captureSource.value
        result["status"] = self.status.value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaptureSession:
        config = dict(data.get("captureConfig") or {})
        if isinstance(config.get("roi"), dict):
            config["roi"] = ROI(**config["roi"])
        return cls(
            **{key: value for key, value in data.items() if key not in {"captureConfig", "captureSource", "status"}},
            captureConfig=CaptureConfig(**config),
            captureSource=CaptureSource(data.get("captureSource", CaptureSource.BROWSER_CAMERA)),
            status=SessionStatus(data.get("status", SessionStatus.CREATED)),
        )


@dataclass
class CaptureSegment:
    sessionId: str
    sequence: int
    startOffsetSeconds: float
    expectedDurationSeconds: float
    status: SegmentStatus = SegmentStatus.RECEIVING
    actualDurationSeconds: float | None = None
    expectedChunkCount: int | None = None
    receivedChunkCount: int = 0
    receivedBytes: int = 0
    mimeType: str | None = None
    mediaRelativePath: str | None = None
    audioStatus: AudioStatus = AudioStatus.UNKNOWN
    processingStatus: str = "PENDING"
    transcriptArtifactId: str | None = None
    frameOutputRelativePath: str | None = None
    contentHash: str | None = None
    error: str | None = None
    schemaVersion: int = 1

    def __post_init__(self) -> None:
        self.sessionId = str(UUID(self.sessionId))
        if self.sequence < 1 or self.startOffsetSeconds < 0 or self.expectedDurationSeconds <= 0:
            raise ValueError("invalid segment sequence or timing")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["audioStatus"] = self.audioStatus.value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaptureSegment:
        return cls(**{
            **data,
            "status": SegmentStatus(data.get("status", SegmentStatus.RECEIVING)),
            "audioStatus": AudioStatus(data.get("audioStatus", AudioStatus.UNKNOWN)),
        })


@dataclass
class TranscriptArtifact:
    transcriptId: str
    sessionId: str
    source: str
    format: str
    language: str | None
    timecoded: bool
    alignment: str
    createdAt: str
    contentHash: str
    relativePath: str
    isActive: bool = False
