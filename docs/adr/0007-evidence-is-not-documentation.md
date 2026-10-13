# ADR 0007 — Evidence is not documentation

## Status
Accepted for Documentation Synthesis V2.

## Context
Zo Media Intelligence originally rendered each retained frame and its nearby transcript/OCR as a documentation step.
This produced excellent provenance but verbose, fragmented manuals and low-quality retrieval chunks for meeting/KT recordings.

## Decision
Separate the Evidence Plane from the Semantic Knowledge Plane.

Evidence is immutable captured source material:
- transcript excerpts;
- OCR;
- frame refs;
- timestamps;
- confidence/provenance.

Documentation is a derived artifact:
- semantic sections;
- grounded claims;
- procedures only when supported;
- representative screenshots.

Every derived factual claim must reference evidence.

A generated synthesis cannot mark itself human reviewed.

## Consequences
Positive:
- concise manuals;
- better RAG chunks;
- preserved traceability;
- no need to retranscribe existing processed media;
- KT/meeting content no longer masquerades as click-by-click tutorials.

Costs:
- synthesis provider path;
- schema/grounding validation;
- two related artifact families to maintain;
- compatibility period for legacy steps.json.

## Security
Raw whole transcript/VTT/media remain local and are not published to the Second Brain.
Existing privacy/provider boundaries remain authoritative.

## Knowledge-to-Action
Natural-language knowledge is still not executable authority.
Only explicit procedure candidates may later enter the existing validated skill/capability chain.
