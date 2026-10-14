# Local Ops - zo_whisper2

GitHub Actions esta DESHABILITADO (politica de costo cero). Estas eran las funciones de Actions:

## 1) Secret scan (antes: secret-scan.yml, on push/pull_request)

```powershell
.\scripts\secret-scan.ps1
```

Recomendacion: correrlo antes de cada push. Es barato y local.

## 2) Dashboard CI (antes: dashboard-ci.yml, on push con paths filtrados)

```bash
pip install -e .[dev]      # o el entorno que uses
pytest tests -q
python -m compileall src/transcript_pipeline dashboard.py master_processor.py simple_scan.py compress_and_move.py
```

## Politica
GitHub Actions: DISABLED. No agregar .github/workflows.

## Validación de interfaz

- Zo Media Intelligence web UI: Playwright Chromium (`python scripts/e2e.py`).
- Proyectos Electron: Playwright Electron.
- Este repositorio no agrega Electron como dependencia de runtime.

El runner local compacto usa `python scripts/gate_runner.py <pytest|quality|security|smoke|playwright|e2e>`.
SonarQube se configura en el entorno o almacén de credenciales local con
`SONAR_HOST_URL` y `SONAR_TOKEN`; no guardar tokens en Git.

La subida desde móvil usa bloques reanudables de 4 MiB. Si se corta la red,
vuelve a abrir el dashboard y selecciona el mismo archivo para continuar; las
sesiones incompletas se conservan hasta 7 días en `.upload_sessions/`.
