"""Puente explícito hacia el "shared kernel" en watcher/core.

watcher/ trae funcionalidad real que el pipeline diario reutiliza
(extracción de keyframes, formateo de timestamps, cliente LLM agnóstico
de proveedor, utilidades de idioma/limpieza). No es un microservicio
aparte para ese código: es una librería compartida, así que en vez de
esparcir `sys.path.insert(...)` en cada módulo que la necesita (como
hacía el script original), este es el único punto que expone el boundary.

watcher/ no tiene `__init__.py` en ningún nivel — son namespace packages
implícitos de Python 3, así que basta con tener PROJECT_ROOT en sys.path
para poder hacer `import watcher.core...`.
"""

from __future__ import annotations

import sys

from transcript_pipeline.config import PROJECT_ROOT

_bootstrapped = False


def ensure_watcher_importable() -> bool:
    """Agrega PROJECT_ROOT a sys.path si hace falta. Devuelve True si watcher/ existe."""
    global _bootstrapped
    watcher_dir = PROJECT_ROOT / "watcher"
    if not watcher_dir.is_dir():
        return False
    if not _bootstrapped:
        root_str = str(PROJECT_ROOT)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        _bootstrapped = True
    return True
