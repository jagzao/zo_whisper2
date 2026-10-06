# Docker local runtime

## Start

Requirements: Docker Engine or Docker Desktop with Compose v2. From the repository root:

```bash
docker compose up -d --build
# Open http://127.0.0.1:5000
```

The published port is bound to host loopback. This runtime is for the same machine; it is not an internet-facing deployment. The first transcription downloads the selected faster-whisper model and can take several minutes. Model weights are stored in the named `zmi-model-cache` volume, not in the image.

## Persistent files and backup

By default, mutable app data is in `./zmi-data/` and model weights are in the named Docker volume `zmi-model-cache`. `ZMI_DATA_PATH` changes the host data directory; create it first and ensure Docker Desktop can access it. Project configuration, manual overrides, processed-file state, transcripts, generated docs, logs and exports are kept under that data root. Docker Desktop on Windows stores bind-mounted files at the selected Windows path; use a path shared with Docker Desktop.

Stop and resume without deleting data:

```bash
docker compose stop
docker compose start
```

Recreate/update the image while keeping data and cache:

```bash
docker compose down
docker compose up -d --build
```

Back up `zmi-data` and the named model cache before destructive maintenance. `docker compose down -v` deletes the Compose model-cache volume; deleting the data directory removes media, settings, transcripts, documents and logs. These deletion steps are intentionally separate from normal stop/update commands.

To choose a data directory, set `ZMI_DATA_PATH` in the shell or a local Compose `.env` file. For example:

```dotenv
ZMI_DATA_PATH=./zmi-data
ZMI_PORT=5000
```

Copy `scan_config.env.example` to `zmi-data/scan_config.env` to set app configuration. Compose loads that optional mounted file through `ZMI_CONFIG_ENV`; it is not copied into the image. Keep credentials and private configuration out of source control.

## External LLM opt-in

External LLM calls are disabled by default. Keep `ALLOW_EXTERNAL_LLM=false` for local-only processing. To opt in for a specific local run, set `ALLOW_EXTERNAL_LLM=true` in your untracked Compose `.env` and configure the provider credentials/base URL in `zmi-data/scan_config.env`. Project classification, image-upload and frame-description safeguards still apply. Do not put API keys in the image or commit them.

The dashboard is published only on `127.0.0.1`; its Host, Origin and mutation-token protections remain active inside the container. Do not edit the port mapping to `0.0.0.0` as a way to expose this local product.

## CPU, memory and offline use

The runtime image is CPU-only. Transcription speed and peak memory depend on the selected Whisper model and media duration; `large-v3` uses substantially more memory and time than `tiny`. FFmpeg and Tesseract also use CPU while processing. For a laptop or small workstation, use a smaller model if latency or memory pressure is a problem. Docker Desktop memory limits apply to the container.

After a model is downloaded, that model can be loaded from the persistent cache without downloading its weights again. Network access may still be needed for optional remote LLMs or other explicitly configured integrations.

## Operations and diagnostics

```bash
docker compose ps
docker compose logs --tail=200 zmi
docker compose restart zmi
docker compose down
```

The application writes persistent logs under `zmi-data/logs` and streams logs to Docker stdout. Check `docker compose ps` health status and `/api/status` when diagnosing startup. The root filesystem is read-only; `/tmp` is temporary, `/data` is persistent state, and `/cache` is the model cache.

Optional Icecream project-source mounts are documented in [`compose.imports.yml.example`](../compose.imports.yml.example); they are disabled by default.
