# US-ZMI-DKR-001 — Dockerize Zo Media Intelligence

## Status
`FROZEN_FOR_IMPLEMENTATION`

## Parent
`.agents/deliverables/EPIC-ZMI-DKR-001-docker-runtime.md`

## Source
`.agents/deliverables/AUDIT-ZMI-DKR-001-docker-readiness.md`

## User story

As a Zo Media Intelligence user/contributor, I want to start the complete local-first product with Docker Compose so that installation is reproducible, media/state/models survive container replacement, and the same behavior is proven by deterministic tests without exposing the dashboard to the network.

## Functional contract

### Runtime filesystem
1. Add `DATA_ROOT` controlled by `ZMI_DATA_ROOT`; default remains `PROJECT_ROOT`.
2. Runtime media/state/config/logs resolve from `DATA_ROOT`, not code root.
3. Existing host mode behaves exactly as before when Docker variables are unset.
4. Synthetic test/demo generators honor the same data root.
5. Relative project `output_path` values are portable and resolve beneath the runtime data area.
6. Host-mode legacy absolute `output_path` remains backward compatible.
7. Container mode refuses unsafe absolute output paths that are not explicitly mapped/allowed.

### Container bind/security
8. Normal host mode continues to reject non-loopback `DASHBOARD_HOST`.
9. `ZMI_CONTAINER_MODE=true` permits internal `0.0.0.0` bind.
10. Production Compose publishes the port only on host loopback.
11. Existing Host/Origin/token protections remain enabled.
12. Container runs as a non-root user with no extra Linux capabilities and no-new-privileges.
13. Root filesystem is read-only after all required runtime write locations are externalized; `/tmp` is tmpfs.
14. No API keys, local env files, real media, transcripts or model weights are copied into image layers.

### Product runtime image
15. Root Dockerfile provides a CPU runtime based on Python 3.12 slim.
16. Runtime includes FFmpeg/ffprobe and Tesseract eng/spa.
17. Runtime installs a pinned `.[studio]` dependency set.
18. faster-whisper model weights are downloaded at runtime to a persistent cache, never baked into the image.
19. Runtime healthcheck calls the actual dashboard status endpoint.
20. `watcher/` and `deepseek/` are excluded from the production build context.

### Compose
21. `docker compose up -d` starts the product with safe defaults.
22. Runtime data is visible/persistent through `${ZMI_DATA_PATH:-./zmi-data}:/data`.
23. Model/cache data persists in a named volume.
24. External LLM remains disabled unless the user explicitly enables it.
25. Icecream source folders are optional/disabled by default.

### Pipeline portability
26. Dashboard-triggered compression/transcription uses installed package modules through `sys.executable -m`, not repo-root script names.
27. Logs write to persistent runtime log directory and stdout.
28. Container recreation does not lose project config, overrides, processed state, transcripts, docs or model cache.

## Validation contract

29. Existing unit/integration/security suites remain green.
30. Add unit tests for `DATA_ROOT`, config/env path behavior, container bind validation and relative output resolution.
31. Add Docker config/build deterministic gate.
32. Add container smoke proving health, non-root user, binaries, safe defaults and writable mounts.
33. Add persistence test across container recreation.
34. Add a low-cost real ASR container test using a tiny test-only Whisper model and synthetic audio.
35. Adapt Playwright E2E to a configurable base URL/data root and validate the running Compose service.
36. E2E must cover at least upload/list/open/edit Project/persist/reload/documentation view/delete behavior using synthetic data.
37. Add restart/recreation behavior test proving fresh in-memory run state.
38. Docker tests never read/write the maintainer's real media directories.
39. Jenkins runs the full frozen matrix and creates compact per-gate result JSON.
40. Jenkins creates `SUMMARY.json` + `SUMMARY.md` and archives raw logs/traces separately.
41. When email is configured, Jenkins sends one final compact result email; no LLM waits for it.
42. Local coding agent terminates after commit/push + Jenkins trigger.

## Quality/non-functional

43. Image build should use Docker layer caching efficiently: dependency installation invalidates only when dependency metadata changes, not on every source edit.
44. Image must not contain `.git`, `.env`, `scan_config.env`, `projects.json`, runtime media, test screenshots/artifacts, `watcher/`, or `deepseek/`.
45. `docker compose down` does not delete runtime data/model cache; destructive deletion requires explicit volume/data removal.
46. Documentation covers first run, model download/cache, host-local URL, data location, backup, stop/start/update and troubleshooting.
47. Threat model/PRIVACY docs explicitly state that Docker is still local-first and not an internet-facing deployment mode.

## Non-goals

- CUDA/GPU image.
- Parakeet Redux.
- multi-user authentication.
- Kubernetes.
- Redis/Celery.
- remote cloud deployment.
- revival of experimental stacks.
- SOC 2.

## Definition of Done

All applicable AC are implemented, deterministic gates are green, Jenkins evidence is produced, no P0/P1 from AUDIT-ZMI-DKR-001 remains, and final state is `READY_FOR_OWNER_AUDIT`.

## Owner interaction budget

1. INITIAL_SPEC — complete in this analysis.
2. FINAL_ACCEPTANCE — owner downloads/pulls final branch and performs the final Docker product test.

Any extra interaction is a documented exception, not normal execution.
