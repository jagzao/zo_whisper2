# FEATURE-ZMI-DKR-003 — Container Behavioral Validation

## Outcome

Docker support is proven by executable behavior, not by a successful image build alone.

## Deterministic acceptance layers

1. Docker static/config
   - Dockerfile parses/builds.
   - `docker compose config` succeeds.
   - runtime image excludes secret/config/media files.

2. Runtime smoke
   - container starts healthy;
   - process runs non-root;
   - ffmpeg + ffprobe are executable;
   - tesseract is executable with eng/spa;
   - `/api/status` responds;
   - external LLM default is false.

3. Persistence
   - write synthetic media/config/state under mounted `/data`;
   - recreate container;
   - state/media remain;
   - run state is fresh, not fabricated as running.

4. Model/cache
   - tiny-model synthetic ASR acceptance downloads/loads a small model;
   - transcription result is non-empty;
   - model cache exists on persistent cache volume;
   - second container run reuses persistent cache.
   - `large-v3` remains the product default; the tiny model is test-only to keep validation economical.

5. Playwright behavior
   - E2E base URL configurable;
   - test container shares app network namespace (`network_mode: service:zmi`) and accesses loopback;
   - validate upload/list/edit project persistence/documentation view/delete using synthetic data;
   - existing local Host/Origin protections remain enabled.

6. Security regression
   - path traversal tests under `DATA_ROOT`;
   - non-container `DASHBOARD_HOST=0.0.0.0` still fails;
   - container mode allows internal bind only;
   - host port publication remains loopback in Compose.

## Supported host acceptance

Required:
- Linux Docker Engine amd64;
- Windows Docker Desktop using Linux containers.

macOS/arm64 can remain best-effort until separately validated.
