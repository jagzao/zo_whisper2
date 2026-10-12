# DELTA-PLV5-001 — Post-review workflow corrections

## Status
FROZEN_FOR_IMPLEMENTATION

## Review finding

Project Lead V5 is directionally correct and the primary workflow change is accepted, but the deterministic gate registry still violates the owner's implementation/heavy split.

Current defect:
- `security` and `smoke` are classified LIGHT even though the frozen V5 protocol says the implementation worker normally runs only compile/typecheck, lint, targeted UT and explicitly frozen low-cost checks.
- `e2e` and `playwright` both map to the same `scripts/e2e.py`, causing duplicate heavy work.
- heavy runner omits the full security/smoke gates.

## Required mechanical changes

1. In `scripts/gate_runner.py`:
   - LIGHT = targeted, unit, lint, quality, typecheck.
   - HEAVY = pytest, security, smoke, e2e, sonar, docker-build, docker-e2e, jenkins, soak.
   - remove duplicate `playwright` alias if it invokes the same authoritative command as `e2e`; one full E2E execution only.
   - NOT_CONFIGURED remains explicit and never PASS.

2. In `scripts/heavy_validation_runner.py`:
   - ordered heavy gates:
     `pytest -> security -> smoke -> e2e -> sonar -> docker-build -> docker-e2e -> jenkins -> soak`.
   - RAM gate remains strict: available > 6.0 GiB only.
   - no LLM, no product-code repair.

3. Update protocol/docs/tests to match exactly.

4. Add/adjust deterministic tests proving:
   - security/smoke cannot be selected as implementation/light gates;
   - E2E is invoked only once;
   - heavy runner includes security/smoke;
   - <=6 GiB starts no heavy child process.

## Validation now
Only targeted PLV5 tests + Ruff/compile/typecheck for changed tooling.
No heavy validation.

## Terminal
Commit/push branch, then READY_FOR_CHATGPT_REVIEW.
