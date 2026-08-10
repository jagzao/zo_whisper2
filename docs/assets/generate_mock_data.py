"""Script de un solo uso: genera archivos mock (video/audio + transcripciones
falsas) para tomar screenshots del dashboard sin usar datos reales de clientes.
Reversible: ver cleanup_mock_data.py.
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
    clip_len = 6  # segundos reales del clip de prueba (loop no hace falta, solo necesitamos que cargue)
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

    metadata = {
        "audio_file": str(media_path),
        "language": language,
        "duration": duration,
        "processing_time": round(duration * 0.18, 1),
        "processed_at": datetime.now().isoformat(),
        "segments_count": 1,
    }
    (out_folder / f"{stem}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    segments_data = {
        **metadata,
        "text": text,
        "segments": [{"start": 0.0, "end": duration, "text": text}],
    }
    (out_folder / f"{stem}_segments.json").write_text(
        json.dumps(segments_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


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
    print("[OK] Datos mock generados.")


if __name__ == "__main__":
    main()
