# Usar imagen base optimizada compartida
FROM whisper-base as base

# Instalar dependencias específicas del watcher
RUN apt-get update && apt-get install -y libmagic1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir \
    watchdog \
    python-dotenv \
    requests \
    openai \
    python-magic \
    redis \
    pytest \
    pytest-asyncio \
    structlog \
    colorlog \
    psycopg2-binary \
    schedule \
    flask \
    psutil

# Copiar todo el watcher
COPY . /app/

# Crear directorios necesarios
RUN mkdir -p /app/logs /app/data

ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ps aux | grep watcher_and_processor.py || exit 1

CMD ["python", "services/watcher_and_processor.py"]
