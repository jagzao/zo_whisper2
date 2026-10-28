# US-ZO-KNOWLEDGE-002 — KAV Operational Knowledge Contract

## Status

IMPLEMENTED_PENDING_INDEPENDENT_REAUDIT

## Parent

`US-ZO-KNOWLEDGE-001-master.md`

## Goal

Emit evidence-grounded procedures and a separate deterministic KAV runbook while keeping human and semantic knowledge outputs distinct.

## Acceptance

1. Zero procedures yields `PROCEDURE_GROUNDING=NOT_APPLICABLE`; this state does not count as a fabricated pass or block quality.
2. Every procedure and material step has a valid evidence reference. Missing or partial provenance fails the gate.
3. Procedure synthesis requires ordered operational evidence. Informational discussion alone yields zero procedures.
4. Runbooks use explicit actionability levels: `REFERENCE`, `GUIDED`, `EXECUTABLE_WITH_CONFIRMATION`, or `EXECUTABLE`. Generated runbooks default to `GUIDED`.
5. Every runbook is a `CANDIDATE`, preserves source evidence, and requires current-live validation for historical instructions.
6. Unknown required values remain explicit `REQUIRED_UNRESOLVED` parameters and preflight stops until supplied from an approved current source. Parameter names do not suppress procedures. Actual secret values are redacted.
7. Material actions carry approval boundaries; no generated runbook is authority to execute them.
8. Human Session/Mission Packs, semantic Knowledge Packages, and `KAV_EXECUTION_RUNBOOKS.json` are separate outputs.
9. `SECOND_BRAIN_READY` passes only when quality, provenance, application resolution where relevant, conflict, privacy, policy, and procedure/runbook gates pass.
10. Chunk eligibility and document embedding readiness are distinct. Document readiness requires every intended chunk to be eligible or explicitly excluded, a passing `SECOND_BRAIN_READY`, curated human-reviewed semantic content, identity, provenance, and a matching content hash. No provider call is part of this work.
11. Runbook validation and execution readiness are distinct. Valid candidates can remain non-executable due to missing values, current-state review, actionability, or approval.
12. Approved Session 41 facts are read-only regression evidence; zero runbooks is valid when no ordered procedure is evidenced. Integrity, V3 regeneration quality, and KAV zero-runbook regression are reported separately.
13. Production code remains generic. Compliance Session 10 terminology may be used in fixtures, never in production rules.

## Verification

Run serial focused procedure/KAV tests, then the focused Documents V3 suite. Do not run another ASR/VAD workload while an authorized transcription batch is active.

## Lifecycle

This is `FEATURE-KNOW-007` under `EPIC-ZO-KNOWLEDGE-001`. Producer implementation is complete; source-specific quality, current-policy review, owner acceptance, Second Brain publication, and embeddings remain separate gates.
