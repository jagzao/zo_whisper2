"""T48: cert/token provisioning CLI — paths and fingerprint only, token gated."""

from __future__ import annotations

import re

from transcript_pipeline.kab_ingest.cli import cert_main
from transcript_pipeline.kab_ingest.certs import TOKEN_BYTES, provision
from tests.kab_ingest_utils import TEST_TOKEN


def test_t48_cert_cli_prints_paths_and_fingerprint_only(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    assert cert_main(["--runtime-dir", str(runtime)]) == 0
    out = capsys.readouterr().out
    assert "cert:" in out
    assert "fingerprint-sha256:" in out
    assert "token-file:" in out
    assert "token:" not in out
    assert TEST_TOKEN not in out
    for line in out.splitlines():
        if line.startswith("fingerprint-sha256:"):
            fingerprint = line.split(":", 1)[1].strip()
            assert re.fullmatch(r"([0-9a-f]{2}:){31}[0-9a-f]{2}", fingerprint)

    assert (runtime / "kab-ingest-cert.pem").is_file()
    assert (runtime / "kab-ingest-key.pem").is_file()
    token_file = runtime / "kab-ingest-token"
    assert token_file.is_file()
    token = token_file.read_text(encoding="utf-8").strip()
    assert len(token) >= TOKEN_BYTES


def test_t48_show_token_is_explicit_opt_in(tmp_path, capsys):
    runtime = tmp_path / "runtime"
    assert cert_main(["--runtime-dir", str(runtime), "--show-token"]) == 0
    out = capsys.readouterr().out
    token_file_token = (runtime / "kab-ingest-token").read_text(encoding="utf-8").strip()
    assert f"token: {token_file_token}" in out


def test_t48_provision_is_idempotent_and_runtime_stays_out_of_git(tmp_path):
    from pathlib import Path

    first = provision(tmp_path / "runtime")
    second = provision(tmp_path / "runtime")
    assert first.token == second.token
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first.token and len(first.token) >= TOKEN_BYTES
    assert first.cert_path.parent == tmp_path / "runtime"

    repo_gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    assert "kab-inbox/" in repo_gitignore.read_text(encoding="utf-8")
