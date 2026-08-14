# Security Policy

## Supported versions

This is a local-first, single-maintainer project (not a hosted service).
Security fixes land on `main`; there is no separate LTS branch. Pull the
latest `main` to get fixes.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security vulnerability.
Instead, use GitHub's private vulnerability reporting (Security tab →
"Report a vulnerability") on this repository, or contact the maintainer
directly through the contact information on their GitHub profile.

Include:
- A description of the issue and its impact.
- Steps to reproduce (a minimal repro is very helpful).
- The affected version/commit.

There is no bug bounty. Reasonable time will be given to fix an issue before
any public disclosure, coordinated with the reporter.

## Threat model summary

Full detail: [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

This is a **local-first** tool. The primary trust boundary is the dashboard
(Flask), which:
- Must bind to a loopback address (`DASHBOARD_HOST` — `127.0.0.1`/
  `localhost`/`::1`). A non-loopback value raises `ConfigurationError` at
  startup; there is no remote-mode override. This is a deliberate,
  permanent design choice, not a temporary limitation.
- Has **no user-account authentication** (by design — single-user, local
  tool). It does enforce a same-machine boundary: a `before_request` hook
  rejects requests with a non-loopback Host header, and mutating requests
  (upload/delete/save/run) additionally require a matching Origin (when
  present) and a per-process token (`X-Local-Dashboard-Token`, generated
  fresh at startup, never persisted or logged) — so an unrelated browser
  tab or local process can't drive the dashboard just by knowing the port.
  This is not equivalent to a login system; anyone with shell access to
  this machine can read the token from the running process regardless.
- Constrains all filesystem access to a fixed set of allowed roots
  (`audio/`, `Videos/`, `Video_compress/`, `CarpetaTranscripciones/`) via
  `SafePathResolver` (`src/transcript_pipeline/security/path_resolver.py`),
  exposed to the frontend only as opaque `media_id`s (never an absolute
  path) — see `tests/security/` for the regression suite covering path
  traversal, absolute paths, symlink escape, and the Host/Origin/token
  checks.

## Secrets policy

- Never commit `.env`, `scan_config.env`, `projects.json`, or any file
  containing a real API key, token, or credential. `.gitignore` already
  excludes these; `scripts/security.py` and CI's `gitleaks` step scan for
  accidental commits.
- `LLM_API_KEY` and any other credential belong in `scan_config.env`
  (gitignored) — never in `projects.json` or code.
- If a credential is ever committed, treat it as compromised: rotate it,
  then follow [`docs/GIT_HISTORY_CLEANUP.md`](docs/GIT_HISTORY_CLEANUP.md)
  to scrub history. Removing it from history does not undo the exposure —
  rotation is what actually matters.

## Data handling

See [`PRIVACY.md`](PRIVACY.md) for what data this tool processes, what stays
local, and what can leave the machine (only the optional LLM enrichment
layer, gated by `ALLOW_EXTERNAL_LLM` and per-project `data_classification`,
off by default).

## Responsible disclosure

If you find a vulnerability, please give a reasonable window to fix it
before public disclosure. Findings that are already public (e.g. a known CVE
in a pinned dependency, surfaced by `pip-audit`/Dependabot) don't need
private reporting — a PR or issue is fine.

## Security testing in this repo

- `tests/security/` — pytest regression suite: path traversal, absolute
  paths (Windows/Unix), sibling-prefix bypass, symlink escape, upload
  validation, privacy-default assertions, malformed project-config rejection.
- `scripts/security.py` — CI gate: committed-secret scan, `.gitignore`
  coverage for `.env`, the `tests/security/` suite, `pip-audit`.
- `.gitleaks.toml` + `gitleaks-action` — secret scanning in CI, independent
  of the regex checks in `scripts/security.py`.
- None of these gates report PASS when the underlying tool isn't installed
  — see `scripts/quality.py`/`scripts/security.py` for the explicit
  fail-closed behavior.
