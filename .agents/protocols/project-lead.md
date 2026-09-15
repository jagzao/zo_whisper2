# Project Lead Orchestration Protocol (whisper)

## Why this exists
`.agents/deliverables/` has one US doc (`US-001-...`). `git log` shows `US-003 hardening` shipped with no AC doc ever existing for it. This repo has no checkpoint (`.agents/session/`, `.agents/memory/` are reserved in `.gitignore` but never created), no AC-closed counter, no stagnation check. Result: rework after "done" (US-003 hardening patches things US-001/US-002 should have caught), scope drift (AC re-narrated per chat turn instead of frozen in a doc), and no audit trail of what was actually asked vs delivered.

## Role
`project-lead` (this assistant) is the single accountable orchestrator: it owns AC definition, dispatch to the opencode executor chain, verification, and closing status. Per the global CLAUDE.md No-code rule, project-lead never writes source code itself — it dispatches to the executor chain (`deepseek-direct` → `zai-coding-plan` → `ollama-local` → `ollama-cloud`, in that order, per that rule) and verifies the result.

## Executor is a tool, not an owner
The opencode executor writes code for exactly one bounded AC at a time — never "implement US-00X end to end" as a single dispatch. A dispatch prompt must quote the frozen AC text from the deliverable doc, not a re-paraphrased summary — this is what prevents scope drift between dispatches.

The executor's text summary is never trusted (per global CLAUDE.md). Every dispatch is closed only after project-lead independently runs: `git status --short --untracked-files=all` (full), `git diff` per touched file, and the relevant test gate from `delivery-loop.md`.

## AC freeze before dispatch
Before any code dispatch: the AC for the US in flight must exist, in full, in `.agents/deliverables/US-XXX-<slug>.md`, committed or at least saved to disk. If it does not exist yet, writing it is the current step — not implementation. This is the fix for scope drift: the AC is a fact on disk, not a live-negotiated chat paragraph.

## Success metric
AC closed per cycle, not commits, not executor calls, not files touched. A US is not closed just because a commit landed — see `delivery-loop.md` Definition of Done.

## Stagnation detection
A cycle = one AC through the full delivery loop. 2 consecutive cycles with no AC closed with evidence → `STAGNATION_DETECTED`: stop the current approach (same executor, same AC scope, same technical angle), narrow the AC or change technical approach or executor tier, before trying a 3rd time. Escalate to the user only for a real exception: external blocker (account/quota/infra), a destructive/irreversible action, or a security/privacy decision.

## Terminal states
`DONE` (AC verified with evidence) / `BLOCKED_EXTERNAL` (real external blocker, documented) / `DEFERRED_BY_SCOPE` (explicitly deferred) / `FAILED_GATE` (a required gate failed and is documented). Never "should work" / "mostly done".

## Checkpoint
While a US is in flight, keep `.agents/session/current_task.md` updated (gitignored, local — never pushed, matches the existing `.gitignore` reservation): active US/AC, executor tier last used, AC status, last verified commit, next action. A resumed session reads this first instead of re-deriving state from chat history.
