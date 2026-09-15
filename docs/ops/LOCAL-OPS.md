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