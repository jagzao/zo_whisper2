# DELTA-ZMI-DOCS-V2-003 — ChatGPT post-review correctness + real-media coverage

## Status
BLOCKING / FROZEN_FOR_IMPLEMENTATION

## Review base
Reviewed remote HEAD:
`0b25e21e9d8c90b23ba1f9f61c534b3bed335bf8`

The slice/fast-CI recovery succeeded and the architecture is materially implemented, but the branch is NOT ready for heavy validation yet.

The following defects must be fixed with one bounded light-only delta.

---

## F1 — Real recordings can lose most speech evidence

### Problem
`build_evidence_timeline()` currently reconstructs transcript evidence primarily from per-frame `transcription_mapping`.

The production transcription path also persists the authoritative full timestamped segment list as:

`<project-output>/<video_stem>_segments.json`

Per-frame mapping only contains segments close to retained frame timestamps. For sparse keyframes/interval extraction, large portions of spoken content can therefore be absent from the V2 Evidence Plane and semantic synthesis.

This is unacceptable for KT/meeting documentation quality.

### Fix
Add a persisted evidence input resolver that receives `frames_dir`/source identity and loads the saved timestamped segment file when it exists.

Resolution order MUST actually be:

1. authoritative saved `*_segments.json` timestamped segment list;
2. unique timestamped segments recoverable from `frame_mapping.transcription_mapping`;
3. mapped `full_text` at real frame PTS;
4. full transcript untimed fallback only when necessary.

Global saved transcript segments become transcript EvidenceItems even when no frame is nearby.

Frames/OCR remain separate evidence and may share timestamps/links, but frame sampling must never determine which spoken content survives.

No retranscription.

### Tests
Add synthetic fixture where:
- only 3 frames exist over a long recording;
- saved segment file contains >=10 timestamped spoken segments;
- only 3 segments appear in frame mapping.

Assert Evidence Plane contains all saved spoken segments in order.

Also test saved-segment file absent -> mapped fallback still works.

---

## F2 — Built-in no-upstream guard does not correctly patch class methods

### Problem
`default_upstream_guard()` contains dotted targets such as:

`transcript_pipeline.transcription.processor.SimpleScanProcessor.transcribe_file`

but `install_upstream_guard()` uses `rpartition(".")` as though everything before the last dot were a module name. That produces a non-module path ending in `SimpleScanProcessor`, so the transcription/keyframe class-method targets can be silently skipped.

Existing test only proves the engine OCR attribute guard.

### Fix
Represent guard targets as:
- importable module path;
- attribute traversal path;

or implement safe longest-import-prefix traversal.

Explicitly import/resolve guarded modules before patching.

Guard must cover:
- SimpleScanProcessor.transcribe_file
- KeyframeExtractor.extract_keyframes
- engine._ocr_text
- engine._vision_description
- OpenAICompatibleProvider.describe_frame
- OpenAICompatibleProvider.describe_frame_with_prompt when present

Undo must restore exact originals.

### Tests
One test per guarded upstream target proving calling it after guard installation raises `UpstreamWorkAttemptedError`.
No test may rely only on external monkeypatching.

---

## F3 — Synthesis schema validation is too permissive

### Problem
`_validate_fragment_shape()` currently accepts any JSON object.

Examples such as:
- `{}`
- `{"foo":"bar"}`
- malformed nested section arrays

can pass the precheck. An empty merged document can then pass grounding because it contains no claims/procedures to invalidate, potentially producing `MANUAL_READY` with no useful semantic knowledge.

Nested malformed values may also escape typed-status guarantees by raising during merge.

### Fix
Implement deterministic strict fragment schema validation before merge.

Require:
- root object;
- sections/procedures/glossary are arrays when present;
- section entries are objects;
- allowed sectionType;
- claims array;
- each factual claim has non-empty text and non-empty evidenceIds;
- procedure entries/steps shape valid;
- each procedure step has non-empty instruction/evidenceIds;
- glossary entries shape valid when present;
- unknown extra authoritative fields rejected or ignored according to one explicit deterministic policy.

When evidence facts exist, successful synthesis MUST contain at least one meaningful semantic unit:
- grounded claim, or
- grounded procedure step, or
- grounded glossary/reference unit as permitted.

Empty semantic output is INVALID, never MANUAL_READY.

Any parser/merge exception becomes typed `SYNTHESIS_INVALID`, not an uncaught exception.

### Tests
- `{}` => INVALID
- unknown-only JSON => INVALID
- malformed nested type => INVALID, no exception
- empty sections/procedures/glossary with facts => INVALID
- valid reference-only section => READY
- pipeline never throws for malformed provider content

Remove vacuous assertions.

---

## F4 — Partial block failures are silently accepted as complete synthesis

### Problem
If one synthesis block fails after its bounded repair but another block succeeds, current code keeps successful fragments and returns `STATUS_OK` with errors.

That can produce/publish a document missing an entire temporal region while reporting MANUAL_READY.

### Fix
Fail closed for V2 production quality:

If ANY required block fails after its one repair retry:
- synthesis result = SYNTHESIS_INVALID;
- no new KnowledgeDocument becomes current;
- last-good document/manual/package remains untouched;
- no publish.

Keep compact per-block failure evidence.

A future explicit PARTIAL mode can be a separate product decision; do not invent it now.

### Tests
Create multi-block fixture/provider:
- block 1 valid;
- block 2 permanently malformed;
- block 3 valid.

Assert:
- result INVALID;
- document None;
- last-good protected;
- no publisher call.

---

## F5 — Compaction overflow can discard transcript content while retaining only ids

### Problem
When block count exceeds `max_blocks`, current compactor merges overflow into the last block with:
- evidence ids retained;
- `transcript_text=""`;
- only small OCR fragments retained.

This makes the coverage appear complete while semantic synthesis never sees tail speech.

### Fix
Never silently report complete synthesis when transcript evidence is omitted because of compaction limits.

Add explicit coverage metadata, e.g.:
- `coverage_complete: bool`
- `omitted_evidence_ids`
- `truncated_transcript: bool`

Preferred behavior for current V2:
- reduce repeated/redundant OCR first;
- use target/hard bounds;
- if all transcript evidence cannot fit inside the frozen bounded call budget, return a typed incomplete-compaction result;
- synthesis must fail closed as SYNTHESIS_INVALID/NOT_AVAILABLE with reason `input_coverage_exceeded`;
- do not publish an incomplete manual as complete.

Do not increase call count unboundedly.

### Tests
Force >max_blocks using unique transcript evidence.
Assert:
- omission is explicit;
- synthesis cannot return READY;
- no evidence coverage is falsely claimed.

---

## F6 — Fast CI currently contains vacuous/skip-able critical assertions

### Problem
Post-review found critical V2 tests containing constructs that can pass without proving behavior, including:
- `... or True`
- `if False else True`
- last-good metadata assertion ending in `or True`
- a skip path for the semantic last-good test even though it uses a deterministic mock provider

A green ALL_LIGHT is therefore weaker than reported.

### Fix
Remove all vacuous assertions from Documentation V2 tests.

Critical deterministic mock-provider tests must not skip due environment when they do not require optional external dependencies.

ReportLab-specific PDF test may remain an explicit optional skip only where the dependency is genuinely optional and the non-PDF behavior is separately tested.

Add a simple anti-vacuous regression check for Documentation V2 test files that fails on:
- `or True`
- `if False else True`
- unconditional `assert True`

Do not weaken assertions to make CI green.

---

## F7 — Mode override must be validated

### Problem
`mode_override` is assigned directly without enum validation.

### Fix
CLI/domain override must reject unknown DocumentationMode deterministically before synthesis.
Return/raise the existing typed configuration/usage error at the appropriate boundary.

### Tests
- valid KT_SESSION accepted;
- unknown mode rejected;
- evidence-only invalid override does not silently succeed with an invalid mode.

---

## CI/CD execution rule

This is a small post-review delta. Do NOT restart WP-01..WP-20.

Implement only F1-F7.

Use fast deterministic feedback:
1. targeted new regression tests;
2. affected existing DV2 tests;
3. Ruff changed surface;
4. targeted Pyright/typecheck;
5. compileall;
6. `python scripts/docs_v2_fast_ci.py --all-light`.

Commit/push once coherent, or at most two small commits if F1 evidence resolver is isolated from F2-F7 validation fixes.

No heavy validation.
No real media.
No Docker.
No Playwright.
No P&G.
No merge/deploy.

## Acceptance

Required before next ChatGPT review:
- authoritative saved timestamp segments drive real-media evidence when available;
- no-upstream guard actually intercepts every named upstream entry point;
- malformed/empty provider JSON cannot produce MANUAL_READY;
- any failed synthesis block fails closed;
- compaction cannot silently omit transcript coverage;
- no vacuous V2 assertions;
- mode override validated;
- ALL_LIGHT PASS;
- remote HEAD verified.

Final state:
`READY_FOR_CHATGPT_REVIEW`.
