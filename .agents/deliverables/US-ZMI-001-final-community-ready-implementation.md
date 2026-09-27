# US-ZMI-001 — Final Community-Ready Implementation

## Status
`IN_PROGRESS`

## Parent
EPIC: `.agents/deliverables/EPIC-ZMI-001-community-ready-completion.md`

## Frozen scope

Implement every P0/P1 item in `AUDIT-ZMI-001-current-state.md` necessary to reach first community-launch readiness. Do not absorb unrelated P2/P3 work.

## Acceptance criteria

1. [ ] Edit File combined save is all-or-nothing; injected transcript/segment/override failures return error and restore previous persisted state.
2. [ ] Project rename/delete plus override migration/cleanup are transaction-like; injected second-write failure rolls back the first write and returns error.
3. [ ] Media delete cannot knowingly return success after project-override persistence failure.
4. [ ] Clean Project-lead V4 protocols/tooling are present without inheriting PR #23's unsafe history.
5. [ ] Project-scoped OpenCode autonomous agent definitions enforce no routine `question` / `doom_loop` owner interruption.
6. [ ] Compact deterministic gate runner emits stable PASS/FAIL JSON and repeated runs invoke no LLM/provider code.
7. [ ] `Jenkinsfile` and `sonar-project.properties` exist, contain no credentials and do not fabricate PASS/coverage.
8. [ ] Real process-level dashboard stop/start recovery smoke passes in isolation.
9. [ ] Lightweight GitHub PR CI + secret scan exist and documentation accurately describes local/Jenkins/public-CI responsibilities.
10. [ ] Community templates/Code of Conduct are present.
11. [ ] Fresh-install acceptance path is documented and scripted so it can be run in an isolated environment.
12. [ ] Full release gates are green and private denylist tree/history scan is clean on the final integration branch.
13. [ ] Final DELIVERY records exact evidence and residual risks; no known P0/P1 remains.
14. [ ] Public CI execution is enabled in repository Actions settings. If repository settings block Actions, record BLOCKED_EXTERNAL with exact owner action; do not pretend remote CI is green.

## Non-goals

- repository rename/tag/release before owner acceptance;
- SOC 2 certification;
- GPU acceleration;
- distributed worker infrastructure;
- extraction of experimental `watcher/` / `deepseek/` trees.

## Owner interventions

Expected: 2
1. INITIAL_SPEC — this frozen implementation contract.
2. FINAL_ACCEPTANCE — local product test after assistant audit.

Unexpected: 0.

## Terminal state

`READY_FOR_OWNER_AUDIT`
