# deepseek/ — experimental, not part of the production pipeline

A standalone FastAPI microservice (Dockerized) wrapping a local DeepSeek
model. It is not imported by `src/transcript_pipeline/` and not part of the
`RUN_MAX_QUALITY.bat` daily workflow — it has its own `requirements.txt`,
its own `.env`, and its own Docker Compose setup, fully independent of the
root `pyproject.toml`.

## Docker commands (reference)

```sh
# Remove previous containers
docker compose down

# Rebuild from scratch — needed for requirements.txt changes
docker compose build --no-cache

# Rebuild only your .py changes (requirements.txt unchanged)
docker compose up --build

# Start with the current build
docker compose up
```

## If you want to revive this

Treat it as a separate project from the main pipeline: it would need its
own CI and its own security review (it currently imports
`watcher/core/integration/llm_client.py`, which still exists for this
reason even though the production pipeline no longer uses it — see
`watcher/README.md`).
