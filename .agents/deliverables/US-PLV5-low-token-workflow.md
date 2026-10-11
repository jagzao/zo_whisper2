# US-PLV5 — Low-Token Implementation and Validation Workflow

## Status
FROZEN_FOR_IMPLEMENTATION

## User story

As the owner of multiple active software projects, I want high-cost reasoning centralized in ChatGPT and local coding/validation constrained to cheap models and deterministic tools so development can continue safely without wasting token quotas or saturating RAM.

## Acceptance criteria

1. Project-lead no longer invokes a STRONG_PLANNER locally for normal delivery.
2. Frozen Git artifacts produced by owner + ChatGPT are the implementation source of truth.
3. The local coder uses the approved cheap provider order:
   Z.ai GLM -> OpenCode DeepSeek -> Ollama-server DeepSeek -> OpenRouter DeepSeek.
4. OpenAI/Codex/GPT, Claude, Kimi and other premium planners are denied for local implementation unless the owner explicitly changes the frozen routing policy.
5. Provider fallback happens only on provider/model availability failure, never as an autonomous response to red tests.
6. Local coder performs code + compile/typecheck + lint + targeted UT.
7. Local coder does not run full E2E/Docker/Jenkins/Sonar/soak before ChatGPT /review.
8. Mechanical repair attempts are capped at 2 per identical failure signature.
9. Local coder commits/pushes implementation and emits compact SUMMARY.json/MD, then stops at READY_FOR_CHATGPT_REVIEW.
10. ChatGPT /review is the decision point for delta vs heavy validation.
11. Heavy validation checks available RAM deterministically and runs only when available RAM is strictly greater than 6 GiB.
12. With <=6 GiB free, heavy validation is deferred rather than forcing memory pressure.
13. Heavy deterministic processes run without an LLM polling/waiting.
14. Heavy failures produce evidence and return to ChatGPT; no autonomous local behavior-changing repair loop.
15. Power loss/session loss resumes from checkpoint and Git state without repeating analysis/planning.
16. Existing dirty owner work is never reset/stashed/discarded automatically.
17. Project-lead/workflow changes are committed and pushed separately before any pending product implementation continues.
18. Knowledge-to-Action implementation branches remain the frozen continuation targets after Project Lead V5 is committed.
