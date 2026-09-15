# Delivery Loop (whisper)

## Story lifecycle
`ANALYSIS -> SPEC (frozen AC doc) -> IMPLEMENTATION (bounded executor dispatch) -> VALIDATION -> REWORK LOOP -> DELIVERY`

## Analysis
Read `CLAUDE.md`, `.agents/AGENTS.md`, the relevant `src/transcript_pipeline/` module, and any existing tests before writing AC — the fastest source of scope drift is writing AC from memory of the codebase instead of its current state.

## Spec
Write `.agents/deliverables/US-XXX-<slug>.md` with 3-6 concrete acceptance criteria before any implementation dispatch. Each AC must be independently testable (a specific pytest, a specific manual repro, or a specific `agent-browser` flow for dashboard UI — see Validation below). This file is the frozen scope; do not renegotiate it mid-implementation without editing it and noting why.

## Implementation
Dispatch one AC per executor call (per `project-lead.md`'s executor policy), quoting the AC text verbatim in the prompt. Small, reversible commits — one AC's implementation should be reviewable as one diff.

## Validation matrix
Run only what the AC touches:
- **Unit**: `pytest tests/ -v` scoped to the touched module (`.projects`, `.language`, `.file_tracker`, `.settings`, `.llm.guard`/`.redaction`, `.documentation.engine`, etc.).
- **Security**: `tests/security/` + `scripts/security.py` — mandatory whenever the AC touches `SafePathResolver`, upload handling, the dashboard token/Host check, or LLM/privacy flags (`ALLOW_EXTERNAL_LLM`, `ALLOW_FRAME_UPLOAD`).
- **Integration**: `tests/integration/` — mandatory whenever the AC touches handler routing, `HandlerResult`/`FileTracker` state, or keyframe/documentation generation.
- **Smoke**: `scripts/smoke.py` (fast, no browser) — run whenever the AC touches settings, dashboard boot, or the documentation engine.
- **Dashboard/UI AC**: per the global Web Validation Standard, use `agent-browser` as the primary loop — open the dashboard, exercise the exact changed flow, check console/network — before considering the AC implemented. Run the Playwright smoke (`scripts/e2e.py` / `tests/e2e/smoke_dashboard.py`) as the closing gate for that AC, not the full suite for every small edit.

Do not run the full `pytest tests/` + Playwright suite on every small AC — that's for epic/release closure. Run what the AC's own surface requires.

## Rework loop
For every finding (test failure, bug found during validation, or a defect reported after a prior "done"): `REPRODUCE -> ROOT CAUSE -> REGRESSION TEST -> FIX -> VALIDATE -> RE-RUN THE RELEVANT GATE`. A fix without a reproduced failure and a regression test is not closed — this is the direct fix for the "US-003 hardening" pattern (bugs shipped as "done", patched later with no regression test proving they won't recur).

## Definition of Done
An AC is DONE only when: the AC's own test/repro passes, `git diff` for every touched file has been read line by line (per global CLAUDE.md verification rule — never trust the executor's text summary), and the deliverable doc's AC checklist is updated with the evidence (which test, what it showed). Do not mark DONE on "should work" or an executor's claim alone.

## Delivery
Commit only after Definition of Done is met for the AC. Update `.agents/deliverables/US-XXX-<slug>.md`'s checklist and, if a session is in flight, `.agents/session/current_task.md`.
