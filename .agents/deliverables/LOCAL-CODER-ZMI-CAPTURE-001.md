# LOCAL-CODER-ZMI-CAPTURE-001

## Status
FROZEN_FOR_IMPLEMENTATION

## Role
Mechanical implementation worker only.

Read:
- EPIC-ZMI-CAPTURE-001-live-capture-to-knowledge.md
- SPEC-ZMI-CAPTURE-001-contracts.md
- US-ZMI-CAPTURE-001-live-recording.md
- PLAN-ZMI-CAPTURE-001-implementation.md
- TEST-MATRIX-ZMI-CAPTURE-001.md
- docs/adr/0008-live-capture-progressive-segments.md

Do not redesign product/security.

## Model routing
1. Z.ai Coding Plan GLM
2. OpenCode DeepSeek
3. Ollama Server DeepSeek
4. OpenRouter DeepSeek

Never auto-use GPT/Codex/Claude/Kimi/premium planner.

## CI
Implement Slices A-H.
Each slice:
- targeted tests
- Ruff/typecheck/compile changed surface
- commit
- push
- checkpoint

No heavy tests before ChatGPT review.

## Hard exclusions
- no LAN dashboard exposure
- no real Android network adapter
- no SaaS
- no billing
- no real client media
- no P&G
- no auto-delete
- no per-segment semantic publish
- no artificial transcript alignment
- no autonomous recursive loops

## Completion
Return READY_FOR_CHATGPT_REVIEW with per-slice remote SHAs and ALL_LIGHT result.
