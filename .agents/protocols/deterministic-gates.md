# Deterministic Gates V5

## Principle

LLMs implement. Deterministic tools validate repeatedly at zero LLM-token cost.

A gate is authoritative only when it has an executable command/tool and machine-readable or reproducible evidence.

`scripts/gate_runner.py` is the single compact runner. It splits gates into two PLV5 categories and never silently treats `NOT_CONFIGURED` as `PASS`.

## Gate categories

### Implementation (light) gates — before ChatGPT review

Run by the local coder after each work package:
- `targeted` / `unit` — pytest on the changed surface (paths required)
- `lint` — Ruff on scripts/tests
- `quality` — `scripts/quality.py`
- `typecheck` — compileall of src/scripts (Pyright when configured)
- `security` — `scripts/security.py`
- `smoke` — `scripts/smoke.py`
- FFmpeg/ffprobe fixture verification when the surface is media

### Heavy gates — only after ChatGPT `/review` and the RAM gate

Run by `scripts/heavy_validation_runner.py`:
- `pytest` — full repository regression
- `e2e` / `playwright` — `scripts/e2e.py` full E2E
- `sonar` — SonarQube quality gate
- `docker-build` / `docker-e2e` — Docker gates when configured
- `jenkins` — Jenkins pipeline when configured
- `soak` — soak/load when configured
- dependency/security scans requiring large downloads

Heavy gates never run before `/review`, never modify product code, and never invoke a model. A heavy failure is handed to ChatGPT for diagnosis.

## RAM gate (heavy validation precondition)

`scripts/ram_gate.py` measures available physical RAM deterministically:

```
available_ram_gib >  6.0  -> HEAVY_VALIDATION_ALLOWED
available_ram_gib <= 6.0  -> HEAVY_VALIDATION_DEFERRED_LOW_RAM
```

Low RAM is not a product failure and must not cause an LLM loop. A deferred run retries the deterministic RAM gate in the nighttime window.

Exit codes: 0 ALLOWED, 3 DEFERRED_LOW_RAM, 2 measurement/config error.

## NOT_CONFIGURED

A gate whose authoritative command is not installed reports `NOT_CONFIGURED` (exit 4). It is neither PASS nor FAIL. If every heavy gate is NOT_CONFIGURED, the heavy runner reports `BLOCKED`.

## Compact failure contract

Prefer a normalized artifact such as:

`artifacts/gates/latest.json`

Example:

```json
{
  "status": "FAIL",
  "gate": "playwright",
  "category": "heavy",
  "check": "project_override_persists_after_reload",
  "error_signature": "expected Project A, got Project B",
  "affected_files": ["src/transcript_pipeline/dashboard/app.py"],
  "artifact": "artifacts/playwright/project-override.zip",
  "duration_seconds": 12.4
}
```

The coder receives this compact evidence first. Raw logs are fetched only when needed. Raw logs are never embedded in summaries.

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

Do not spend model tokens manually rediscovering what SonarQube can report deterministically.

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

No LLM waits for or polls a deterministic process: pytest, Playwright, Docker, Jenkins and Sonar run to completion on their own.
