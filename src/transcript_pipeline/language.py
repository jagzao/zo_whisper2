"""Detección de idioma: prefijo de filename > lang.txt de la carpeta > None (auto).

Extraído de SimpleScanProcessor para que sea una función pura, testeable
sin instanciar el procesador completo (que carga el modelo Whisper).
"""

from __future__ import annotations

from pathlib import Path

_SUPPORTED = {"es", "en"}


class LanguageDetector:
    """Cachea las lecturas de lang.txt por carpeta (I/O barata pero repetida)."""

    def __init__(self) -> None:
        self._lang_txt_cache: dict[Path, str | None] = {}

    def detect(self, filename: str, folder: Path | None = None) -> str | None:
        filename_lower = filename.lower()
        if filename_lower.startswith("es_"):
            return "es"
        if filename_lower.startswith("en_"):
            return "en"

        if folder is None:
            return None

        if folder not in self._lang_txt_cache:
            lang_file = folder / "lang.txt"
            lang = lang_file.read_text(encoding="utf-8").strip().lower() if lang_file.exists() else None
            self._lang_txt_cache[folder] = lang if lang in _SUPPORTED else None

        return self._lang_txt_cache[folder]
