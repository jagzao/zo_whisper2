# ADR 0006 — Docker preserves the local-only trust boundary

## Status

Accepted for EPIC-ZMI-DKR-001.

## Context

Zo Media Intelligence currently binds the Flask dashboard to loopback and validates request Host/Origin values accordingly. Docker networking requires a process inside a container to bind to a container interface such as `0.0.0.0` for host port publishing.

Treating that internal bind as permission to expose the product to a LAN/Internet would silently change the threat model. The dashboard is single-user and has no account authentication.

## Decision

Docker mode separates **internal process bind** from **host exposure**.

- Host mode remains loopback-only.
- Container mode may bind `0.0.0.0:5000` internally.
- Production Compose publishes only `127.0.0.1:<port>:5000`.
- Existing per-process dashboard token and Host/Origin checks remain enabled.
- Docker E2E shares the app network namespace and uses loopback; security is not disabled for tests.
- No reverse proxy, public hostname or remote auth mode is introduced.
- Remote deployment requires a separate future architecture/security decision.

## Data boundary

Container writable state is limited to explicit mounts:
- `/data` — media, transcriptions, project state and logs;
- `/cache` — model/application caches;
- `/tmp` — ephemeral tmpfs.

Application code/root filesystem is read-only in the production Compose contract.

## Consequences

Positive:
- reproducible install without weakening localhost security;
- explicit persistence/backup boundary;
- safer image/container permissions;
- host and container execution share the same application package.

Trade-offs:
- container cannot be treated as a ready-made remote SaaS;
- external host folders require explicit mounts;
- old absolute Windows output paths require migration/portable relative config for Docker use.
