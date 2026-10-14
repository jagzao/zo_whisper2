# DELTA-ZMI-DOCS-V2-004 — Real-flow transcript completeness and block grounding

## Status
BLOCKING / FINAL LIGHT DELTA BEFORE HEAVY VALIDATION

## Review base
Reviewed implementation HEAD:
`f9f6c251637ce7a107178244cb2106cfdc0f964d`

F1-F7 from DELTA-003 are materially corrected. This delta addresses issues found by reviewing the real production call order and evidence semantics.

Do NOT rerun WP-01..WP-20.
Do NOT change product scope.
Implement only F8-F10.

---

## F8 — New-video production flow generates docs before authoritative segments file exists

### Evidence
Current `SimpleScanProcessor.process_file()` order is effectively:

```
result = transcribe_file(audio_path)
_integrate_transcription_with_frames(result, frame_info)
_generate_documentation_bundle(...)
save_transcription(audio_path, result)
```

But F1's authoritative evidence resolver reads persisted:
`<output>/<video_stem>_segments.json`

That file is written by `save_transcription()`, so it does NOT exist when documentation is first generated for a new video.

Result: regeneration is complete, but first-pass production documentation can still fall back to sparse frame-near transcript segments and omit speech.

### Required fix
Make authoritative timestamped segments available BEFORE semantic documentation generation.

Preferred low-risk implementation:
1. transcribe;
2. integrate mapping;
3. persist transcription + timestamped segments atomically through existing save path;
4. generate documentation from those persisted segments;
5. mark tracker completed only after the existing process completes.

Documentation remains non-fatal: a docs failure must not erase/rollback a successfully persisted transcript.

If reordering `save_transcription` introduces a concrete invariant conflict, alternatively thread `transcription_result["segments"]` into the V2 evidence resolver as an explicit authoritative source, but DO NOT duplicate persistence logic.

Do not transcribe twice.
Do not write a second segment file format.

### Tests
Add a deterministic process-order test using fakes/spies:
- `save_transcription` happens before `_generate_documentation_bundle`;
- docs can resolve all authoritative segments on first pass;
- docs failure remains non-fatal to transcript persistence;
- tracker completion behavior remains consistent with current contract.

---

## F9 — Per-block synthesis evidence IDs must be enforced, not only prompted

### Problem
Strict schema validation currently verifies that `evidenceIds` are non-empty strings.
Final grounding verifies that ids exist somewhere in the whole timeline.

A provider processing block N can therefore hallucinate/cite a REAL evidence id from another block. Because that id exists globally, final grounding can accept an unrelated claim as grounded.

### Required fix
For each provider response, validate every claim/procedure/glossary evidence id against the CURRENT block's allowed evidence-id set.

Change the fragment validator/request path so it receives:
`allowed_evidence_ids=set(block.evidence_ids)`.

A response citing any id outside the current block:
- is schema/grounding-invalid for that block;
- may use the one existing bounded repair retry;
- if still invalid, entire synthesis fails closed via F4.

Do not rely only on prompt instructions.

### Tests
Multi-block fixture:
- block 1 contains E-001;
- block 2 contains E-002;
- provider for block 1 returns a plausible claim citing E-002.

Assert:
- first response rejected;
- one repair max;
- unrepaired cross-block citation => SYNTHESIS_INVALID;
- cross-block id existing globally does NOT make it valid.

---

## F10 — Full-transcript fallback must not silently truncate to one 1200-char EvidenceItem

### Problem
When no timestamped/mapped transcript evidence is available, fallback currently inserts the full transcript into one raw entry, but `EvidenceItem.transcript_excerpt` is bounded by `MAX_EXCERPT_CHARS=1200`.

A long fallback transcript can therefore silently lose most speech while the EvidenceTimeline appears usable.

### Required fix
Preserve the entire fallback transcript deterministically without fabricating timestamps.

Split full transcript into bounded ordered untimed EvidenceItems:
- each excerpt <= configured evidence excerpt bound;
- all marked `untimed=true`;
- use honest source range semantics (e.g. 0..duration or explicit untimed marker already present);
- deterministic ids/order;
- no semantic invention;
- no content omission except whitespace normalization needed for deterministic chunking.

Do the same for any single persisted transcript segment that exceeds the evidence excerpt bound: split it deterministically rather than silently truncating it.

The synthesis compactor may still reject a document as `input_coverage_exceeded` when the bounded total call budget cannot cover all evidence. That is correct/fail-closed behavior.

### Tests
- long full-transcript fallback > 3x excerpt bound;
- reconstructed concatenated excerpts preserve the original normalized content in order;
- no excerpt > bound;
- all fallback chunks are untimed;
- no fake per-chunk timestamp progression;
- oversized saved segment is split without content loss;
- compaction either covers everything or explicitly fails coverage; never silent success.

---

## Existing DELTA-003 acceptance remains required

Re-run affected tests proving:
- saved segments authoritative when present;
- upstream guard real;
- strict schema;
- partial block fail closed;
- compaction coverage explicit;
- no vacuous critical tests;
- mode override validation.

## Fast CI only

Run:
- new F8-F10 regression tests;
- directly affected V2 tests;
- affected transcription process-order test;
- Ruff changed surface;
- targeted Pyright/typecheck;
- compileall;
- `python scripts/docs_v2_fast_ci.py --all-light`.

No full pytest.
No security/smoke.
No Playwright.
No Docker.
No real LLM.
No real media.
No heavy validation.
No merge/deploy.

## Acceptance before heavy
- first-pass production docs see authoritative full timestamped transcript;
- regeneration remains no-upstream-work;
- claims cannot cite evidence outside their synthesis block;
- no transcript fallback/oversized segment is silently truncated;
- ALL_LIGHT PASS;
- remote SHA verified.

Terminal:
`READY_FOR_CHATGPT_REVIEW`.
