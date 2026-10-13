# AUDIT-ZMI-DOCS-V2-001 — Current documentation quality

## Status
FROZEN_ANALYSIS

## Scope
Review the current video-to-documentation implementation and the generated 75-minute KT/KAP sample without changing product code.

## Finding
The current pipeline is strong as an evidence timeline and weak as human documentation.

Current flow:

```text
frame_mapping.json
  -> build_steps()
  -> one ProceduralStep per extracted frame
  -> MANUAL.md / MANUAL.pdf
  -> one RAG chunk per ProceduralStep
```

That design preserves provenance but equates "captured moment" with "documentation step".

## Evidence from current code

### documentation/models.py
`ProceduralStep` is a frame-aligned captured-evidence object carrying:
- timestamp
- frame_ref
- transcript_ref
- OCR
- confidence
- reviewed
- optional unverified visual description

### documentation/engine.py
`build_steps()` iterates every extracted frame.
- transcript + OCR => high confidence
- transcript => high confidence
- OCR => medium confidence
- no captured evidence => low confidence placeholder

`write_manual()` then renders every step sequentially.

`write_ai_package()` creates one `chunks.jsonl` item per step:
`title + instruction`.

### documentation/pdf_writer.py
The PDF renders every step with heading, timestamp, screenshot and instruction.
It is a faithful renderer of the current model; the renderer itself is not the root problem.

### transcription/processor.py
The persisted data is sufficient to create a better V2 without repeating expensive upstream work:
- full transcription is persisted in `frame_mapping.json.transcription_summary.full_transcription`;
- timestamp-aligned nearby segments are persisted in `transcription_mapping`;
- timestamped transcription segments are also written by the transcription path;
- frames already exist on disk.

## Observed sample quality
The reviewed sample is 01:15:22 and produced 149 steps, including 20 low-confidence steps.
Repeated or near-identical screenshots dominate many pages.
The document contains useful KT facts but exposes them as fragmented conversational excerpts rather than synthesized knowledge.

Examples of knowledge currently buried in the timeline:
- KT/App Support knowledge areas;
- Compliance and ITSM topics;
- application walkthrough expectations;
- application architecture/technology discussion;
- shadow/reverse-shadow;
- Knowledge Acquisition schedule;
- transition timing concerns;
- dashboards/repositories used as information sources.

## Root causes

1. Frame == step coupling.
2. No semantic topic segmentation.
3. No document-type-aware rendering.
4. No semantic synthesis layer.
5. No claim-to-evidence model above raw steps.
6. Screenshot selection is frame-driven rather than section-driven.
7. Low-confidence evidence becomes visible manual content instead of a review queue.
8. Knowledge Package v2 currently builds its title/summary/procedure from all raw steps.
9. RAG chunks therefore contain fragmented transcript/OCR rather than consolidated knowledge.

## Non-problems
Do NOT solve this by:
- removing timestamps/provenance;
- allowing ungrounded LLM prose;
- retranscribing existing media;
- rerunning OCR for already persisted evidence;
- publishing raw transcript/VTT/media to the Second Brain.

## Architectural conclusion
Current `ProceduralStep` should become the compatibility representation of the Evidence Plane.
Documentation V2 adds a semantic synthesis layer above it.

Target:

```text
media/transcript/frames/OCR
          |
          v
Evidence Timeline
          |
          v
Semantic Synthesis
          |
          v
Grounded Knowledge Document
      /               \
 Human Manual      AI Package
                       |
                       v
                 Second Brain
```

The evidence timeline remains durable and inspectable.
The human manual and RAG package must no longer be direct renderings of every frame.
