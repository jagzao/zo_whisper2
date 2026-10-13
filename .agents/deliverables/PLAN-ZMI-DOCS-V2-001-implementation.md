# PLAN-ZMI-DOCS-V2-001 — Implementation plan

## Status
FROZEN_FOR_IMPLEMENTATION

## Branch
`feat/zmi-documentation-synthesis-v2`

Base:
`feat/zmi-knowledge-to-action-v1 @ 179ac48f8479ee3f39b71b7575574f34a5342b89`

## Rules
Implementation worker codes mechanically from this plan.
No architecture replanning.
No real confidential media.
No heavy validation before ChatGPT review.

## WP-01 — Configuration and enums
Modify project validation/config.

Add `documentation` block:
- mode
- synthesis_enabled
- max_screenshots
- max_screenshots_per_section

Add typed DocumentationMode constants in documentation domain, not knowledge cross-repo enum.

Add tests for defaults/invalid values/explicit authority.

Do not use filename suffix as authoritative mode.

## WP-02 — Evidence model
Create typed V2 evidence models, preferably:
`src/transcript_pipeline/documentation/evidence.py` or a focused models module.

Implement:
- EvidenceRef
- EvidenceItem
- EvidenceTimeline
- deterministic evidence ids
- review queue

Adapter converts current ProceduralStep + persisted mapping/segments into EvidenceItem without mutating source files.

Evidence resolver:
1. timestamped saved segments when discoverable;
2. unique transcription_mapping segments;
3. full transcription fallback.

Avoid duplicate overlapping transcript excerpts.

## WP-03 — Evidence timeline writer
Move current frame-by-frame human representation to:
- `evidence/evidence.jsonl`
- `evidence/EVIDENCE_TIMELINE.md`
- `evidence/review-queue.json`

Keep `manual/steps.json` compatibility generation.

Do not generate EVIDENCE_TIMELINE.pdf by default.

Tests prove 149-like evidence entries do not imply 149 manual semantic sections.

## WP-04 — Mode resolver
Create `documentation/classifier.py`.

Resolution:
explicit documentation.mode
-> artifact mapping
-> allowed classifier for AUTO
-> REFERENCE.

For `AUTO`, classifier receives compact textual evidence only, not screenshots unless explicitly required/allowed.

Structured output only.

If classifier unavailable/blocked/invalid:
REFERENCE fallback with typed reason.

## WP-05 — Deterministic synthesis input compactor
Create `documentation/compaction.py`.

Responsibilities:
- chronological transcript block construction;
- repeated OCR suppression;
- frame evidence references;
- configurable char bounds;
- max block count;
- no semantic invention.

Do not call LLM.

Unit tests:
- ordering;
- dedup;
- bounds;
- no evidence loss of ids;
- redundant OCR reduction.

## WP-06 — Synthesis domain
Create typed:
- KnowledgeClaim
- KnowledgeSection
- SynthesizedProcedure
- KnowledgeDocument
- SynthesisMetadata

Serialization deterministic and versioned.

## WP-07 — Synthesis provider/service
Create `documentation/synthesis.py`.

Reuse existing provider/privacy infrastructure where possible.

One API at domain level:
`synthesize(evidence_timeline, mode, project_config) -> SynthesisResult`.

Requirements:
- JSON structured prompt;
- map blocks only when needed;
- bounded calls;
- deterministic temperature 0;
- one malformed-schema repair retry max;
- no recursive repair;
- compact model metadata;
- no secrets.

The prompt explicitly requires evidence ids on every claim/step.

Do not expose whole raw confidential transcript to a remote provider if privacy policy blocks it.

## WP-08 — Grounding validator
Create `documentation/grounding.py`.

Validate SPEC §5.
Fail closed.

A synthesis result with unknown/missing evidence references never reaches MANUAL or publisher.

Persist a compact validation report:
`manual/synthesis-validation.json`.

No LLM verifier in this epic.

## WP-09 — Representative screenshot selector
Create `documentation/screenshots.py`.

Use existing Pillow/ImageHash when present.
- pHash threshold default 6;
- choose from evidence refs in semantic section;
- rank confidence/review/OCR usefulness;
- cap per section/global;
- graceful deterministic fallback.

Never delete source frames.

## WP-10 — Semantic Markdown writer
Refactor `write_manual` or introduce `semantic_manual_writer.py`.

V2 MANUAL.md reads KnowledgeDocument.

Render mode-appropriate sections.
For each section:
- title;
- concise prose/claims;
- representative screenshots;
- compact evidence references such as `[E-001 @ 00:13:34]`.

Do not include complete OCR/transcript.
Review queue count appears as callout only.

Persist:
`manual/knowledge-document.json`.

Keep existing metadata keys and add:
- schema_version=2
- documentation_mode
- synthesis_status
- review_required_count
- evidence_item_count
- semantic_section_count

## WP-11 — Semantic PDF writer
Refactor pdf writer to consume KnowledgeDocument + selected screenshots.

Keep:
- A4;
- bundled fonts/fallback;
- metadata;
- footer;
- graceful no-reportlab.

Add:
- executive summary styling;
- section styling;
- evidence-reference style;
- review-needed callout.

Do not render every EvidenceItem.

Tests should assert semantic content and bounded image count, not brittle page count.

## WP-12 — AI package V2
Refactor `write_ai_package`.

Outputs:
- semantic knowledge.md;
- semantic chunks.jsonl;
- manifest;
- evidence.jsonl;
- assets;
- compatibility steps.json if needed.

Chunk by KnowledgeSection/Claim/Procedure.
Metadata per SPEC.

Low-confidence evidence that supports no valid synthesized claim is not an independent retrieval chunk.

## WP-13 — Knowledge Package v2 bridge
Refactor package_builder with backwards-compatible overload/adapter.

Preferred new call:
`build_knowledge_package_from_document(..., knowledge_document, evidence_timeline, ...)`.

Keep old builder callable for existing tests/legacy path during migration.

New semantic path:
- title/summary from KnowledgeDocument;
- sections/claims in knowledge payload;
- procedure list only from SynthesizedProcedure;
- no all-evidence fake procedure.

Update source hash/content identity to include normalized semantic document + relevant evidence identity, not generated timestamp.

Preserve PROJECT/GLOBAL/policy/outbox behavior.

## WP-14 — Pipeline orchestration
Refactor `generate_documentation` into explicit staged result:
1. load persisted evidence;
2. create evidence timeline;
3. resolve mode;
4. synthesize if allowed;
5. validate grounding;
6. select screenshots;
7. write semantic manual/package;
8. publish semantic Knowledge Package when enabled.

Documentation failure remains non-fatal to transcription.

If synthesis unavailable:
- write evidence;
- typed result;
- do not pretend semantic MANUAL is complete.

## WP-15 — Regeneration command/API
Add deterministic CLI/script entry point, e.g.:
`python -m transcript_pipeline.documentation.regenerate_v2 <frames-dir>`
or equivalent existing CLI integration.

Required flags:
- frames dir;
- optional explicit mode override;
- no-upstream-work guard.

The implementation MUST expose a way to prove no Whisper/FFmpeg/OCR/vision calls occur.

Existing real processed recordings can later be regenerated through this path.

## WP-16 — Human review compatibility
Do not delete update/remove evidence-step functions.

Add semantic document load/save/regeneration primitive:
- edit semantic claim/section title/text;
- mark human reviewed only via explicit local review API/function.

Full new review UI is not required unless existing dashboard integration makes it trivial.

## WP-17 — Documentation/dashboard surfacing
Minimal integration:
- current "Open generated documentation" opens semantic MANUAL when available;
- evidence timeline is separately discoverable/downloadable;
- status distinguishes evidence-only vs semantic-manual-ready.

No major dashboard redesign in this epic.

## WP-18 — Synthetic fixtures
Create synthetic fixtures only:
- KT session with repeated frames and decisions/risks/process content;
- tutorial with explicit ordered actions;
- reference meeting;
- low-confidence evidence tail.

No actual client text/names/screenshots.

Use mock synthesis provider returning frozen structured JSON for deterministic UT/integration tests.

## WP-19 — Documentation
Update:
- README/docs for V2 artifact layout;
- knowledge-to-action docs;
- privacy explanation;
- regeneration instructions.

Add ADR 0007.

## WP-20 — Coding-phase validation
Run only:
- targeted documentation tests;
- targeted knowledge package regression tests;
- project config tests;
- Ruff on changed Python;
- Pyright/type validation for changed surface if configured;
- compileall.

No:
- full pytest;
- Playwright;
- Docker E2E;
- Jenkins;
- Sonar;
- soak;
- real LLM;
- real confidential videos.

Commit + push.
Return compact summary for ChatGPT /review.

## WP-21 — Post-review heavy validation (NOT NOW)
Only after ChatGPT approves code:
- RAM gate >6 GiB;
- full pytest;
- integration;
- security;
- smoke;
- E2E;
- Docker;
- other configured heavy gates.

## WP-22 — Post-heavy operational rollout (NOT CODING PHASE)
Only after heavy review:
- merge strategy;
- rebuild Docker runtime;
- configure real project mode/scope locally;
- regenerate already processed real videos from persisted evidence;
- inspect first semantic manual;
- then enable/publish to Second Brain;
- verify project isolation/retrieval.
