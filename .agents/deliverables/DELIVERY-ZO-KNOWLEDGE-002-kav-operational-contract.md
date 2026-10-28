# DELIVERY-ZO-KNOWLEDGE-002 — KAV Operational Contract

## State

`IMPLEMENTED_PENDING_INDEPENDENT_REAUDIT`

`PRODUCT_DEVELOPMENT_COMPLETE=YES` for the producer-side Documents V3/KAV knowledge contract. This is not source approval, Second Brain publication, or embedding authorization.

## Implementation

- Generic procedure extraction requires ordered action evidence; no procedure is emitted for informational discussion.
- Extraction scans complete recordings and emits multiple isolated procedures; invalid anchors recover, long workflows are bounded by inactivity/context/completion, and application context is retained when evidenced.
- Sequence anchors permit related intermediate unnumbered actions. Parameter names such as ACS URL, entity ID, role, group, or request ID remain unresolved required values; they do not suppress the procedure. Actual secret values are redacted.
- `PROCEDURE_GROUNDING` now returns `PASS`, `FAIL`, or `NOT_APPLICABLE`; `NOT_APPLICABLE` is non-blocking in quality/pilot aggregation.
- Evidence-grounded runbooks are separate, schema-versioned `KAV_EXECUTION_RUNBOOKS.json` artifacts.
- Runbooks default to `GUIDED`, remain candidates, preserve distinct source claims/evidence and execution capture requirements, and stop on missing values, unvalidated/current-state conflicts, or missing approval. Runbook validation is separate from execution readiness.
- `SECOND_BRAIN_READY`, chunk embedding eligibility, and document embedding readiness are separate fail-closed gates. Each embedding chunk has deterministic `chunk_id` independent of document `knowledge_id`; exclusions account for exact chunk IDs. Gemini is deferred.
- Missing OCR confidence remains null and is not counted as known zero confidence; diagnostics report missing and low values separately.

## Verification evidence

- Focused serial tests: KAV 12 passed; Session Pack 26 passed.
- Ruff: pass. Pyright: 0 errors. Syntax compilation: pass.
- Session 41 approved artifact integrity: preserved. V3 regeneration quality: `FAIL` (`VISUAL_TOPIC_COVERAGE`, `LOW_CONFIDENCE_FILLER`, with derived `QUALITY_GATE` and `SECOND_BRAIN_READY` failures). KAV regression: zero procedures/runbooks and both KAV gates `NOT_APPLICABLE`.
- Session 10 source remains `PARTIAL`; a local fixture contains three evidence-disjoint procedures and three passing candidate runbooks. Preflight stops on unresolved values. Nothing is published to Second Brain.
- Session 41 approved artifacts remain untouched. Visual coverage remains failed; archived regression input lacks per-frame selection/status/source metadata, so selected/uncovered counts are `NOT_RETAINED` and classification is `REGRESSION_FIXTURE_INCOMPLETE`. Low confidence is 16/64 material claims (0.25), all visual; missing confidence is zero.
- Session 18 state is `RECOVERY_SOURCE_AVAILABLE`; healthy original is recorded for later scoped recovery, waiting for the heavy slot.
- Gemini embeddings: deferred.

## Publication boundary

No P&G knowledge was published to Second Brain. Source-specific `SECOND_BRAIN_READY` remains `NO` until the actual package policy and review gates pass. Local audit outputs remain outside the implementation commit because they contain client-derived evidence.

No merge to `main` is included in this delivery.
