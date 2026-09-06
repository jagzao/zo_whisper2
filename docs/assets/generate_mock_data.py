"""One-off script: generates mock files (video/audio + fake transcriptions)
to take dashboard screenshots without using real client data.
Reversible: see cleanup_mock_data.py.

FAKE_TRANSCRIPT_ES is intentionally in Spanish — it's illustrative sample
data showing the bilingual (es/en) transcription feature, not a piece of
untranslated documentation.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "audio"
VIDEOS = ROOT / "Videos"
TRANSCRIPTIONS = ROOT / "CarpetaTranscripciones"
PROCESSED_DB = ROOT / "processed_files.json"

FAKE_TRANSCRIPT_ES = (
    "Buenos días equipo, empecemos con el repaso del sprint. Terminamos la "
    "integración del endpoint de autenticación y quedó pendiente el ajuste de "
    "paginación en el listado principal. El pipeline de CI ya corre las pruebas "
    "unitarias en cada pull request, falta agregar las de integración. "
    "Sobre el bug reportado ayer, ya identificamos que era un problema de caché "
    "en el cliente, se corrige con invalidación al guardar. Para el próximo "
    "sprint priorizamos la migración del servicio de notificaciones y "
    "la documentación de la API interna. ¿Alguna duda antes de cerrar?"
)

FAKE_TRANSCRIPT_EN = (
    "Good morning everyone, let's go through the sprint review. We finished the "
    "authentication endpoint integration, pagination on the main list is still "
    "pending. CI already runs unit tests on every pull request, integration "
    "tests are next. About yesterday's bug, it was a client-side caching issue, "
    "fixed with invalidation on save. Next sprint we're prioritizing the "
    "notification service migration and internal API docs. Any questions "
    "before we wrap up?"
)

# (relative_path, language, transcript, duration_sec)
MOCK_FILES: list[tuple[str, str, str, float]] = [
    ("Videos/py_northwind/northwind_standup_260801.mp4", "en", FAKE_TRANSCRIPT_EN, 612.0),
    ("Videos/py_northwind/northwind_planning_260805.mp4", "en", FAKE_TRANSCRIPT_EN, 754.0),
    ("Videos/py_zo/zo_interview_acme.mp4", "es", FAKE_TRANSCRIPT_ES, 1834.0),
    ("audio/py_contoso/contoso_daily_260802.mp3", "en", FAKE_TRANSCRIPT_EN, 320.0),
    ("audio/py_contoso/contoso_daily_260803.mp3", "en", FAKE_TRANSCRIPT_EN, 298.0),
    ("audio/py_contoso/contoso_claim_review.mp3", "en", FAKE_TRANSCRIPT_EN, 415.0),
    ("Videos/py_meetings/meeting_arquitectura_260803.webm", "es", FAKE_TRANSCRIPT_ES, 2635.0),
    ("Videos/py_fabrikam/fabrikam_planning_260804.webm", "es", FAKE_TRANSCRIPT_ES, 2151.0),
    ("Videos/py_fabrikam/fabrikam_status_260806.webm", "es", FAKE_TRANSCRIPT_ES, 1897.0),
    ("Videos/mi_tutorial_deploy_pipeline.mp4", "es", FAKE_TRANSCRIPT_ES, 980.0),
]


def make_media(path: Path, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clip_len = 6  # actual seconds of the test clip (no need to loop, just needs to load)
    if path.suffix.lower() == ".mp3":
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(clip_len), str(path),
        ]
    else:
        vcodec = "libvpx-vp9" if path.suffix.lower() == ".webm" else "libx264"
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=15",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(clip_len), "-c:v", vcodec, "-pix_fmt", "yuv420p", str(path),
        ]
    subprocess.run(cmd, check=True, capture_output=True)


def make_transcription(rel_path: str, language: str, text: str, duration: float) -> None:
    media_path = ROOT / rel_path
    base = Path(rel_path)
    is_video = base.parts[0] == "Videos"
    src_base = VIDEOS if is_video else AUDIO
    rel_to_base = media_path.relative_to(src_base)
    out_folder = TRANSCRIPTIONS / rel_to_base.parent
    out_folder.mkdir(parents=True, exist_ok=True)

    stem = media_path.stem
    (out_folder / f"{stem}.txt").write_text(text, encoding="utf-8")

    # Split into multiple sentence-level segments (not one giant blob) so
    # the dashboard's segment-click-to-seek / evidence-navigation flow has
    # more than one segment to actually navigate between.
    sentences = [s.strip() for s in text.replace("¿", "").split(". ") if s.strip()]
    if not sentences:
        sentences = [text]
    seg_len = duration / len(sentences)
    segments = [
        {"start": round(i * seg_len, 1), "end": round((i + 1) * seg_len, 1), "text": s if s.endswith((".", "?")) else s + "."}
        for i, s in enumerate(sentences)
    ]

    metadata = {
        "audio_file": str(media_path),
        "language": language,
        "duration": duration,
        "processing_time": round(duration * 0.18, 1),
        "processed_at": datetime.now().isoformat(),
        "segments_count": len(segments),
    }
    (out_folder / f"{stem}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    segments_data = {
        **metadata,
        "text": text,
        "segments": segments,
    }
    (out_folder / f"{stem}_segments.json").write_text(
        json.dumps(segments_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def make_tutorial_documentation(rel_path: str, language: str) -> None:
    """Builds a synthetic frame_mapping.json (2 fake frames + aligned
    transcript excerpts) for the mock tutorial video and runs the real
    documentation engine on it — so the dashboard's DOCS tab and the
    Documentation action have something real to render in CI screenshots
    and the E2E smoke test, without needing an actual transcription run."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "src"))
    from transcript_pipeline.documentation.engine import generate_documentation

    media_path = ROOT / rel_path
    stem = media_path.stem
    frames_parent = TRANSCRIPTIONS / f"{stem}_Frames" / stem
    frames_parent.mkdir(parents=True, exist_ok=True)

    # Two tiny real PNGs so the DOCS tab / MANUAL.md images actually load.
    for i in range(2):
        frame_path = frames_parent / f"frame_{i:04d}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(frame_path)],
            check=True, capture_output=True,
        )

    mapping = {
        "video_info": {"name": media_path.name, "duration": 980.0, "extraction_method": "smart_scene"},
        "transcription_summary": {"language": language},
        "frames": [
            {"frame_file": "frame_0000.png", "timestamp": 5.0, "timestamp_formatted": "00:00:05.000"},
            {"frame_file": "frame_0001.png", "timestamp": 42.0, "timestamp_formatted": "00:00:42.000"},
        ],
        "transcription_mapping": {
            "frame_0000.png": {"full_text": "Open the deploy pipeline dashboard and select the target environment."},
            "frame_0001.png": {"full_text": "Click Run to start the deployment and watch the pipeline stages progress."},
        },
    }
    (frames_parent / "frame_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    generate_documentation(frames_parent, media_path.name)


def mark_processed(rel_path: str) -> None:
    db = json.loads(PROCESSED_DB.read_text(encoding="utf-8")) if PROCESSED_DB.exists() else {}
    media_path = ROOT / rel_path
    key = str(media_path.absolute())
    db[key] = {
        "path": key,
        "name": media_path.name,
        "size": media_path.stat().st_size if media_path.exists() else 0,
        "date": datetime.now().isoformat(),
        "status": "completed_routed",
        "hash": "mockdata00000000",
    }
    PROCESSED_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    for rel_path, language, text, duration in MOCK_FILES:
        path = ROOT / rel_path
        print(f"[MOCK] {rel_path}")
        make_media(path, duration)
        make_transcription(rel_path, language, text, duration)
        mark_processed(rel_path)
        if "tutorial" in rel_path.lower():
            make_tutorial_documentation(rel_path, language)
    print("[OK] Mock data generated.")


if __name__ == "__main__":
    main()
