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

## Project Lead V5 (entrega de bajo token)

Herramientas deterministas del workflow (ver `.agents/protocols/`):

- `python scripts/model_router.py` — selección determinista del coder barato (cadena congelada Z.ai GLM -> OpenCode DeepSeek -> Ollama DeepSeek -> OpenRouter DeepSeek).
- `python scripts/ram_gate.py` — gate de RAM para validación pesada (`> 6.0 GiB` permitido; `<= 6.0 GiB` diferido a ventana nocturna).
- `python scripts/heavy_validation_runner.py` — orquestador de gates pesados sin LLM; solo tras `/review` en ChatGPT.
- `python scripts/implementation_summary.py ...` — SUMMARY.json/md compacto de cada entrega.
- `python scripts/delivery_checkpoint.py <show|verify|next-step>` — checkpoint atómico para reanudar tras cortes de luz.

Reglas: no E2E/Docker/Jenkins/Sonar antes del `/review` de ChatGPT; máximo 2
reparaciones mecánicas por firma idéntica; ningún test roto justifica escalar
de modelo.

La subida desde móvil usa bloques reanudables de 4 MiB. Si se corta la red,
vuelve a abrir el dashboard y selecciona el mismo archivo para continuar; las
sesiones incompletas se conservan hasta 7 días en `.upload_sessions/`.
