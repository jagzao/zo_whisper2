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

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from transcript_pipeline.config import load_env
from transcript_pipeline.errors import ConfigurationError

_LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _infer_llm_provider_type(llm_base_url: str) -> str:
    """Real hostname parsing, not a substring check — "localhost" in
    "https://localhost.example.com" would otherwise misclassify a remote
    domain as local."""
    hostname = (urlparse(llm_base_url).hostname or "").lower()
    if hostname in _LOOPBACK_HOSTNAMES:
        return "local"
    try:
        return "local" if ipaddress.ip_address(hostname).is_loopback else "remote"
    except ValueError:
        return "remote"


def _bool(name: str, default: bool) -> bool:
    import os

    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() not in {"0", "false", "no", ""}


def _bool_with_legacy_alias(name: str, legacy_name: str, default: bool) -> bool:
    """Reads `name`; if unset, falls back to the deprecated `legacy_name`
    env var so existing `scan_config.env` files don't silently stop working
    after a rename."""
    import os

    if os.getenv(name) is not None:
        return _bool(name, default)
    return _bool(legacy_name, default)


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

    # ── File tracking ────────────────────────────────────────────────
    file_tracker_hash_mode: str  # "fast" | "full"

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
    allow_image_upload: bool  # any image bytes outbound: frames, screenshots, document-embedded images
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
        provider_type = os.getenv("LLM_PROVIDER_TYPE") or _infer_llm_provider_type(llm_base_url)

        settings = cls(
            whisper_model=os.getenv("WHISPER_MODEL", "large-v3"),
            word_timestamps=_bool("WORD_TIMESTAMPS", False),
            clean_transcription=_bool("CLEAN_TRANSCRIPTION", False),
            keyframes_required=_bool("KEYFRAMES_REQUIRED", True),
            keyframe_method=os.getenv("KEYFRAME_METHOD", "smart_scene").strip().lower() or "smart_scene",
            file_tracker_hash_mode=os.getenv("FILE_TRACKER_HASH_MODE", "fast").strip().lower() or "fast",
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
            allow_image_upload=_bool_with_legacy_alias("ALLOW_IMAGE_UPLOAD", "ALLOW_FRAME_UPLOAD", False),
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
        if self.file_tracker_hash_mode not in ("fast", "full"):
            raise ConfigurationError(f"FILE_TRACKER_HASH_MODE must be 'fast' or 'full': {self.file_tracker_hash_mode!r}")
        if not (0 <= self.video_compress_crf <= 51):
            raise ConfigurationError(f"VIDEO_COMPRESS_CRF out of range (0-51): {self.video_compress_crf}")
        if not (1024 <= self.dashboard_port <= 65535):
            raise ConfigurationError(f"DASHBOARD_PORT invalid: {self.dashboard_port}")
        if self.dashboard_host not in _LOOPBACK_HOSTNAMES:
            raise ConfigurationError(
                f"DASHBOARD_HOST must be a loopback address (127.0.0.1/localhost/::1): "
                f"{self.dashboard_host!r} — remote binding is not supported."
            )
        if self.llm_provider_type not in ("local", "remote"):
            raise ConfigurationError(f"LLM_PROVIDER_TYPE must be 'local' or 'remote': {self.llm_provider_type!r}")
        if self.retention_days < 0:
            raise ConfigurationError(f"RETENTION_DAYS cannot be negative: {self.retention_days}")
        if self.upload_max_mb <= 0:
            raise ConfigurationError(f"UPLOAD_MAX_MB must be positive: {self.upload_max_mb}")


SETTINGS = Settings.from_env()
