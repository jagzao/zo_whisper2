# AUDIT-ZMI-DKR-001 — Docker Readiness Audit

## Snapshot

Audit target: Zo Media Intelligence production application only.

Base: `feat/zmi-final-completion` at `4e1691c43c5d56b64e8f7d1e9d0959afd75ffeaa`.

Deployment target:
- Linux container, CPU-first.
- Windows Docker Desktop and Linux Docker Engine as supported hosts.
- Browser access remains host-local by default.
- `watcher/` and `deepseek/` are explicitly excluded from the production container.

## Current state

The root production application has no Dockerfile, root Docker Compose file, container health contract, container-specific data-root abstraction, or container E2E path.

There are old Docker artifacts under `watcher/` and `deepseek/`, but those trees are documented as experimental and are not imported by `src/transcript_pipeline/`. They MUST NOT be used as the production Docker design.

The current application is portable Python, but several assumptions bind runtime state to the checked-out repository and Windows/local-host execution.

## Findings

### P0 — Docker blockers

#### BUG-DKR-001 — dashboard cannot bind inside a normal container
`Settings._validate()` rejects every non-loopback `DASHBOARD_HOST`, while a container must bind to `0.0.0.0` internally for Docker port publishing to work.

Required design:
- default non-container behavior remains loopback-only;
- `ZMI_CONTAINER_MODE=true` permits internal bind `0.0.0.0`;
- Docker Compose publishes only `127.0.0.1:${ZMI_PORT}:5000`;
- Host/Origin validation remains loopback-focused for normal browser traffic;
- no public-network mode is introduced.

#### TECHDEBT-DKR-001 — code root and mutable data root are the same thing
`config.py` derives audio, videos, transcriptions, projects config, processed state and scan config from `PROJECT_ROOT`.

In a container, code should be immutable while media/state is persistent.

Required design:
- retain `PROJECT_ROOT` for application code;
- introduce `DATA_ROOT` from `ZMI_DATA_ROOT`, defaulting to `PROJECT_ROOT` for backward compatibility;
- move runtime directories/state constants to `DATA_ROOT`;
- support an optional `ZMI_CONFIG_ENV` path;
- production container uses `/data`.

#### BUG-DKR-002 — logs write into the application source tree
`configure_logging()` writes log files under `PROJECT_ROOT`.

Required:
- `LOG_DIR` under `DATA_ROOT/logs` by default;
- stdout remains enabled for Docker logs;
- log directory is created explicitly.

#### TECHDEBT-DKR-002 — dashboard subprocess execution depends on repo-root scripts/cwd
The dashboard launches `compress_and_move.py` and `master_processor.py` from `ROOT`.

Required:
- use `sys.executable -m transcript_pipeline.media.compressor`;
- use `sys.executable -m transcript_pipeline.pipeline.master`;
- remove special interpreter discovery in favor of the interpreter already running the dashboard.

This keeps host mode and container mode on the same installed package surface.

#### BUG-DKR-003 — public project examples contain Windows-only output paths
`projects.json.example` includes `C:/...` output paths.

Required:
- example config becomes OS-neutral;
- relative output paths resolve beneath the runtime data root/export root;
- existing absolute paths remain supported for host-mode backward compatibility;
- container mode must not silently write outside mounted/persistent data.

#### GAP-DKR-001 — no production container image
Required:
- root `Dockerfile`;
- root `.dockerignore`;
- CPU runtime with Python 3.12;
- FFmpeg/ffprobe;
- Tesseract OCR with English + Spanish language data;
- required runtime shared libraries;
- non-root user;
- no model weights or secrets baked into the image;
- explicit `HEALTHCHECK`.

#### GAP-DKR-002 — no production Docker Compose contract
Required:
- root `compose.yml`;
- host-local port publishing only;
- bind-mounted persistent data;
- persistent Hugging Face/model cache;
- tmpfs for temporary work;
- external LLM off by default;
- optional Icecream import mounts disabled by default.

### P1 — required for reliable Docker delivery

#### GAP-DKR-003 — model cache is not explicitly persistent
faster-whisper model downloads must survive image/container replacement.

Required:
- `HF_HOME=/cache/huggingface`;
- `XDG_CACHE_HOME=/cache`;
- persistent `zmi-model-cache` volume;
- model is downloaded on first use, not during image build.

#### GAP-DKR-004 — no container-level behavioral acceptance
Existing smoke/E2E primarily validate a host process.

Required deterministic tests:
- image builds;
- container becomes healthy;
- dashboard is reachable through the host-local mapped port;
- filesystem state persists across container recreation;
- model cache persists;
- FFmpeg/ffprobe available;
- Tesseract available;
- synthetic upload/edit/project/doc flows work;
- Playwright validates the running container;
- container stop/start does not fabricate run state;
- container runs non-root.

#### GAP-DKR-005 — E2E assumes localhost and repo-relative mutable directories
`tests/e2e/smoke_dashboard.py` hardcodes `http://127.0.0.1:5000` and writes directly to `Videos/` / `CarpetaTranscripciones/`.

Required:
- configurable `ZMI_BASE_URL`;
- configurable test data root;
- Docker E2E executes in a test container sharing the app service network namespace (`network_mode: service:zmi`) so existing loopback Host security remains intact;
- test data remains synthetic.

#### GAP-DKR-006 — synthetic data generators are repo-root-coupled
`generate_mock_data.py` and cleanup scripts write to repo-root data directories.

Required:
- honor the same `DATA_ROOT` abstraction;
- never touch maintainer real data during Docker tests.

#### TECHDEBT-DKR-003 — runtime dependency lock includes all/dev packages
`requirements.lock.txt` was compiled with `--extra all --extra dev`, making it unsuitable as the lean production image contract.

Required:
- add a pinned runtime lock generated for `.[studio]`;
- Docker runtime installs pinned runtime dependencies, then package with `--no-deps`;
- test image may use the existing dev/all lock or a dedicated test lock.

#### GAP-DKR-007 — Docker image security contract is missing
Required:
- non-root UID/GID;
- `cap_drop: ALL`;
- `no-new-privileges`;
- read-only root filesystem where practical;
- writable `/data`, `/cache`, and tmpfs `/tmp`;
- no Docker socket mount;
- no secrets in image layers;
- only localhost port publication.

### P1 — delivery/test workflow blockers

#### BUG-DKR-004 — Jenkins does not represent the complete requested test matrix
Current Jenkins stages do not explicitly execute full unit/integration + smoke as distinct release gates and do not aggregate all gate outcomes.

Required matrix:
- targeted;
- unit/integration pytest;
- quality;
- security;
- container build/config;
- container smoke;
- Playwright behavior;
- E2E;
- SonarQube when configured;
- optional soak.

#### TECHDEBT-DKR-004 — gate runner overwrites a single `latest.json`
The desired review workflow needs one compact result per gate plus one aggregate build summary.

Required:
```
artifacts/US-ZMI-DKR-001/<build>/
  SUMMARY.json
  SUMMARY.md
  targeted.json
  pytest.json
  quality.json
  security.json
  docker-build.json
  docker-smoke.json
  playwright.json
  e2e.json
  sonar.json
```

Raw logs/traces remain Jenkins artifacts and are inspected only on demand.

#### GAP-DKR-008 — no single completion notification
Required:
- Jenkins generates `SUMMARY.json` and `SUMMARY.md`;
- one final email is sent after the whole pipeline finishes when Jenkins email is configured;
- email contains only compact gate results and artifact/build link;
- the coding LLM never waits for or reads the full logs.

### P2 — useful but not first-container blockers

#### TECHDEBT-DKR-005 — Flask development server remains the runtime server
For this local-only, single-user product this is acceptable for the first Docker release if the port stays host-local. A future feature may evaluate a single-worker threaded WSGI server, but multi-worker deployment must not be introduced while run state and locks are in-memory.

#### TECHDEBT-DKR-006 — absolute path keys remain in processed_files.json
Hash keys make normal migration tolerant, but legacy path-only entries may not match after Windows-host -> Linux-container migration.

Future:
- state migration/normalization utility;
- prefer portable media IDs over absolute-path aliases.

#### TECHDEBT-DKR-007 — container image vulnerability/SBOM automation
Post-first-container hardening:
- Trivy or equivalent image CVE scan;
- CycloneDX/Syft SBOM;
- optional signed image provenance.

### P3 — explicitly out of scope

- Kubernetes.
- Redis/Celery/job queues.
- multi-user authentication.
- internet-facing hosting.
- GPU/CUDA Docker image.
- reviving `watcher/` or `deepseek/`.
- Parakeet Redux integration.
- SOC 2 certification.

## Architectural decision

The first Docker release stays a single-machine, local-first product.

```
Browser on host
    |
127.0.0.1:${ZMI_PORT}
    |
Docker publish boundary
    |
0.0.0.0:5000 inside container
    |
Zo Media Intelligence
    |-- /data   persistent media/state/logs
    |-- /cache  persistent model cache
    |-- /tmp    ephemeral tmpfs
```

Docker changes packaging and isolation only; it does not change the product trust model into a remote web service.
