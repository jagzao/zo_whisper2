# TEST-MATRIX-ZMI-DOCS-V2-001

## Status
FROZEN_FOR_IMPLEMENTATION

## Unit / targeted matrix

### DV2-01 mode explicit
Explicit KT_SESSION wins over filename hint.

### DV2-02 artifact mapping
default_artifact_type=KT maps to KT_SESSION when documentation.mode=AUTO.

### DV2-03 safe fallback
No config/provider => REFERENCE, typed reason.

### DV2-04 confidential remote block
Remote synthesis on confidential project is blocked before request.

### DV2-05 local confidential allowed
Configured local provider can receive bounded synthesis blocks according to privacy policy.

### DV2-06 evidence ids stable
Same persisted evidence => same evidence ids.

### DV2-07 segment recovery
Timestamped saved segments preferred.

### DV2-08 mapped segment fallback
Missing saved segment file => unique frame-mapped segments recovered/deduped.

### DV2-09 full transcript fallback
Only full transcript => evidence result explicitly lower fidelity, no fake timestamps.

### DV2-10 low-confidence queue
none-source items enter review queue and do not become synthesis facts automatically.

### DV2-11 compaction order
Blocks preserve chronology.

### DV2-12 OCR dedup
Repeated OCR from near-identical frames does not inflate synthesis input.

### DV2-13 block bounds
Hard character/call bounds respected.

### DV2-14 JSON only
Free-form model response rejected.

### DV2-15 unknown evidence
Claim citing E-999 fails grounding validation.

### DV2-16 missing evidence
Factual claim without refs fails.

### DV2-17 bad procedure
Procedure step without evidence fails.

### DV2-18 reviewed spoof
Model-provided HUMAN_REVIEWED fails/coerces to unreviewed according to frozen validator behavior; never accepted as human review.

### DV2-19 timestamp bound
Out-of-duration ref fails.

### DV2-20 last-good
Invalid synthesis does not overwrite existing valid manual/document.

### DV2-21 screenshot duplicate
Near-identical pHash frames collapse.

### DV2-22 screenshot cap
Global/per-section caps enforced.

### DV2-23 no imagehash fallback
Missing optional hash lib still produces deterministic bounded selection.

### DV2-24 KT template
Synthetic KT document includes summary/context/process/system/decision/risk/open-question/action sections when fixture supports them; no forced procedure.

### DV2-25 tutorial procedure
Synthetic tutorial creates grounded ordered procedure.

### DV2-26 reference no procedure
Reference source can validly output procedures=[].

### DV2-27 semantic manual
MANUAL content comes from KnowledgeDocument, not one heading per EvidenceItem.

### DV2-28 review queue callout
Manual shows count, not 20 empty sections.

### DV2-29 semantic PDF
PDF includes semantic headings/evidence refs and bounded screenshots.

### DV2-30 evidence timeline
EVIDENCE_TIMELINE preserves raw chronological captured evidence.

### DV2-31 chunks semantic
chunks.jsonl count follows semantic units, not frame count.

### DV2-32 chunks metadata
scope/project/artifact/actionability/evidence refs all present.

### DV2-33 raw transcript forbidden
No whole raw transcript/VTT/media keys in package/chunks.

### DV2-34 semantic package
Knowledge Package summary/title/sections originate from KnowledgeDocument.

### DV2-35 no fake procedure
KT document without procedure yields no procedure.json / package procedures.

### DV2-36 real procedure bridge
Tutorial procedure maps to Procedure v1 preserving evidence.

### DV2-37 identity timestamp-independent
generatedAt changes alone do not create new knowledge version.

### DV2-38 semantic version change
Material semantic/evidence change increments existing knowledge version according to current rules.

### DV2-39 publisher compatibility
Existing outbox/publisher receives semantic package unchanged at transport layer.

### DV2-40 regeneration no whisper
Monkeypatch transcription to throw; regenerate succeeds from persisted artifacts.

### DV2-41 regeneration no ffmpeg
Monkeypatch keyframe extraction to throw; regenerate succeeds.

### DV2-42 regeneration no OCR
Monkeypatch OCR to throw; regenerate succeeds.

### DV2-43 regeneration no vision
Monkeypatch frame vision to throw; regenerate succeeds.

### DV2-44 evidence-only provider unavailable
Evidence outputs succeed; synthesis typed unavailable; no false MANUAL_READY.

### DV2-45 malformed retry bound
At most one schema-repair call.

### DV2-46 no recursive loop
Provider invocation count cannot exceed configured block count + one bounded repair per failed response under frozen policy.

### DV2-47 current compatibility
Existing manual/steps metadata callers do not crash.

### DV2-48 synthetic no-client-data
Fixtures contain only synthetic organizations/apps/screens.

## Coding phase gates
Required now:
- DV2 targeted tests
- existing documentation/knowledge regressions touched by changes
- Ruff
- compileall
- Pyright if targeted command is available

Explicitly NOT NOW:
- full test suite
- Docker
- Playwright
- Jenkins
- Sonar
- soak
- real external/local LLM
- real client media

## Heavy phase
After ChatGPT /review only and RAM >6 GiB:
- full pytest/regression
- integration
- security
- smoke
- E2E
- Docker gates
- dependency/secret gates as configured
