"""CLI entry points for the K'ab ingest ([project.scripts] in pyproject).

- transcript-kab-ingest         run the TLS receiver (refuses unsafe config)
- transcript-kab-ingest-worker  run the local processing worker
- transcript-kab-ingest-cert    provision self-signed cert/key + bearer token

The cert CLI prints the cert path, its SHA-256 fingerprint and the token
*path* only; the token value is printed solely when --show-token is passed
explicitly. Nothing here performs network I/O.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcript-kab-ingest",
        description="Run the K'ab local ingest TLS receiver (KAB_INGEST_* config).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the configured posture and exit without serving",
    )
    return parser


def serve_main(argv: list[str] | None = None) -> int:
    args = _serve_parser().parse_args(argv)
    from transcript_pipeline.errors import ConfigurationError
    from transcript_pipeline.kab_ingest.server import run_server
    from transcript_pipeline.kab_ingest.settings import KabIngestSettings

    settings = KabIngestSettings.from_env()
    try:
        settings.validate_for_server()
    except ConfigurationError as exc:
        print(f"[kab-ingest] refusing to start: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print("[kab-ingest] configuration OK (receiver not started)")
        return 0
    return run_server(settings)


def worker_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transcript-kab-ingest-worker",
        description="Run the K'ab local ingest worker (scan ready/, transcribe, consolidate).",
    )
    parser.add_argument("--once", action="store_true", help="run a single scan pass and exit")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="seconds between scans (default 5)")
    args = parser.parse_args(argv)

    from transcript_pipeline.config import DATA_ROOT
    from transcript_pipeline.kab_ingest.settings import KabIngestSettings
    from transcript_pipeline.kab_ingest.store import SessionStore
    from transcript_pipeline.kab_ingest.worker import KabIngestWorker

    settings = KabIngestSettings.from_env()
    store = SessionStore(
        settings.storage_root(),
        max_chunk_bytes=settings.max_chunk_bytes,
        max_session_bytes=settings.max_session_bytes,
    )
    worker = KabIngestWorker(store, DATA_ROOT, poll_seconds=max(args.poll_seconds, 0.1))
    if args.once:
        processed = worker.run_once()
        print(f"[kab-ingest-worker] pass complete ({processed} segment(s) finished)")
        return 0
    worker.run_forever()
    return 0


def cert_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transcript-kab-ingest-cert",
        description="Provision the local self-signed TLS cert/key and high-entropy bearer token.",
    )
    parser.add_argument(
        "--runtime-dir",
        type=str,
        default=None,
        help="runtime directory (default: <KAB_INGEST_ROOT or DATA_ROOT/kab-inbox>/.runtime) — kept outside Git",
    )
    parser.add_argument(
        "--show-token",
        action="store_true",
        help="print the bearer token value (default: only the token file path is printed)",
    )
    args = parser.parse_args(argv)

    from transcript_pipeline.kab_ingest.certs import provision
    from transcript_pipeline.kab_ingest.settings import KabIngestSettings

    settings = KabIngestSettings.from_env()
    runtime_dir = (
        Path(args.runtime_dir)
        if args.runtime_dir
        else settings.storage_root() / ".runtime"
    )
    result = provision(runtime_dir)
    print(f"cert: {result.cert_path}")
    print(f"fingerprint-sha256: {result.fingerprint_sha256}")
    print(f"token-file: {result.token_path}")
    if args.show_token:
        print(f"token: {result.token}")
    return 0
