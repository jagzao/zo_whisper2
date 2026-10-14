# DELTA-ZMI-DOCS-V2-005 — Ground every user-visible synthesized prose field

## Status
BLOCKING / FINAL CORRECTNESS DELTA BEFORE HEAVY

## Review base
Implementation:
`5da0ab6df62ec5a6ad59ffbc94f7ecddec7dc18d`

Workflow policy:
`.agents/deliverables/WORKFLOW-ZO-001-single-active-workspace.md`

## Problem
Claims and procedure steps are evidence-grounded, but several user-visible LLM-generated fields are currently rendered without explicit evidence binding:
- KnowledgeSection.summary
- SynthesizedProcedure.purpose
- SynthesizedProcedure.prerequisites
- SynthesizedProcedure.expectedOutcomes
- executiveSummary when derived from section.summary

This violates the product promise that factual synthesized prose is evidence-grounded.

## F11 — Section summary grounding

Provider schema may include section `summary` only when the same section includes:
`evidenceIds: [..]`

Rules:
- non-empty summary => non-empty section evidenceIds;
- ids must be subset of current synthesis block;
- merge stores section.evidence_refs from those ids;
- final grounding validator rejects non-empty summary without valid evidence refs;
- placeholder-only evidence cannot solely ground a factual summary.

Manual/PDF/semantic package must render compact evidence refs with section summary.

An empty summary may have empty evidenceIds.

## F12 — Procedure metadata grounding

If any generated procedure contains non-empty:
- purpose
- prerequisites
- expectedOutcomes

then procedure-level `evidenceIds` is REQUIRED and must be a subset of the current synthesis block.

Merge stores procedure.evidence_refs from provider procedure evidenceIds plus step refs, deduplicated deterministically.

Final grounding validator rejects ungrounded non-empty procedure metadata.

Manual/PDF must display procedure-level evidence refs adjacent to purpose/prerequisites/expected outcomes or in a compact procedure evidence line.

Procedure title is treated as a semantic label, not a standalone factual assertion.

## F13 — Executive summary grounding

`KnowledgeDocument.executive_summary` may only be derived from:
1. a grounded EXECUTIVE_SUMMARY section.summary with valid section evidence_refs, or
2. grounded claims inside that section.

If neither exists, leave executive_summary empty.

Expose/store executive-summary evidence refs through the originating section; do not invent a second untracked prose source.

## F14 — RAG/package preservation

Semantic chunks/package that include:
- section summary
- procedure purpose/prerequisites/expected outcomes

must also carry the corresponding evidence refs.

Do not publish any user-visible synthesized prose without evidence metadata.

## Tests

Add targeted regressions:
1. non-empty section summary without evidenceIds => invalid;
2. section summary citing id outside current block => invalid;
3. grounded section summary => valid and rendered with evidence refs;
4. procedure purpose without procedure evidenceIds => invalid;
5. prerequisite/outcome without procedure evidenceIds => invalid;
6. grounded procedure metadata => valid and rendered with refs;
7. executive summary cannot come from ungrounded summary;
8. semantic chunk containing summary/procedure metadata carries refs;
9. existing claim/step grounding regressions remain green.

## Execution policy
Use the SAME normal project workspace/worktree.
Do not create an isolated/parallel worktree.

Do not restart WP-01..WP-20.
Implement only F11-F14.

Fast/light only:
- new targeted tests;
- affected V2 tests;
- Ruff;
- targeted Pyright;
- compileall;
- docs_v2_fast_ci --all-light.

No heavy/full pytest/security/smoke/Playwright/Docker/real media/real LLM.

Commit + push frequently/coherently.
Then READY_FOR_CHATGPT_REVIEW.
