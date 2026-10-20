# EPIC-ZMI-DOCS-V2-001 — Evidence-to-Knowledge Documentation Synthesis V2

## Status
FROZEN_FOR_IMPLEMENTATION

## Product goal
Turn Zo Media Intelligence from a frame-by-frame documentation generator into an evidence-grounded media-to-knowledge system.

The system must produce:
1. a durable Evidence Timeline for audit/debug/review;
2. a concise, semantically structured human manual;
3. AI-ready knowledge chunks optimized for retrieval;
4. procedure candidates only when the source actually contains a procedure;
5. traceable evidence references for every synthesized factual claim.

## Core principle
**Evidence is not documentation.**

Captured evidence remains immutable source material.
Semantic knowledge is a derived, reviewable layer.

## Required architecture

```text
VIDEO / AUDIO
   |
   +-- transcript segments
   +-- frames/keyframes
   +-- OCR
   +-- timestamps
          |
          v
  EVIDENCE PLANE
  EvidenceItem[]
          |
          +--> EVIDENCE_TIMELINE.md/jsonl
          +--> review-queue.json
          |
          v
  DOCUMENT CLASSIFICATION
          |
          v
  SEMANTIC SEGMENTATION
          |
          v
  GROUNDED SYNTHESIS
  KnowledgeDocument
          |
      +---+----------------------+
      |                          |
      v                          v
 MANUAL.md/pdf             AI knowledge package
                               |
                               v
                         Knowledge Package v2
                               |
                               v
                             Zavi
```

## Documentation modes
Introduce a DocumentationMode independent from the cross-repo KnowledgeArtifactType enum:

- AUTO
- TUTORIAL
- KT_SESSION
- PROCESS_WALKTHROUGH
- MEETING
- ARCHITECTURE
- INCIDENT
- REFERENCE

Reason: human document shape and cross-repo knowledge artifact type are related but not identical.

Mapping defaults:
- TUTORIAL -> TUTORIAL
- KT_SESSION -> KT
- PROCESS_WALKTHROUGH -> PROCEDURE
- MEETING -> REFERENCE
- ARCHITECTURE -> APPLICATION or REFERENCE according to explicit project config
- INCIDENT -> INCIDENT
- REFERENCE -> REFERENCE

No automatic cross-repo enum expansion is required in this epic.

## Mode authority
Resolution order:
1. explicit project `documentation.mode`;
2. explicit `second_brain.default_artifact_type` mapping;
3. optional allowed synthesis classifier when mode=AUTO;
4. safe fallback REFERENCE.

Filename suffixes such as `_tutorial` are hints only and MUST NOT override explicit project configuration.

## P&G-like confidential KT use case
A confidential project can be configured locally as:
- documentation.mode = KT_SESSION
- second_brain.scope = PROJECT
- project_id = local project key
- default_artifact_type = KT
- default_actionability = REFERENCE

No real client names/config/content may be committed to the public repository.

Remote LLM synthesis remains blocked by the existing privacy policy.
A permitted local provider may synthesize confidential evidence.
If no allowed synthesis provider exists, preserve evidence and return SYNTHESIS_NOT_AVAILABLE; never generate unsupported prose.

## Regeneration guarantee
Existing processed media MUST be eligible for V2 regeneration without:
- re-transcription;
- new keyframe extraction;
- OCR rerun;
- media re-encoding.

Input resolver preference:
1. persisted timestamped transcription segments;
2. unique timestamped segments from `frame_mapping.transcription_mapping`;
3. full persisted transcription as lower-fidelity untimed fallback.

Existing screenshots/frames are reused.

## Human manual philosophy
A 60–90 minute KT meeting should normally become tens of meaningful sections, not hundreds of frame entries.

A KT_SESSION document shape includes when supported:
- Executive Summary
- Context and Scope
- Key Concepts
- Processes / Workflows
- Systems and Information Sources
- Roles and Responsibilities
- Decisions / Agreements
- Risks / Concerns
- Open Questions
- Action Items
- Glossary
- Evidence Index

Other modes have their own templates in SPEC.

## Evidence grounding
Every synthesized factual claim MUST reference >=1 valid EvidenceRef.
Unknown evidence ids fail validation.
Low-confidence/no-evidence items cannot silently become claims.

Generated prose and captured evidence remain distinguishable.

## Screenshot strategy
Screenshots are selected per semantic section, not per source frame.

Selection:
- prefer referenced frames;
- perceptual-hash dedup;
- prefer higher evidence confidence and useful OCR;
- maximum configurable screenshots per section;
- global manual screenshot cap.

All original evidence frames remain available in the evidence plane.

## Second Brain quality
Do not publish one RAG chunk per raw frame.

AI chunks must be section/claim/procedure oriented:
- coherent topic;
- bounded size;
- evidence refs;
- scope/project metadata;
- artifact type;
- confidence/review status.

Raw whole transcript/VTT/media remain forbidden.

## Knowledge-to-Action compatibility
Knowledge Package v2 remains the cross-repo envelope.

The producer changes from:
`steps -> fake all-steps procedure`

to:
`KnowledgeDocument -> knowledge sections + optional real procedure candidates`.

REFERENCE/KT content may contain zero procedures.
EXECUTABLE authority remains governed by the existing Knowledge -> Procedure -> Skill Candidate -> validated capability chain.

## Cost policy
Runtime synthesis must be bounded:
- deterministic compaction before LLM;
- no per-frame LLM synthesis;
- configurable input block size;
- bounded number of synthesis calls;
- no recursive self-repair loop;
- no LLM polling;
- no second verifier LLM by default.

## Deliverables
- typed evidence/synthesis models;
- evidence timeline writer;
- document mode resolver;
- semantic input compactor;
- synthesis provider interface;
- grounded JSON synthesis parser/validator;
- section-based manual Markdown/PDF;
- semantic AI package/chunks;
- Knowledge Package v2 integration;
- regeneration command/API path from existing artifacts;
- deterministic fixtures/tests;
- docs and ADR.

## Out of scope
- reprocessing the real confidential videos during implementation;
- uploading real client data into tests/Git;
- real cloud/agent execution;
- Zavi migration changes unless contract incompatibility is discovered;
- KAV behavior changes;
- model training/fine-tuning;
- autonomous factual correction of transcripts;
- speaker diarization unless separately scoped.
