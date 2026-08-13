"""Centralized, typed configuration.

Before this module, ~15 environment variables were read ad hoc across
`dashboard/app.py`, `pipeline/master.py`, `media/compressor.py`,
`transcription/processor.py`, and the shared-kernel modules under
`watcher/core/`, each with its own `os.getenv(...)` call and its own
boolean-parsing rule (`.strip().lower() not in {"0", "false", "no"}`
repeated slightly differently in different places). `Settings.from_env()`
is the single place that reads and validates them; everything else
imports `SETTINGS` instead of calling `os.getenv` directly.

Kept intentionally as one dataclass, not a package: ~20 fields don't
justify a `settings/` submodule, and a flat dataclass keeps
`SETTINGS.field` lookups trivial to grep for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transcript_pipeline.config import load_env
from transcript_pipeline.errors import ConfigurationError


def _bool(name: str, default: bool) -> bool:
    import os

    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() not in {"0", "false", "no", ""}


def _str_or_none(name: str) -> str | None:
    import os

    val = os.getenv(name)
    return val if val else None


@dataclass(frozen=True)
class Settings:
    # ── Transcription ────────────────────────────────────────────────
    whisper_model: str
    word_timestamps: bool
    clean_transcription: bool
    keyframes_required: bool
    keyframe_method: str

    # ── Video ─────────────────────────────────────────────────────────
    video_compress_crf: int
    tesseract_cmd: str | None

    # ── Meeting handler ──────────────────────────────────────────────
    meeting_frame_interval: int
    meeting_max_screen_analyses: int
    meeting_keep_frames: bool

    # ── LLM / privacy ─────────────────────────────────────────────────
    llm_api_key: str | None
    llm_model: str
    llm_base_url: str
    llm_provider_type: str  # "local" | "remote", derived unless overridden
    allow_external_llm: bool
    frame_descriptions: bool
    frame_description_max: int

    # ── Privacy policy ────────────────────────────────────────────────
    privacy_mode: str  # "local" | "cloud"
    allow_frame_upload: bool
    retention_days: int

    # ── Dashboard ─────────────────────────────────────────────────────
    dashboard_host: str
    dashboard_port: int
    upload_max_mb: int

    # ── External source folders (Icecream Screen Recorder output) ───
    icecream_music: Path | None
    icecream_videos: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        import os

        load_env()

        llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        provider_type = os.getenv("LLM_PROVIDER_TYPE")
        if not provider_type:
            host = llm_base_url.lower()
            provider_type = "local" if ("localhost" in host or "127.0.0.1" in host) else "remote"

        settings = cls(
            whisper_model=os.getenv("WHISPER_MODEL", "large-v3"),
            word_timestamps=_bool("WORD_TIMESTAMPS", False),
            clean_transcription=_bool("CLEAN_TRANSCRIPTION", False),
            keyframes_required=_bool("KEYFRAMES_REQUIRED", True),
            keyframe_method=os.getenv("KEYFRAME_METHOD", "smart_scene").strip().lower() or "smart_scene",
            video_compress_crf=int(os.getenv("VIDEO_COMPRESS_CRF", "25")),
            tesseract_cmd=_str_or_none("TESSERACT_CMD"),
            meeting_frame_interval=int(os.getenv("MEETING_FRAME_INTERVAL", "15")),
            meeting_max_screen_analyses=int(os.getenv("MEETING_MAX_SCREEN_ANALYSES", "30")),
            meeting_keep_frames=_bool("MEETING_KEEP_FRAMES", False),
            llm_api_key=_str_or_none("LLM_API_KEY"),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_base_url=llm_base_url,
            llm_provider_type=provider_type,
            allow_external_llm=_bool("ALLOW_EXTERNAL_LLM", False),
            frame_descriptions=_bool("FRAME_DESCRIPTIONS", False),
            frame_description_max=int(os.getenv("FRAME_DESCRIPTION_MAX", "20")),
            privacy_mode=os.getenv("PRIVACY_MODE", "local").strip().lower(),
            allow_frame_upload=_bool("ALLOW_FRAME_UPLOAD", False),
            retention_days=int(os.getenv("RETENTION_DAYS", "0")),
            dashboard_host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
            dashboard_port=int(os.getenv("DASHBOARD_PORT", "5000")),
            upload_max_mb=int(os.getenv("UPLOAD_MAX_MB", "500")),
            icecream_music=Path(v) if (v := os.getenv("ICECREAM_MUSIC")) else None,
            icecream_videos=Path(v) if (v := os.getenv("ICECREAM_VIDEOS")) else None,
        )
        settings._validate()
        return settings

    def _validate(self) -> None:
        if not (0 <= self.video_compress_crf <= 51):
            raise ConfigurationError(f"VIDEO_COMPRESS_CRF out of range (0-51): {self.video_compress_crf}")
        if not (1024 <= self.dashboard_port <= 65535):
            raise ConfigurationError(f"DASHBOARD_PORT invalid: {self.dashboard_port}")
        if self.llm_provider_type not in ("local", "remote"):
            raise ConfigurationError(f"LLM_PROVIDER_TYPE must be 'local' or 'remote': {self.llm_provider_type!r}")
        if self.privacy_mode not in ("local", "cloud"):
            raise ConfigurationError(f"PRIVACY_MODE must be 'local' or 'cloud': {self.privacy_mode!r}")
        if self.retention_days < 0:
            raise ConfigurationError(f"RETENTION_DAYS cannot be negative: {self.retention_days}")
        if self.upload_max_mb <= 0:
            raise ConfigurationError(f"UPLOAD_MAX_MB must be positive: {self.upload_max_mb}")


SETTINGS = Settings.from_env()
