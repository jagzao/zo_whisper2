# Contributing

## Environment setup

```
pip install -e ".[dev]"
```

This installs the package in editable mode plus dev tooling (pytest,
playwright, ruff, pyright, pip-audit). Python 3.10+ (the venv used for
daily development is Python 3.12+, resolved by `RUN_MAX_QUALITY.bat` in
this order: `watcher\venv\Scripts\python.exe` → miniconda → system `PATH`).

For a reproducible install matching exactly what CI uses, see
`requirements.lock.txt` (regenerate with `uv pip compile pyproject.toml
--extra dev -o requirements.lock.txt`).

## Running tests

```
pytest tests/ -v                    # unit + security + integration
pytest tests/security/ -v           # path traversal, upload, privacy defaults
pytest tests/integration/ -v        # handler <-> HandlerResult <-> FileTracker contract
```

`tests/e2e/smoke_dashboard.py` is Playwright-based and not part of the
default `pytest` run — see `scripts/e2e.py`, which generates synthetic mock
data first (`docs/assets/generate_mock_data.py`), then drives the dashboard
in a real browser. Never run E2E against real recordings or real
`projects.json` — always the `.example` + generated mock data.

## Quality gates

Run the same harnesses CI runs:

```
python scripts/quality.py     # syntax, import sanity, ruff, pyright
python scripts/security.py    # secret scan, tests/security/, pip-audit
python scripts/ut.py          # pytest tests/
python scripts/run_harness.py # all of the above in sequence
```

These are **fail-closed**: if `ruff`, `pyright`, or `pip-audit` aren't
installed, the corresponding check reports FAIL rather than silently
passing. Install dev extras first.

## Security expectations

- Any endpoint or code path that touches the filesystem based on
  user/browser input must go through `SafePathResolver`
  (`src/transcript_pipeline/security/`) — see
  `docs/adr/0002-safe-filesystem-boundary.md`.
- Any code path that can send content to an external service must go
  through `PrivacyGuard.check()` (`src/transcript_pipeline/llm/guard.py`)
  first — see `docs/adr/0001-local-first-privacy.md` and
  `docs/adr/0003-external-llm-opt-in.md`.
- New endpoints/features with either of the above need a corresponding
  test in `tests/security/`.
- Never commit `.env`, `scan_config.env`, `projects.json`, real API keys,
  real recordings, real transcripts, or real client/personal names.
  `scripts/security.py` and CI's `gitleaks` step catch obvious cases, but
  review your own diff first.

## Fixture policy

- `projects.json.example`, `scan_config.env.example`: synthetic project
  names only (Northwind, Contoso, Fabrikam, Adventure Works — see existing
  examples for the established convention).
- `docs/assets/generate_mock_data.py` / `generate_screenshots.py`: the only
  source of public screenshots and demo data. Never commit a manually
  captured screenshot of real data.
- Tests use `tmp_path` for anything touching the filesystem — no test
  should depend on a real local path or a real `projects.json`.

## PR expectations

- Type hints on new code; avoid side effects at module import time (see
  `docs/adr/0002-safe-filesystem-boundary.md`'s neighbor concern: a library
  module must never `sys.exit()` or block on import).
- Keep changes scoped — this repo intentionally stays a single-process,
  local-first tool (see "What this project deliberately doesn't do" in
  `README.md`); don't introduce a database, message queue, or
  containerized service stack to solve a problem `SafePathResolver`,
  `Settings`, or a `dataclass` already solves.
- Run `python scripts/run_harness.py` before opening a PR.
- Describe *why* in the PR description, not just *what* — the diff already
  shows what changed.
