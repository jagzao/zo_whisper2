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

Dashboard uploads use resumable 4 MiB chunks and stay in `.upload_sessions`
until approved. Once the whole batch is uploaded, approve it to promote the
files into `zmi-data/Video_compress` or `zmi-data/audio` and start or queue
`Process pending`; declining leaves them staged. Up to two files upload at once.
Approved unfinished inputs resume when the container starts. Keep the phone
browser tab active during transfer; if mobile power management suspends it,
select the same files again to resume. Set
`UPLOAD_MAX_MB` in `scan_config.env` to allow files larger than the 500 MiB
default. Each 4 MiB checkpoint is flushed before the server advances its
offset. Pipeline jobs and lifecycle events persist in `processing_queue.sqlite3`
under the data root; one heavy job runs at a time, with up to three attempts.
`/api/status` exposes queue counts and jobs; `/api/events?after=<id>` returns
durable lifecycle events. The file Edit action can assign a project before a
transcript exists; manual assignments control compression routing. Compose
limits the service to 2 CPU by default; set `ZMI_CPUS` to change that ceiling.

## External LLM opt-in

External LLM calls are disabled by default. Keep `ALLOW_EXTERNAL_LLM=false` for local-only processing. To opt in for a specific local run, set `ALLOW_EXTERNAL_LLM=true` in your untracked Compose `.env` and configure the provider credentials/base URL in `zmi-data/scan_config.env`. Project classification, image-upload and frame-description safeguards still apply. Do not put API keys in the image or commit them.

The dashboard port is published on host interfaces for trusted LAN devices;
`DASHBOARD_ALLOWED_HOSTS` controls which Host/Origin values the app accepts.
Do not expose it beyond the trusted local network.

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
