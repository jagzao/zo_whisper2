# FEATURE-ZMI-DKR-002 — Secure CPU Container Runtime

## Outcome

A user can run the product with `docker compose up -d` and reach the dashboard only from the same host.

## Runtime image

Target: `python:3.12-slim-bookworm` compatible CPU image.

System dependencies:
- FFmpeg / ffprobe;
- Tesseract OCR;
- English + Spanish Tesseract language packs;
- runtime native libraries required by CTranslate2/faster-whisper;
- basic fonts required by PDF output.

Image rules:
- no model download at build time;
- no secrets;
- non-root runtime user;
- lean `.[studio]` runtime dependency lock;
- production code only; exclude `watcher/`, `deepseek/`, local media, caches, Git metadata and artifacts;
- healthcheck uses `/api/status`.

## Compose contract

Service: `zmi`.

Required defaults:
- `ZMI_CONTAINER_MODE=true`;
- `ZMI_DATA_ROOT=/data`;
- `DASHBOARD_HOST=0.0.0.0`;
- `DASHBOARD_PORT=5000`;
- `ALLOW_EXTERNAL_LLM=false`;
- `HF_HOME=/cache/huggingface`;
- `XDG_CACHE_HOME=/cache`;
- `OMP_WAIT_POLICY=PASSIVE`.

Mounts:
- host-visible/bind runtime data: `${ZMI_DATA_PATH:-./zmi-data}:/data`;
- named model cache: `zmi-model-cache:/cache`;
- tmpfs: `/tmp`.

Network/security:
- publish only `127.0.0.1:${ZMI_PORT:-5000}:5000`;
- `cap_drop: [ALL]`;
- `security_opt: no-new-privileges:true`;
- read-only root filesystem when all required mutable paths have been externalized;
- never mount Docker socket.

Optional Icecream folders are opt-in Compose overrides/profile, not default mounts.

## Initialization

Entrypoint creates required runtime folders and seeds a portable `projects.json` from example only when the mounted data root has none. It must never overwrite user state.
