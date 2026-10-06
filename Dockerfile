# syntax=docker/dockerfile:1
# PLAN-ZMI-DKR-001 — WP-04 Docker build contract.
#
# Stages:
#   base    — shared OS layer: Python 3.12 slim + ffmpeg/tesseract/libs + non-root user.
#   runtime — lean product image (default build target): locked third-party deps,
#             app installed --no-deps, non-root, /api/status healthcheck, dashboard CLI.
#   test    — runtime + dev/test deps + Chromium for Playwright; never shipped.
#
# Never bake: model weights, secrets, runtime env/config/data (see .dockerignore).

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base

# UTF-8 everywhere, unbuffered stdout/stderr (logs must stream), no pip cache.
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg provides both ffmpeg and ffprobe. Tesseract eng+spa backs the OCR
# vision extra. libgomp1 is required by ctranslate2 (faster-whisper).
# DejaVu covers OCR/PDF font rendering. ca-certificates for model downloads.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        fonts-dejavu-core \
        libgomp1 \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Fixed non-root identity; writable data/cache/tmp locations.
RUN groupadd --gid 10001 zmi \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin zmi \
    && mkdir -p /data /cache /tmp \
    && chown -R zmi:zmi /data /cache /tmp \
    && chmod 1777 /tmp

FROM base AS runtime
WORKDIR /app

# Dependency metadata first so the locked dependency install only re-runs
# when the pins change. README/LICENSE are required wheel-build inputs/metadata.
COPY pyproject.toml README.md LICENSE requirements.runtime.lock.txt ./
RUN pip install -r requirements.runtime.lock.txt

# Application source/resources, then the project itself without deps:
# every third-party pin already came from the lock above.
COPY src ./src
COPY projects.json.example ./
RUN pip install --no-deps .

# Entrypoint is chmod'd here so it works regardless of the checkout's exec bit.
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

# Writable data volume root (bind/named volume target in compose) and the
# model-cache root; huggingface defaults resolve under XDG_CACHE_HOME.
ENV ZMI_DATA_ROOT=/data \
    XDG_CACHE_HOME=/cache

USER zmi
EXPOSE 5000

# Real liveness probe: the dashboard must answer /api/status on loopback.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/api/status', timeout=4).getcode() == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["transcript-dashboard"]

FROM runtime AS test
# Dev/test dependencies from the repo-wide pinned lock (--extra all --extra dev).
# Kept out of the lean runtime image; this target exists for CI/E2E only.
USER root
COPY requirements.lock.txt ./
COPY scripts ./scripts
COPY tests ./tests
COPY docs/assets/generate_mock_data.py docs/assets/generate_mock_data.py
RUN pip install -r requirements.lock.txt

# Chromium for Playwright E2E. Browsers live in a shared path so any user
# can run them; --with-deps installs the browser's own OS libraries.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
