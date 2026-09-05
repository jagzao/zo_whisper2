"""Smoke harness: fast, minimal checks that the product can actually start
and do its core job — distinct from the full UT suite and the browser-driven
E2E harness (US-001 §11.4/§12). Fails fast with actionable output.

Run:
    python scripts/smoke.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
REPORT_PATH = ROOT / "smoke_report.json"

sys.path.insert(0, str(SRC))

REPORT: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    REPORT.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    return ok


def check_core_imports() -> bool:
    try:
        import transcript_pipeline.config  # noqa: F401
        import transcript_pipeline.documentation.engine  # noqa: F401
        import transcript_pipeline.file_tracker  # noqa: F401
        import transcript_pipeline.projects  # noqa: F401
        import transcript_pipeline.settings  # noqa: F401
        return check("core_imports", True)
    except Exception as e:
        return check("core_imports", False, str(e))


def check_settings_load() -> bool:
    try:
        from transcript_pipeline.settings import SETTINGS
        ok = bool(SETTINGS.dashboard_host) and SETTINGS.allow_external_llm is False
        return check("settings_load_safe_defaults", ok, f"dashboard_host={SETTINGS.dashboard_host!r}")
    except Exception as e:
        return check("settings_load_safe_defaults", False, str(e))


def check_ffmpeg_detection() -> bool:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    return check("ffmpeg_detection", bool(ffmpeg and ffprobe), f"ffmpeg={ffmpeg}, ffprobe={ffprobe}")


def check_dashboard_boots() -> bool:
    try:
        from transcript_pipeline.dashboard import app as dashboard_app
        dashboard_app.app.config.update(TESTING=True)
        with dashboard_app.app.test_client() as client:
            index_ok = client.get("/").status_code == 200
            status_resp = client.get("/api/status")
            status_ok = status_resp.status_code == 200 and "running" in status_resp.get_json()
        return check("dashboard_boots_and_status_responds", index_ok and status_ok)
    except Exception as e:
        return check("dashboard_boots_and_status_responds", False, str(e))


def check_transcription_pipeline_initializes() -> bool:
    try:
        from transcript_pipeline.transcription import processor
        # Not loading the actual Whisper model (expensive) — this proves the
        # module's import-time environment setup (CPU threads, tutorial
        # feature detection, dependency probing) doesn't blow up.
        ok = hasattr(processor, "SimpleScanProcessor") and hasattr(processor, "WHISPER_AVAILABLE")
        return check(
            "transcription_pipeline_initializes", ok,
            f"tutorial_features_available={processor.TUTORIAL_FEATURES_AVAILABLE}"
        )
    except Exception as e:
        return check("transcription_pipeline_initializes", False, str(e))


def check_documentation_renderer() -> bool:
    try:
        from transcript_pipeline.documentation.engine import generate_documentation
        with tempfile.TemporaryDirectory() as tmp:
            frames_dir = Path(tmp) / "frames"
            frames_dir.mkdir()
            mapping = {
                "video_info": {"name": "smoke.mp4", "duration": 5.0, "extraction_method": "smart_scene"},
                "transcription_summary": {"language": "en"},
                "frames": [{"frame_file": "frame_0000.png", "timestamp": 1.0, "timestamp_formatted": "00:00:01.000"}],
                "transcription_mapping": {"frame_0000.png": {"full_text": "Click OK."}},
            }
            (frames_dir / "frame_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
            (frames_dir / "frame_0000.png").write_bytes(b"fake")
            summary = generate_documentation(frames_dir, "smoke.mp4")
            ok = summary["step_count"] == 1 and (frames_dir / "manual" / "MANUAL.md").exists()
        return check("documentation_renderer_tiny_fixture", ok)
    except Exception as e:
        return check("documentation_renderer_tiny_fixture", False, str(e))


def main() -> int:
    checks = [
        check_core_imports,
        check_settings_load,
        check_ffmpeg_detection,
        check_dashboard_boots,
        check_transcription_pipeline_initializes,
        check_documentation_renderer,
    ]
    ok = True
    for fn in checks:
        ok &= fn()

    REPORT_PATH.write_text(json.dumps({"checks": REPORT, "ok": ok}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
