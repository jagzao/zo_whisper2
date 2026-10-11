# TEST-MATRIX-PLV5 — Low-Token Workflow

## Router
- PLV5-R01: Z.ai available -> Z.ai GLM selected.
- PLV5-R02: Z.ai unavailable, OpenCode DeepSeek available -> OpenCode DeepSeek selected.
- PLV5-R03: first two unavailable -> Ollama-server DeepSeek.
- PLV5-R04: first three unavailable -> OpenRouter DeepSeek.
- PLV5-R05: only premium/OpenAI/Claude/Kimi available -> fail closed, no selection.
- PLV5-R06: red unit test does not cause provider/model escalation.

## Implementation phase
- PLV5-I01: frozen contract missing -> SPEC_CONFLICT/blocked, no invented plan.
- PLV5-I02: local worker does not invoke planner/subagent.
- PLV5-I03: targeted UT runs.
- PLV5-I04: lint runs.
- PLV5-I05: typecheck/build runs where configured.
- PLV5-I06: full E2E/Docker/Jenkins/Sonar do not run before ChatGPT review.
- PLV5-I07: identical mechanical failure gets max 2 repair attempts.
- PLV5-I08: compact summary is created.
- PLV5-I09: commit/push precede READY_FOR_CHATGPT_REVIEW.

## RAM/heavy validation
- PLV5-H01: available=6.01 GiB -> ALLOWED.
- PLV5-H02: available=6.00 GiB -> DEFERRED_LOW_RAM.
- PLV5-H03: available=5.99 GiB -> DEFERRED_LOW_RAM.
- PLV5-H04: deferred run starts no heavy child process.
- PLV5-H05: allowed run invokes configured heavy deterministic gates.
- PLV5-H06: one heavy gate failure does not trigger product-code repair.
- PLV5-H07: one heavy gate failure does not skip independent heavy gates.
- PLV5-H08: no LLM/provider SDK is called by heavy runner.

## Resume/power loss
- PLV5-P01: checkpoint atomic write survives interrupted temp write.
- PLV5-P02: restart resumes first incomplete mechanical step.
- PLV5-P03: restart does not rerun local planning.
- PLV5-P04: dirty owner work is not reset/stashed/deleted.
- PLV5-P05: branch/SHA mismatch fails closed with evidence.

## Git sequencing
- PLV5-G01: Project Lead workflow commit contains only allowlisted paths.
- PLV5-G02: Project Lead workflow is pushed before Knowledge-to-Action resumes.
- PLV5-G03: Knowledge-to-Action implementation commits remain on their dedicated branches.
- PLV5-G04: no merge/deploy is performed.

## Token/no-loop proof
- PLV5-T01: deterministic gate runner imports/calls no LLM provider.
- PLV5-T02: heavy validation runner imports/calls no LLM provider.
- PLV5-T03: model router never returns OpenAI/Codex/GPT/Claude/Kimi.
- PLV5-T04: no unbounded retry/while loop around model invocation.
- PLV5-T05: raw logs are not embedded in implementation summary.
