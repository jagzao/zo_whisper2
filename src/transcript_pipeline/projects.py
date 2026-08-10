"""Routing declarativo de proyectos: config, no if/else hardcodeado.

`projects.json` define, por proyecto, las reglas de match (carpeta, prefijo
de filename, palabra clave) y a dónde/cómo enrutar el resultado. Este
módulo es puro (no toca el filesystem salvo para leer el JSON) y por eso
es fácil de testear sin necesidad de audio real ni del modelo Whisper.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_projects(config_path: Path) -> list[dict]:
    """Carga la lista de proyectos desde projects.json. [] si no existe."""
    if not config_path.exists():
        logger.warning("[CONFIG] %s no encontrado — routing estático desactivado", config_path.name)
        return []
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("projects", [])


def match_project(audio_path: Path, projects: list[dict]) -> dict | None:
    """Devuelve el primer proyecto cuyas reglas de match aplican a audio_path."""
    name_lower = audio_path.name.lower()
    parent_str = str(audio_path.parent)

    for proj in projects:
        rules = proj.get("match", {})

        for folder in rules.get("folder_contains", []):
            if folder.lower() in parent_str.lower():
                return proj

        for prefix in rules.get("prefix", []):
            if name_lower.startswith(prefix.lower()):
                return proj

        for keyword in rules.get("filename_contains", []):
            if keyword.lower() in name_lower:
                return proj

    return None
