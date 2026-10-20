# SPEC-ZMI-DOCS-V2-001 — Evidence, synthesis and output contracts

## Status
FROZEN_FOR_IMPLEMENTATION

## 1. Compatibility
Existing upstream evidence files remain readable.
No migration may require retranscription.

Current `ProceduralStep` stays supported as a legacy/evidence object during V2.
Do not silently change its existing JSON wire keys.

## 2. DocumentationMode
```text
AUTO
TUTORIAL
KT_SESSION
PROCESS_WALKTHROUGH
MEETING
ARCHITECTURE
INCIDENT
REFERENCE
```

Project config:
```json
{
  "documentation": {
    "mode": "KT_SESSION",
    "synthesis_enabled": true,
    "max_screenshots": 24,
    "max_screenshots_per_section": 2
  }
}
```

Defaults:
- mode=AUTO
- synthesis_enabled=true
- max_screenshots=24
- max_screenshots_per_section=2

Validation rejects unknown modes and non-positive bounds.

## 3. Evidence contracts

### EvidenceRef
Required fields:
- evidenceId
- timestampStart
- timestampEnd
- evidenceSource: transcript | ocr | transcript_ocr | frame | none
- confidence: high | medium | low
- reviewed
Optional:
- frameRef
- transcriptExcerpt
- ocrExcerpt
- sourceSegmentIds

Raw whole transcripts are not embedded in EvidenceRef.

### EvidenceItem
- evidenceId
- ordinal
- timestampStart/end
- transcriptExcerpt
- ocrExcerpt
- frameRef
- confidence
- reviewed
- source provenance

Evidence ids are deterministic for unchanged persisted source evidence.

## 4. Knowledge contracts

### KnowledgeClaim
- id
- text
- evidenceRefs[] REQUIRED non-empty
- evidenceConfidence
- verificationStatus:
  - SYNTHESIZED_UNREVIEWED
  - HUMAN_REVIEWED
- tags[]

The model may not mark its own claim HUMAN_REVIEWED.

### KnowledgeSection
- id
- sectionType
- title
- summary
- claims[]
- evidenceRefs[]
- screenshotCandidates[]
- order

sectionType enum:
- EXECUTIVE_SUMMARY
- CONTEXT_SCOPE
- GOAL
- PREREQUISITES
- CONCEPT
- PROCESS
- PROCEDURE
- SYSTEM
- ROLE_RESPONSIBILITY
- DECISION
- RISK
- OPEN_QUESTION
- ACTION_ITEM
- TROUBLESHOOTING
- ARCHITECTURE_COMPONENT
- DEPENDENCY
- DATA_FLOW
- EXPECTED_RESULT
- GLOSSARY
- REFERENCE

### SynthesizedProcedure
A procedure exists only if the source evidence supports ordered operational actions.

Fields:
- id
- title
- purpose
- prerequisites[]
- steps[]
- expectedOutcomes[]
- evidenceRefs[]
- actionability

Each step:
- order
- instruction
- evidenceRefs[]
- semanticAction/semanticTarget nullable

No semanticAction is inferred merely from natural-language text.

### KnowledgeDocument
- schemaVersion = 2
- source
- documentationMode
- title
- purpose nullable
- executiveSummary
- sections[]
- procedures[]
- glossary[]
- evidenceIndex[]
- synthesis:
  - providerType
  - model
  - generatedAt
  - status
  - inputHash
- reviewStatus

## 5. Grounding validator
A KnowledgeDocument is valid only when:
1. each claim has >=1 evidence ref;
2. every ref exists in EvidenceIndex;
3. every procedure step has >=1 evidence ref;
4. timestamps are within source duration;
5. low/no-evidence placeholder items cannot be the sole support for a factual claim;
6. generated content cannot set reviewed=true/HUMAN_REVIEWED;
7. unknown section/mode enum fails;
8. forbidden raw payload keys fail recursively;
9. output does not include whole raw transcript;
10. source evidence is never rewritten in-place by synthesis.

Invalid synthesis output:
- is stored only as compact failure evidence;
- does not replace the last good manual;
- does not publish to Second Brain.

## 6. Synthesis input
Do not send every screenshot/OCR blob blindly.

Create deterministic SynthesisBlocks:
- ordered;
- timestamp range;
- transcript excerpts;
- deduplicated meaningful OCR;
- frame/evidence ids;
- bounded characters.

Default bounds:
- target <= 18,000 chars per block;
- hard <= 24,000 chars;
- max 12 map blocks per document;
- if source exceeds bound, merge/truncate only redundant OCR first; never fabricate or reorder evidence.

Full transcript may be read locally to construct blocks, but raw full transcript is never published downstream.

## 7. Provider behavior
Use existing OpenAI-compatible provider abstraction and PrivacyGuard where practical.

Synthesis is allowed only when provider/config/privacy permits it.

Remote provider + confidential project:
- blocked exactly like other external LLM calls.

Local provider:
- allowed according to existing local policy.

Provider output MUST be structured JSON matching the frozen synthesis schema.
No free-form Markdown is accepted as authoritative synthesis.

One bounded retry is allowed only for malformed JSON/schema repair using the same provider/model.
No recursive repair loop.

## 8. Mode templates

### TUTORIAL
Preferred order:
1. EXECUTIVE_SUMMARY / GOAL
2. PREREQUISITES
3. PROCEDURE
4. EXPECTED_RESULT
5. TROUBLESHOOTING
6. GLOSSARY
7. evidence appendix

### KT_SESSION
1. EXECUTIVE_SUMMARY
2. CONTEXT_SCOPE
3. CONCEPT
4. PROCESS
5. SYSTEM
6. ROLE_RESPONSIBILITY
7. DECISION
8. RISK
9. OPEN_QUESTION
10. ACTION_ITEM
11. GLOSSARY
12. evidence appendix

### PROCESS_WALKTHROUGH
1. EXECUTIVE_SUMMARY
2. CONTEXT_SCOPE
3. PREREQUISITES/inputs
4. ROLE_RESPONSIBILITY
5. PROCESS/PROCEDURE
6. decision points represented as PROCESS/REFERENCE claims
7. EXPECTED_RESULT
8. TROUBLESHOOTING/exceptions
9. evidence appendix

### MEETING
1. EXECUTIVE_SUMMARY
2. CONTEXT_SCOPE
3. DECISION
4. ACTION_ITEM
5. RISK
6. OPEN_QUESTION
7. REFERENCE topics
8. evidence appendix

### ARCHITECTURE
1. EXECUTIVE_SUMMARY
2. CONTEXT_SCOPE
3. ARCHITECTURE_COMPONENT
4. DEPENDENCY
5. DATA_FLOW
6. SYSTEM
7. RISK
8. REFERENCE/operational notes
9. evidence appendix

### INCIDENT
1. EXECUTIVE_SUMMARY
2. CONTEXT_SCOPE
3. timeline/process
4. SYSTEM
5. root-cause claim only if evidence supports it
6. ACTION_ITEM
7. TROUBLESHOOTING
8. evidence appendix

### REFERENCE
No forced procedure.
Use coherent concepts/reference sections.

## 9. Screenshot selection
Implement deterministic representative selection.

Candidate score may use:
- section evidence reference;
- confidence;
- reviewed;
- OCR text density;
- temporal centrality.

Dedup with perceptual hash when ImageHash/Pillow are available.
If unavailable, fall back to same-frame id/path dedup, never fail documentation.

Defaults:
- pHash Hamming distance <= 6 => duplicate;
- max 2 screenshots/section;
- max 24 screenshots/manual.

Do not delete original frame evidence.

## 10. Output layout

```text
<frames_dir>/
  frame_mapping.json
  manual/
    MANUAL.md
    MANUAL.pdf
    knowledge-document.json
    metadata.json
    assets/
    steps.json                  # compatibility evidence source
  evidence/
    evidence.jsonl
    EVIDENCE_TIMELINE.md
    review-queue.json
    assets/                     # optional references/copies
  ai-package/
    knowledge.md
    chunks.jsonl
    manifest.json
    knowledge-package.json
    procedure.json              # only when real procedure exists
    evidence.jsonl
    assets/
```

EVIDENCE_TIMELINE.pdf is optional and disabled by default to avoid a second huge PDF.
The old frame-by-frame MANUAL representation becomes EVIDENCE_TIMELINE.md.

## 11. Human MANUAL rules
MANUAL must:
- use semantic sections;
- include an executive summary where mode supports it;
- show evidence citations as timestamps/evidence ids;
- show only representative screenshots;
- exclude raw low-confidence placeholders from main prose;
- include a compact review-needed callout when review queue non-empty;
- never dump full OCR/transcript.

## 12. AI package rules
`knowledge.md` mirrors semantic sections, not raw steps.

`chunks.jsonl` chunks by semantic section/claim/procedure with metadata:
- knowledge/document id
- section id/type
- scope
- project id when PROJECT
- artifact type
- actionability
- evidence refs
- evidence confidence
- review status
- source media
- timestamp range

Chunk target:
- coherent semantic unit;
- <= 4,000 chars default;
- split long section by claims, not arbitrary character slices when possible.

## 13. Knowledge Package v2 bridge
Update builder to accept KnowledgeDocument V2.

Package knowledge:
- title from synthesized document;
- summary from executive summary;
- tags/glossary where applicable;
- semantic sections/claims;
- procedures only from SynthesizedProcedure.

Do not construct a Procedure from every EvidenceItem.

If synthesis is unavailable/invalid:
- evidence artifacts may still succeed;
- no new semantic Knowledge Package is published;
- return typed status.

## 14. Regeneration
Add a deterministic V2 regeneration entry point that accepts an already processed frames directory.

It MUST NOT invoke:
- Whisper/faster-whisper;
- FFmpeg keyframe extraction;
- OCR;
- vision frame description.

It may invoke the synthesis provider if enabled/allowed.

A no-provider dry regeneration can still rebuild Evidence Timeline from persisted evidence.

## 15. Status values
Documentation result:
- EVIDENCE_READY
- SYNTHESIS_READY
- SYNTHESIS_NOT_AVAILABLE
- SYNTHESIS_BLOCKED_PRIVACY
- SYNTHESIS_INVALID
- MANUAL_READY
- PUBLISH_ENQUEUED
- PUBLISH_ACK
- PUBLISH_PENDING_RETRY

No bare success boolean is sufficient for V2 orchestration.
