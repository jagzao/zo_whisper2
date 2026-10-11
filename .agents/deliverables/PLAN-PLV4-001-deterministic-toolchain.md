# PLAN-PLV4-001 — Deterministic Delivery Toolchain

## Parent
- US: `.agents/deliverables/US-PLV4-001-deterministic-toolchain.md`
- EPIC: `.agents/deliverables/EPIC-PLV4-autonomous-delivery.md`

## Frozen spec authority
This PLAN implements the frozen US. It does not change product scope.
If implementation reveals a contradiction, stop with `SPEC_CONFLICT`.

## Baseline evidence (branch `feat/project-lead-v4-autonomous-delivery` @ dc8f01d)
- `pytest tests/ -q` -> 313 passed, 1 skipped
- `python scripts/quality.py` -> PASS
- `python scripts/smoke.py` -> PASS
- `python scripts/security.py` -> FAIL
- `no_denylisted_identifiers`: a private identifier in tracked `.agents/protocols/deterministic-gates.md` (introduced by this branch; also in history)
  - `dependency_audit`: venv drift (anyio 4.14.0, soupsieve 2.8.4). Lock already pins anyio==4.14.2, soupsieve==2.9.2.
- `python scripts/e2e.py` -> FAIL: no synthetic seed data present
- `.github/workflows/` absent by policy (zero-cost CI). `docs/ops/LOCAL-OPS.md` documents local equivalents.

## Impacted components
- `scripts/` (new gate runner)
- `tests/` (new deterministic tests)
- `.gitignore` (runtime artifacts)
- repo root (`Jenkinsfile`, `sonar-project.properties`)
- `.agents/protocols/` (provider alias mapping; no secrets)
- `docs/ops/LOCAL-OPS.md` (UI validation adapter note)
- `.agents/protocols/deterministic-gates.md` (sanitize leaked token)

## Work packages

### WP-01 — Compact deterministic gate runner + no-LLM proof (AC-1, AC-2, AC-6, AC-7) — COMPLETE
- New `scripts/gate_runner.py`:
  - registry of named gates: `pytest`, `quality`, `security`, `smoke`, `e2e`
  - each gate is an existing command; no logic duplication
  - executes the command, captures stdout/stderr, measures duration
  - writes raw log to `artifacts/gates/logs/<gate>.log`
  - writes normalized `artifacts/gates/latest.json` with fields:
    `status`, `gate`, `check`, `error_signature`, `affected_files`,
    `artifact`, `duration_seconds`, `command`
  - `check`/`error_signature` extracted from the gate's own JSON report when present
    (quality_report.json, security_report.json, smoke_report.json, e2e_report.json)
  - exit code 0 on PASS, 1 on FAIL, 2 on unknown gate
- New `tests/test_gate_runner.py`:
  - PASS compact JSON shape
  - FAIL compact JSON shape + error_signature populated
  - no-LLM proof: runner executes a gate with `socket` disabled and an LLM-provider
    sentinel patched to raise; assert PASS and zero provider calls; plus a
    source-level assertion that `scripts/gate_runner.py` imports no provider SDK
- `.gitignore`: add `artifacts/` (runtime output). Keep specs/PLAN/DELIVERY tracked.

### WP-02 — Jenkins, SonarQube, provider aliases, UI adapter (AC-3, AC-4, AC-5) — IMPLEMENTED
- New cross-platform `Jenkinsfile` (declarative):
  - stages: targeted -> quality -> security -> Playwright -> SonarQube -> full E2E -> optional soak -> archive
  - Windows/Linux command handling
  - no embedded credentials
  - Sonar stage explicit; `NOT_CONFIGURED` when unset (never fake PASS)
  - archive `artifacts/gates/**`
  - cleanup of test processes/workspaces
- New `sonar-project.properties` for Python:
  - sources `src/transcript_pipeline`, tests `tests`
  - python version set
  - exclusions: `watcher/**`, `deepseek/**`, `**/node_modules/**`, `**/venv/**`,
    `**/__pycache__/**`, `artifacts/**`
  - no coverage report path (repo generates no coverage) — do not fabricate
- New `.agents/protocols/provider-aliases.md`:
  - maps `STRONG_PLANNER` / `PRIMARY_CODER` / `FREE_WORKER` / `SECONDARY_CODER`
    to local provider configuration; no credentials/endpoints committed
- `docs/ops/LOCAL-OPS.md`: append UI validation adapter section
  - web -> Playwright Chromium; electron -> Playwright Electron; no Electron runtime here

### WP-03 — Baseline security hygiene (AC-8) — IMPLEMENTED; pushed-history cleanup awaits owner authorization
- Sanitize `.agents/protocols/deterministic-gates.md`: replace the leaked
  private identifier in the example failure signature with a synthetic placeholder.
- Align venv with lock: anyio==4.14.2, soupsieve==2.9.2.
- Record residual: the identifier remains in this branch's pushed history (f7f5452).
  History rewrite is owner-only per `docs/GIT_HISTORY_CLEANUP.md`.

## Deterministic validation mapping
| AC | Gate |
|----|------|
| AC-1 | `tests/test_gate_runner.py` |
| AC-2 | code review + `tests/test_gate_runner.py` (invokes existing scripts) |
| AC-3 | code review of `Jenkinsfile` (declarative parse when Jenkins available) |
| AC-4 | code review of `sonar-project.properties`; no fake claims |
| AC-5 | `tests/test_packaging_core_deps.py` + grep for Electron |
| AC-6 | `tests/test_gate_runner.py::no_llm` |
| AC-7 | `git check-ignore artifacts/` + tracked specs present |
| AC-8 | `pytest tests/ -q`, `quality.py`, `security.py`, `smoke.py`, `e2e.py` |

## Dependencies
- Python runtime: `watcher\venv\Scripts\python.exe` (3.14.6)
- Playwright Chromium (present)
- Jenkins/Sonar: not installed locally -> explicit `NOT_CONFIGURED` evidence

## Risk / rollback
- Risk: e2e seed data absent locally. Mitigation: use existing
  `docs/assets/generate_mock_data.py` seeding path documented in LOCAL-OPS.
- Risk: history leak cannot be purged without owner-only rewrite.
- Rollback: revert WP-01/WP-02 files; no product code touched.

## Completion evidence required
- compact gate reports under `artifacts/gates/`
- pytest summary
- security/quality/smoke/e2e reports
- DELIVERY doc with owner intervention count
