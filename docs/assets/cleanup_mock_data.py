"""Revierte exactamente lo que genera generate_mock_data.py."""
from __future__ import annotations

import json
from pathlib import Path

from generate_mock_data import MOCK_FILES, ROOT, PROCESSED_DB, VIDEOS, AUDIO, TRANSCRIPTIONS


def main() -> None:
    db = json.loads(PROCESSED_DB.read_text(encoding="utf-8")) if PROCESSED_DB.exists() else {}

    for rel_path, *_ in MOCK_FILES:
        media_path = ROOT / rel_path
        base = Path(rel_path)
        is_video = base.parts[0] == "Videos"
        src_base = VIDEOS if is_video else AUDIO
        rel_to_base = media_path.relative_to(src_base)
        out_folder = TRANSCRIPTIONS / rel_to_base.parent
        stem = media_path.stem

        for f in [media_path, out_folder / f"{stem}.txt",
                  out_folder / f"{stem}_metadata.json", out_folder / f"{stem}_segments.json"]:
            if f.exists():
                f.unlink()
                print(f"[DEL] {f}")

        key = str(media_path.absolute())
        db.pop(key, None)

        # limpiar carpetas vacias que haya creado el mock
        try:
            media_path.parent.rmdir()
        except OSError:
            pass
        try:
            out_folder.rmdir()
        except OSError:
            pass

    PROCESSED_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[OK] Datos mock eliminados, processed_files.json restaurado.")


if __name__ == "__main__":
    main()
