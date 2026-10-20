# TEST-MATRIX-ZMI-DKR-001 — Docker Acceptance Matrix

## Principle

Tests define expected behavior before local coding begins. The coding agent may implement them but may not weaken them to obtain green status without a new owner-approved analysis.

## Matrix

| ID | Layer | Behavior | Deterministic command / evidence | Required |
|---|---|---|---|---|
| DKR-UT-001 | Unit | DATA_ROOT defaults to PROJECT_ROOT | pytest | yes |
| DKR-UT-002 | Unit | ZMI_DATA_ROOT relocates all mutable paths | pytest tmp_path | yes |
| DKR-UT-003 | Unit | ZMI_CONFIG_ENV override is honored | pytest | yes |
| DKR-UT-004 | Unit | host mode rejects DASHBOARD_HOST=0.0.0.0 | pytest | yes |
| DKR-UT-005 | Unit | container mode allows internal 0.0.0.0 | pytest | yes |
| DKR-UT-006 | Unit | relative project output resolves under DATA_ROOT | pytest | yes |
| DKR-UT-007 | Unit/security | ../ output path escape rejected | pytest | yes |
| DKR-UT-008 | Unit/security | unsafe absolute output path rejected in container mode | pytest | yes |
| DKR-UT-009 | Unit | host legacy absolute output remains supported | pytest | yes |
| DKR-UT-010 | Unit | dashboard builds module subprocess commands with sys.executable | pytest mock | yes |
| DKR-UT-011 | Unit | logs target DATA_ROOT/logs | pytest tmp_path | yes |
| DKR-UT-012 | Unit | mock-data generator honors test data root | pytest/temp | yes |
| DKR-CFG-001 | Docker | docker compose config parses | docker compose config | yes |
| DKR-BLD-001 | Docker | runtime image builds from clean tree | docker build target runtime | yes |
| DKR-BLD-002 | Docker/security | image excludes secret/runtime paths | image/container filesystem assertions | yes |
| DKR-BLD-003 | Docker | test target builds | docker build target test | yes |
| DKR-SMK-001 | Container | app reaches healthy | healthcheck/API | yes |
| DKR-SMK-002 | Container | process UID != 0 | docker exec id -u | yes |
| DKR-SMK-003 | Container | ffmpeg + ffprobe present | command checks | yes |
| DKR-SMK-004 | Container | tesseract eng/spa present | tesseract --list-langs | yes |
| DKR-SMK-005 | Container/security | ALLOW_EXTERNAL_LLM false by default | status/config assertion | yes |
| DKR-SMK-006 | Container/security | root filesystem read-only | controlled write failure outside mounts | yes |
| DKR-SMK-007 | Container | /data and /cache writable | synthetic probe | yes |
| DKR-SMK-008 | Network/security | published binding is 127.0.0.1 only | docker inspect/compose config | yes |
| DKR-PER-001 | Persistence | projects config survives recreate | compose recreate + API/file assert | yes |
| DKR-PER-002 | Persistence | project override survives recreate | Playwright/API + recreate | yes |
| DKR-PER-003 | Persistence | processed state survives recreate | file state assert | yes |
| DKR-PER-004 | Persistence | transcript/docs survive recreate | file/API assert | yes |
| DKR-PER-005 | Recovery | run state after restart is not stale-running | /api/status | yes |
| DKR-ASR-001 | ML runtime | tiny Whisper model loads in container | deterministic script | yes |
| DKR-ASR-002 | ML runtime | tiny fixture returns non-empty transcription | deterministic script | yes |
| DKR-ASR-003 | Cache | model cache persists across recreate | cache listing/hash/second run | yes |
| DKR-E2E-001 | Playwright | dashboard loads through running Compose app | Playwright | yes |
| DKR-E2E-002 | Playwright | file table lists synthetic media | Playwright | yes |
| DKR-E2E-003 | Playwright | upload works | Playwright | yes |
| DKR-E2E-004 | Playwright | Edit File loads transcription | Playwright | yes |
| DKR-E2E-005 | Playwright | manual Project override saves | Playwright | yes |
| DKR-E2E-006 | Playwright | override survives reload | Playwright | yes |
| DKR-E2E-007 | Playwright | Auto removes manual override | Playwright | yes |
| DKR-E2E-008 | Playwright | docs/frame evidence UI loads | Playwright | yes |
| DKR-E2E-009 | Playwright | delete removes synthetic media | Playwright | yes |
| DKR-E2E-010 | Playwright | critical path has no uncaught page errors | Playwright | yes |
| DKR-REG-001 | Regression | existing host-mode pytest passes | full pytest | yes |
| DKR-REG-002 | Regression | existing host smoke passes | smoke gate | yes |
| DKR-REG-003 | Regression | existing host Playwright E2E passes | e2e gate | yes |
| DKR-SEC-001 | Security | SafePathResolver traversal suite stays green under relocated roots | security gate | yes |
| DKR-SEC-002 | Security | no secret/env/media file in image | image assertion + security scan | yes |
| DKR-SEC-003 | Security | no Docker socket/privileged/capabilities | compose config assertions | yes |
| DKR-QA-001 | Quality | Ruff/Pyright green | quality gate | yes |
| DKR-QA-002 | Dependencies | pip-audit green | security gate | yes |
| DKR-QA-003 | Sonar | quality gate result captured when configured | sonar.json | conditional |
| DKR-SOAK-001 | Soak | Docker E2E x3 without leaked state/processes | Jenkins optional soak | pre-release recommended |

## Timeouts

- unit/targeted: bounded by pytest normal timeout policy;
- container health: <= 60 s after Python process starts, excluding first model download;
- Docker build: CI/Jenkins hard timeout;
- tiny ASR: hard timeout <= 10 minutes including first download on normal broadband/CPU;
- Playwright E2E: <= 10 minutes;
- no LLM process waits on these timeouts.

## Failure artifact rules

On FAIL keep:
- compact gate JSON;
- last useful log segment;
- Playwright screenshot/trace when applicable;
- container logs;
- exact command;
- error signature.

Do not copy entire verbose logs into SUMMARY.md.

## Acceptance

No required test may be converted to SKIP to make the story pass unless the frozen spec is amended by owner + heavy-model analysis.
