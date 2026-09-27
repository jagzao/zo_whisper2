# V4 Resilience Findings

Tracked evidence of runtime/environment failures that Project-lead V4 must
survive. Each finding records impact, detection, recovery, and prevention.

---

## F-V4-001 — Bun runtime crash truncates partial file writes

- **Date:** 2026-09-26
- **Context:** US-PLV4-001, WP-01 in progress on branch
  `feat/project-lead-v4-autonomous-delivery`.
- **Trigger:** the hosting agent runtime (Bun) crashed mid-session.
- **Impact (verified against `HEAD`):**
  - `.gitignore` was left truncated to 2 lines (a whole-file rewrite was
    interrupted). `HEAD` has 98 lines. Effect: `.env`, `scan_config.env`,
    `.sensitive-identifiers`, `projects.json` and many runtime artifacts became
    visible as untracked — a privacy exposure if staged by mistake.
  - `scripts/gate_runner.py` written but structurally incomplete: missing
    `import json`, missing `from pathlib import Path`, no
    `artifacts/gates/logs` directory creation, and reading gate reports from the
    wrong path.
  - `tests/test_gate_runner.py` written with a syntax error (line 56) and four
    non-functional tests.
- **Detection:** `git status` showed a large untracked surface; `git diff`
  on `.gitignore` showed 117 deletions vs 2 insertions; the new files failed
  import/py_compile.
- **Recovery (performed, no `reset`/`clean`/`checkout`):**
  - `.gitignore` restored byte-exact from `HEAD:.gitignore` via
    `git cat-file blob HEAD:.gitignore > .gitignore`, then `artifacts/` appended.
    Verified residual diff is exactly `+3` lines.
  - `gate_runner.py` / `test_gate_runner.py` rebuilt under WP-01.
  - All other working-tree state preserved untouched.
- **Prevention / V4 rule:** any host/runtime crash during a write is a
  resume event, not a restart. Rule: `LOAD_CHECKPOINT -> VERIFY_REPO_STATE`
  must include verifying that non-atomic whole-file writes (`.gitignore`,
  config, ignore rules) still match `HEAD` before trusting the tree. Prefer
  appending/editing over whole-file rewrite for ignore/config surfaces.
- **Owner intervention required:** none. Recovery derived from Git state.
