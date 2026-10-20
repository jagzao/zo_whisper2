# PLAN-ZMI-DKR-001 — Docker Implementation Plan

## Source

Frozen contract:
- `AUDIT-ZMI-DKR-001-docker-readiness.md`
- `EPIC-ZMI-DKR-001-docker-runtime.md`
- `US-ZMI-DKR-001-dockerize-product.md`

This plan is implementation detail only. It MUST NOT redefine expected product behavior.

## Execution model

Heavy reasoning/design has already been done in Git.

Local agent responsibilities:
- implement this plan;
- use lightweight GLM coder for normal coding;
- use deterministic tools for validation;
- do not redesign architecture;
- do not watch long-running gates;
- commit + push;
- trigger Jenkins;
- exit.

## Work package order

### WP-01 — Runtime path abstraction

Primary files:
- `src/transcript_pipeline/config.py`
- `src/transcript_pipeline/settings.py`
- `src/transcript_pipeline/logging_setup.py`
- `src/transcript_pipeline/dashboard/app.py`
- `src/transcript_pipeline/pipeline/master.py`
- `src/transcript_pipeline/file_tracker.py`
- synthetic-data scripts/tests.

Implementation:
1. Keep `PROJECT_ROOT` unchanged as immutable code root.
2. Add:
   - `DATA_ROOT = Path(os.getenv("ZMI_DATA_ROOT", PROJECT_ROOT)).resolve(...)`
   - `LOG_DIR = DATA_ROOT / "logs"`
   - `VIDEO_COMPRESS_DIR = DATA_ROOT / "Video_compress"`
   - existing AUDIO/VIDEOS/TRANSCRIPTIONS/state/config constants from DATA_ROOT.
3. Add `ZMI_CONFIG_ENV` support; default to existing repo-root `scan_config.env` for host backward compatibility.
4. Ensure `load_env()` does not fail when env file is absent.
5. Dashboard imports shared runtime path constants instead of rebuilding from `PROJECT_ROOT`.
6. `MasterProcessor.base_path = DATA_ROOT`; organize targets use `VIDEOS_DIR`.
7. Logging creates `LOG_DIR` and writes file there while preserving stdout.
8. Synthetic data generator/cleanup accepts `ZMI_DATA_ROOT`.
9. Add tests proving default host paths are unchanged and overridden paths all stay under temp data root.

Targeted gate:
`pytest tests/test_settings.py tests/test_file_tracker.py tests/test_dashboard_new_endpoints.py tests/integration -q`

### WP-02 — Container-safe bind and output routing

Primary files:
- `settings.py`
- `dashboard/app.py`
- `projects.py`
- `pipeline/master.py`
- `projects.json.example`
- security tests/docs.

Implementation:
1. Add typed `container_mode` setting from `ZMI_CONTAINER_MODE=false`.
2. Validation:
   - normal mode: dashboard host must remain loopback;
   - container mode: allow loopback or `0.0.0.0`;
   - do not add public-host authorization behavior.
3. Keep request Host/Origin allowlist unchanged for normal host access.
4. Add helper `resolve_project_output_path(raw, data_root, container_mode)`.
5. Relative path:
   - normalize against DATA_ROOT;
   - reject traversal;
   - create/allow only under DATA_ROOT.
6. Absolute path:
   - host mode: keep legacy behavior;
   - container mode: allow only when path resolves under DATA_ROOT or explicit configured allowed export roots; otherwise log + disable/reject.
7. Make `projects.json.example` portable with relative output paths/null where appropriate.
8. Regression tests for `../`, Windows drive paths and symlink escape.

Targeted gate:
`pytest tests/test_settings.py tests/test_projects.py tests/security -q`

### WP-03 — Remove repo-root subprocess coupling

Primary files:
- `dashboard/app.py`
- CLI/module tests.

Implementation:
1. Delete/simplify `_python_exe()`; use `sys.executable`.
2. Compression command:
   `[sys.executable, "-m", "transcript_pipeline.media.compressor"]`.
3. Master command:
   `[sys.executable, "-m", "transcript_pipeline.pipeline.master"]`.
4. `cwd` no longer determines module discovery; use installed package.
5. Preserve streaming stdout/stderr and stage inference.
6. Add command-construction unit tests; no real long transcription.

### WP-04 — Docker build contract

Create:
- `Dockerfile`
- `.dockerignore`
- `docker/entrypoint.sh`
- `requirements.runtime.lock.txt`.

Dockerfile stages:
1. `base`
   - Python 3.12 slim;
   - env: UTF-8, unbuffered, no pip cache;
   - apt packages: ffmpeg, tesseract-ocr, tesseract-ocr-eng, tesseract-ocr-spa, libgomp1, fonts-dejavu-core, ca-certificates;
   - create non-root `zmi` UID/GID 10001;
   - create/chown `/data /cache /tmp`.
2. `runtime`
   - copy dependency metadata first;
   - install pinned runtime lock;
   - copy application source/resources;
   - install project `--no-deps`;
   - copy executable entrypoint;
   - USER zmi;
   - `EXPOSE 5000`;
   - healthcheck with Python urllib against 127.0.0.1:5000/api/status;
   - entrypoint then `transcript-dashboard`.
3. `test`
   - dev/test dependencies;
   - Chromium + Playwright dependencies;
   - remains separate from lean runtime image.

Runtime lock generation:
`uv pip compile pyproject.toml --extra studio -o requirements.runtime.lock.txt`

Do not bake models. Do not copy runtime env/config/data.

Dockerignore must exclude at minimum:
- .git
- .env / scan_config.env / projects.json / project_overrides.json / processed_files.json
- audio / Videos / Video_compress / CarpetaTranscripciones
- artifacts / screenshots / logs / caches
- watcher / deepseek
- local venvs / node_modules / __pycache__.

### WP-05 — Entrypoint + Compose

Create root `compose.yml`.

Entrypoint:
1. create `/data/{audio,Videos,Video_compress,CarpetaTranscripciones,logs,exports}`;
2. seed `/data/projects.json` from portable example only if absent;
3. never overwrite mounted state;
4. exec final command so SIGTERM reaches Python.

Compose service `zmi`:
- build runtime target;
- `127.0.0.1:${ZMI_PORT:-5000}:5000`;
- `${ZMI_DATA_PATH:-./zmi-data}:/data`;
- `zmi-model-cache:/cache`;
- tmpfs /tmp;
- env defaults from feature spec;
- optional `env_file: scan_config.env` only when file exists strategy is practical; otherwise document `--env-file` usage so first run does not fail because file is absent;
- read_only true;
- cap_drop ALL;
- no-new-privileges;
- restart unless-stopped;
- health dependency ready.

Do NOT mount source code in production compose.

Optional `compose.imports.yml.example` may document Icecream bind mounts; do not activate by default.

### WP-06 — Container deterministic harnesses

Create:
- `scripts/docker_gate.py` or equivalent deterministic runner;
- `tests/integration/test_docker_*.py` where appropriate;
- adapt E2E for env-driven URL/data root.

Named gates:
- `docker-config`
- `docker-build`
- `docker-smoke`
- `docker-persistence`
- `docker-asr-smoke`
- `docker-e2e`.

Gate behavior:
- each gate has bounded timeout;
- each emits compact JSON;
- each cleans only its isolated synthetic compose project/data;
- never `docker system prune`;
- never delete user volumes/data outside test project namespace.

Docker test project name:
`zmi-test-${BUILD_ID or deterministic local suffix}`.

### WP-07 — Playwright container behavior

Refactor E2E:
- `ZMI_BASE_URL` default remains `http://127.0.0.1:5000`;
- `ZMI_TEST_DATA_ROOT` default remains current repo root for host tests;
- all direct test fixture writes use test data root;
- no regression to current host E2E.

Docker E2E service:
- based on Dockerfile test target;
- `network_mode: service:zmi`;
- same test data mount;
- URL remains `http://127.0.0.1:5000`, preserving Host/Origin security;
- app must be healthy before Playwright begins.

Behavior checks:
1. dashboard loads;
2. synthetic file listed;
3. upload accepted;
4. edit modal loads transcript;
5. Project manual override save succeeds;
6. reload retains override;
7. switch back to Auto works;
8. documentation/framing UI works on synthetic tutorial fixture;
9. delete removes synthetic file;
10. no browser console/page errors for critical path.

### WP-08 — Real low-cost ASR container acceptance

Purpose: prove native ML/media stack actually works inside container without paying large-v3 download cost every build.

Flow:
1. generate deterministic 2–5 sec synthetic/fixture WAV with known spoken audio OR commit a tiny non-sensitive test audio fixture with appropriate provenance;
2. run with `WHISPER_MODEL=tiny`;
3. assert non-empty transcript + metadata;
4. confirm model files land under /cache;
5. restart/recreate and prove cache remains available.

Do not change default `WHISPER_MODEL=large-v3`.

If synthetic TTS would add another runtime dependency, prefer a tiny committed public-domain/generated audio fixture with documented provenance.

### WP-09 — Gate evidence aggregation

Modify:
- `scripts/gate_runner.py`;
- add `scripts/summarize_gates.py`;
- Jenkinsfile.

Gate runner:
- continue `latest.json` compatibility if needed;
- additionally persist `<gate>.json` under current build artifact directory;
- raw logs separate.

Aggregator:
- read only compact gate JSON;
- output `SUMMARY.json` + `SUMMARY.md`;
- no LLM/provider import/network call.

Jenkins final matrix:
1. targeted;
2. pytest full unit/integration;
3. quality;
4. security;
5. Docker config/build;
6. Docker smoke/persistence/ASR;
7. Playwright/E2E;
8. Sonar;
9. optional soak;
10. aggregate/archive/notify.

Jenkins must continue to final aggregation even when a gate fails so the summary shows all runnable gate statuses; later dependent tests may be SKIPPED with explicit reason.

### WP-10 — Email notification

Use Jenkins Email Extension only if configured by the owner/Jenkins host.

Post-build:
- generate summary first;
- archive artifacts;
- send one email whose body is SUMMARY.md;
- include Jenkins build URL;
- no giant logs/attachments by default.

If email plugin/SMTP is not configured:
- record `EMAIL_STATUS=NOT_CONFIGURED`;
- do not fail product correctness gates;
- archived summary remains source of truth.

### WP-11 — Documentation/security

Update:
- README;
- CONTRIBUTING;
- SECURITY;
- PRIVACY;
- THREAT_MODEL;
- DATA_FLOW;
- LOCAL-OPS;
- add `docs/DOCKER.md`;
- ADR for Docker local trust boundary.

README quick start:
```bash
docker compose up -d --build
# browse http://127.0.0.1:5000
```

Document:
- first model download;
- data/model cache paths;
- backup;
- update/rebuild;
- logs;
- offline behavior after cache warm-up;
- optional external LLM config;
- stop vs destructive delete;
- CPU/RAM expectations;
- Windows Docker Desktop notes.

### WP-12 — Closure

Run:
- targeted;
- full pytest;
- quality;
- security;
- smoke;
- host E2E;
- Docker config/build;
- Docker smoke;
- Docker persistence;
- Docker ASR smoke;
- Docker Playwright/E2E;
- Sonar when configured;
- optional 3x Docker E2E soak.

Then:
- commit/push;
- trigger Jenkins;
- local coder exits;
- owner + heavy model review compact evidence and Git diff.

## Prohibited implementation shortcuts

- Do not use old `watcher/docker-compose.yml`.
- Do not copy real `projects.json` into image.
- Do not expose `0.0.0.0:5000` on host.
- Do not bake large-v3 into image.
- Do not disable Host/Origin/token checks to make Docker E2E pass.
- Do not make root filesystem writable merely to hide path bugs.
- Do not use privileged container.
- Do not mount Docker socket.
- Do not add database/Redis.
- Do not let tests touch real user media.
