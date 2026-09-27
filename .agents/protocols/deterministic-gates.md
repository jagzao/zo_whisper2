# Deterministic Gates V4

## Principle

LLMs plan and code. Deterministic tools validate repeatedly at zero LLM-token cost.

A gate is authoritative only when it has an executable command/tool and machine-readable or reproducible evidence.

## Gate classes

### Fast targeted gates

Run after each relevant work package:
- targeted pytest
- Ruff on touched Python surface
- Pyright on typed production surface
- narrow security regression
- narrow Playwright scenario
- FFmpeg/ffprobe fixture verification

### Release gates

Run at US/feature closure:
- `pytest tests/ -q`
- `python scripts/quality.py`
- `python scripts/security.py`
- `python scripts/smoke.py`
- `python scripts/e2e.py`
- SonarQube quality gate when configured
- Jenkins integration/soak workflow when configured
- GitHub Actions/public PR checks when enabled

## Compact failure contract

Prefer a normalized artifact such as:

`artifacts/gates/latest.json`

Example:

```json
{
  "status": "FAIL",
  "gate": "playwright",
  "check": "project_override_persists_after_reload",
  "error_signature": "expected Project A, got Project B",
  "affected_files": ["src/transcript_pipeline/dashboard/app.py"],
  "artifact": "artifacts/playwright/project-override.zip",
  "duration_seconds": 12.4
}
```

The coder receives this compact evidence first. Raw logs are fetched only when needed.

## Playwright

For Zo Media Intelligence:
- browser = Chromium
- validate real UI behavior
- save screenshot/trace only when useful
- scenario code becomes a permanent deterministic regression test

Do not use an LLM to repeatedly click through a stable scenario.

## Electron

Electron is not a validator by itself.

Only Electron products use Playwright Electron. Zo Media Intelligence remains on the browser adapter and must not acquire an Electron runtime just to test the UI.

## Jenkins

Jenkins is the preferred local/long-running orchestrator when installed/configured.

Intended pipeline:
```
changed-file analysis
 -> targeted tests
 -> quality
 -> security
 -> Playwright
 -> SonarQube
 -> integration/full E2E
 -> optional soak/nightly
 -> artifacts
```

Jenkins is complementary to public PR CI; it does not replace GitHub Actions when the latter is available.

Jenkins failures should emit compact artifacts consumable by project-lead.

## SonarQube

Use SonarQube for deterministic static-quality findings such as:
- code smells
- cognitive complexity
- duplication
- maintainability findings
- coverage/quality thresholds when configured

Do not spend strong-model tokens manually rediscovering what SonarQube can report deterministically.

A failing Sonar rule should be routed as structured evidence:
- rule id
- severity
- file/line
- concise message

## Zero-token repeat requirement

Once a gate/test exists, project-lead must be able to rerun it without invoking an LLM.

An LLM is used only when:
- authoring/updating a test as part of implementation, or
- fixing a deterministic failure.
