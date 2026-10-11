# PLAN-PLV5 — Implementation Plan for ChatGPT-led Low-Token Delivery

## Status
FROZEN_FOR_IMPLEMENTATION

## Scope

First repair the Project Lead workflow/tooling. Commit and push that as an isolated delivery. Only after that may pending product development resume.

## WP-A — Reconcile current dirty Project Lead work safely

Current local branch may contain uncommitted work from the interrupted V4 implementation.

The dirty owner worktree is SOURCE-ONLY for reconciliation. Do not commit/rebase/switch it.

Required isolation:
1. keep the original dirty worktree untouched;
2. `git fetch origin`;
3. create a NEW isolated integration worktree from the latest
   `origin/feat/project-lead-v4-autonomous-delivery`, preferably detached or on
   a temporary local reconciliation branch;
4. copy/apply ONLY allowlisted Project Lead/tooling candidate changes from the dirty
   worktree into the isolated integration worktree;
5. reconcile those copied files to the frozen PLV5 contract there;
6. commit/test/push from the isolated integration worktree;
7. never require the dirty owner worktree to become clean.

Rules:
- never reset --hard the owner worktree;
- never stash automatically;
- never clean -fd;
- never discard untracked files;
- inspect git status and preserve all owner work;
- read this frozen PLV5 contract from origin;
- reconcile only files in the Project Lead/tooling allowlist below;
- product-code files outside the allowlist are not included in the Project Lead commit unless this PLAN explicitly names them.

Project Lead commit allowlist:
- `.agents/AGENTS.md`
- `.agents/protocols/**`
- `.agents/deliverables/*PLV4*`
- `.agents/deliverables/*PLV5*`
- `.agents/evidence/**`
- `docs/ops/LOCAL-OPS.md`
- `scripts/gate_runner.py`
- new `scripts/model_router.py`
- new `scripts/ram_gate.py`
- new `scripts/implementation_summary.py`
- new `scripts/heavy_validation_runner.py`
- `tests/test_gate_runner.py`
- new PLV5 workflow tests
- `.gitignore`
- `Jenkinsfile`
- `sonar-project.properties`
- provider/router config files without credentials
- dependency/lockfile edits only when strictly needed by deterministic tooling

Do not include unrelated modifications in:
- dashboard product behavior;
- transcription/product implementation;
- media product behavior;
unless a frozen PLV5 test proves the workflow itself cannot function without a tiny mechanical compatibility edit. Such an edit must be separately identified.

## WP-B — Rewrite core protocol semantics to V5

Update:
- `.agents/AGENTS.md`
- `.agents/protocols/project-lead.md`
- `.agents/protocols/model-routing.md`
- `.agents/protocols/delivery-loop.md`
- `.agents/protocols/deterministic-gates.md`

Required:
- remove local STRONG_PLAN stage;
- replace READY_FOR_OWNER_AUDIT after full validation with READY_FOR_CHATGPT_REVIEW after implementation gates;
- local implementation is one cheap coder, not model-tier escalation;
- no red-test-driven provider escalation;
- split implementation gates from heavy gates;
- add >6 GiB RAM gate;
- add power-loss resume;
- add max-2 mechanical repair policy;
- compact evidence first;
- heavy failures stop for ChatGPT diagnosis.

## WP-C — Deterministic cheap model router

Create `scripts/model_router.py` or equivalent deterministic script.

Input: configured provider aliases / discovered model list.
Output: selected model/provider and reason.

Exact priority:
1. Z.ai Coding Plan GLM configured owner-approved coder.
2. OpenCode DeepSeek.
3. Ollama server DeepSeek.
4. OpenRouter DeepSeek.

Rules:
- never select OpenAI/Codex/GPT/Claude/Kimi/premium models;
- fallback only when previous provider is unavailable/auth/quota/invocation failure;
- do not route based on test complexity;
- emit machine-readable JSON;
- no network beyond provider/model availability command already required by runtime;
- no LLM decides routing.

## WP-D — RAM gate

Create `scripts/ram_gate.py`.

Use psutil or OS metrics already available.

Output JSON:
```json
{
  "available_gib": 7.2,
  "threshold_gib": 6.0,
  "heavy_validation": "ALLOWED"
}
```

Strict rule:
- > 6.0 => ALLOWED
- <= 6.0 => DEFERRED_LOW_RAM

Exit codes:
- 0 ALLOWED
- 3 DEFERRED_LOW_RAM
- 2 measurement/config error

## WP-E — Implementation summary contract

Create deterministic summary writer:
`scripts/implementation_summary.py`

Output:
`artifacts/delivery/implementation/SUMMARY.json`
and `SUMMARY.md`.

Required fields:
- contract id;
- branch;
- start SHA;
- end SHA;
- changed files;
- selected cheap model;
- targeted unit result;
- lint result;
- typecheck/build result;
- blockers;
- terminal state.

No raw logs embedded.

## WP-F — Heavy validation runner

Create `scripts/heavy_validation_runner.py`.

Behavior:
1. run RAM gate first;
2. if <=6 GiB, write DEFERRED summary and exit without starting heavy tools;
3. if allowed, run configured heavy gates sequentially with no LLM:
   - full regression/integration as configured;
   - E2E/Playwright;
   - Docker gates;
   - security/dependency audit;
   - Sonar/Jenkins when configured;
4. continue independent gates after one failure;
5. emit compact summary;
6. never modify product code;
7. never invoke a model;
8. terminal state is PASS/FAIL/DEFERRED/BLOCKED.

## WP-G — Gate runner split

Update `scripts/gate_runner.py` registry/categories.

Implementation/light gates:
- targeted
- lint/quality
- typecheck
- unit

Heavy:
- full-pytest/regression
- e2e
- docker*
- security-heavy/dependency audit where applicable
- sonar
- jenkins
- soak

Do not silently treat NOT_CONFIGURED as PASS.

## WP-H — Checkpoint/resume

Define gitignored checkpoint:
`.agents/session/delivery-checkpoint.json`

Update atomically after:
- implementation package completion;
- commit;
- push;
- gate summary;
- terminal state.

Resume must validate:
- current branch;
- expected remote;
- SHA relation;
- dirty work;
- frozen contract path.

It may continue only mechanical pending work. It may never re-plan.

## WP-I — Lightweight validation of Project Lead V5

Before committing Project Lead changes run only:
- targeted PLV workflow tests;
- Ruff on changed Python tooling;
- Pyright/typecheck on changed tooling if configured;
- no full E2E;
- no Docker;
- no Jenkins pipeline;
- no Sonar;
- no soak.

Then, FROM THE ISOLATED INTEGRATION WORKTREE:
- selectively stage only allowlisted Project Lead files;
- commit;
- fetch origin;
- if remote advanced concurrently, rebase the CLEAN integration commit(s) onto latest origin there (never in the dirty owner worktree);
- push HEAD to `feat/project-lead-v4-autonomous-delivery`;
- verify remote SHA;
- write compact implementation summary.

The original dirty worktree remains untouched throughout.

## WP-J — Resume pending Knowledge-to-Action implementation

Only after WP-I is pushed.

Frozen continuation branches:
- `jagzao/zo_whisper2:feat/zmi-knowledge-to-action-v1`
- `jagzao/zavi:feat/knowledge-scope-publishing-v1`
- `jagzao/zavi-kab:feat/knowledge-bound-skills-v1`

The outage occurred before implementation commits. Existing branch heads are frozen-spec/tooling state, not completed feature code.

Sequence:
1. Zo Media producer contract.
2. Zavi scoped Second Brain contract.
3. KAV knowledge-bound skills contract.

For each repo:
- run direct cheapest approved coder;
- no subagents/planners;
- implement frozen contract;
- compile/typecheck/lint/targeted UT only;
- no heavy validation yet;
- commit/push;
- compact summary;
- continue next repo even if previous ends REVIEW_REQUIRED, unless its contract artifact itself is missing/corrupt.

At the end stop:
`READY_FOR_CHATGPT_REVIEW`

Do NOT run Knowledge-to-Action cross-repo E2E yet.
