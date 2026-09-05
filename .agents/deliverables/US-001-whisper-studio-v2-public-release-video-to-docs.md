# US-001 — Whisper Studio v2: Public Release + Video-to-Documentation Engine

## Status
READY FOR PROJECT-LEAD EXECUTION

## Objective
Transform the current `zo_whisper2` codebase into a portfolio-grade, release-ready product branded as **Zo Whisper Studio**, suitable to publish publicly as a Python flagship project and distribute free to followers/subscribers, while adding the core capability:

> **Video ingestion → synchronized speech + screen understanding → human documentation + AI-ready structured knowledge.**

This delivery is intentionally end-to-end. The project-lead must implement, validate, fix, re-run, and complete all applicable quality gates before declaring the work done.

---

# 1. Product outcome

The finished product must clearly demonstrate professional Python engineering, not only transcription.

Primary positioning:

**Zo Whisper Studio — Local-first AI media intelligence that converts meetings, tutorials and screen recordings into searchable transcripts, structured documentation and AI-ready knowledge.**

Core flow:

```text
VIDEO / AUDIO / DOCUMENTS
        ↓
Media validation + metadata
        ↓
FFmpeg audio extraction / compression
        ↓
faster-whisper transcription + timestamps
        ↓
Scene / keyframe detection
        ↓
OCR / Vision understanding
        ↓
Temporal alignment
        ↓
Evidence model
        ↓
Documentation Engine
        ├── Human documentation
        └── AI knowledge package
```

The product must remain local-first. External LLM use remains explicit opt-in and subject to existing privacy boundaries.

---

# 2. Scope

## 2.1 Public productization

### Required
- Public-facing name: **Zo Whisper Studio**.
- Keep package/internal compatibility where changing names would create unnecessary breakage, but remove `zo_whisper2` from visible product branding.
- Update README, app header, metadata and screenshots.
- Produce a clear quick-start path for a new user.
- Detect and explain missing dependencies such as Python version, FFmpeg, optional Tesseract and optional LLM provider.
- Preserve a lightweight core install.
- Preserve MIT licensing unless explicitly changed later by the owner.
- Add or update architecture diagrams describing the actual current system.
- Mark `watcher/` and `deepseek/` unambiguously as experimental/non-core. Prefer moving them out of the main product surface if doing so is safe; otherwise isolate them clearly in docs and quality configuration.
- Prepare repository for a real `v1.x` release.

### Distribution note
The repository is MIT/open-source, therefore “free for subscribers” is a distribution/marketing benefit, not technical exclusivity. Do not implement false access restrictions into the public repository unless a separate distribution model is explicitly requested.

---

# 3. Futuristic dashboard redesign

Implement the approved visual direction as a production UI, not as a static mockup.

## 3.1 Visual language
- Dark near-black base.
- TRON-inspired cyan/electric-blue accents.
- Restrained glow; readability is more important than decoration.
- Angular/panel geometry without sacrificing responsive behavior.
- High contrast and accessible focus states.
- Consistent iconography.

## 3.2 Header — mandatory controls
The following existing functionality must remain visible and usable in the header:
- Product title/logo.
- System status (`Listo` / `System Ready`).
- `RUN Full`.
- `Solo Comprimir`.
- `Solo Transcribir`.
- Dashboard/grid icon.
- Logs/documents icon.

Do not hide these behind menus on normal desktop widths.

## 3.3 Main dashboard
Replace implementation-centric counters with useful operational metrics while retaining storage visibility where needed.

Preferred summary metrics:
- Files processed.
- Audio/video duration processed.
- Success rate.
- Average processing time.

Storage/folder counts may be available in a secondary storage/explorer view.

## 3.4 Pipeline visualization
Show the real execution lifecycle and current step where possible:

```text
UPLOAD → ANALYZE → COMPRESS → TRANSCRIBE → VISION/OCR → ROUTE → DOCUMENT → STORE
```

Per-stage status should support at least:
- pending
- running
- completed
- skipped
- failed

When timing information exists, display duration per stage.

## 3.5 Files / jobs table
Keep the useful current behavior, redesign presentation.

Required concepts:
- filename
- project
- source type
- language
- state
- output/transcript availability
- processing duration when available
- actions

Actions:
- View
- Edit
- Delete with confirmation
- Open generated documentation when available
- Open AI package/details when available

Backend/internal states such as `completed_routed` must be mapped to human-readable UI labels.

## 3.6 Transcript/document workspace
Opening a processed item must provide a useful workspace, not just a raw text page.

Include where data exists:
- audio/video player
- transcript
- timestamp navigation
- search
- language
- model
- duration
- processing metadata
- generated documentation
- evidence links to source timestamps/screenshots

---

# 4. Video ingestion → documentation engine

This is the central new capability.

## 4.1 Supported source
At minimum preserve current video support:
- mp4
- mkv
- mov
- avi
- webm

Audio-only files continue to work.

## 4.2 Media analysis
For video:
- extract audio for transcription
- collect reliable media duration and metadata
- detect meaningful screen/scene changes
- extract only the frames required for documentation/evidence
- avoid unbounded frame growth on long recordings

Use existing FFmpeg infrastructure and current keyframe/scene work where appropriate.

## 4.3 Critical timestamp correction
**Release blocker:** do not use uniformly estimated timestamps for scene/smart-scene frames when generating evidence-backed documentation.

Scene/keyframe extraction must retain the real timestamp / PTS associated with each selected frame.

Acceptance:
- Each retained frame has a trustworthy source timestamp.
- Timestamp provenance is preserved into later artifacts.
- Automated tests prove temporal mapping for known synthetic video fixtures.

## 4.4 Transcription alignment
Each documentation candidate must be alignable to nearby transcript segments.

Implement a domain model such as equivalent typed structures for:
- source media
- transcript segment
- visual evidence
- aligned evidence block
- generated procedural step

Exact naming is implementation-owned, but raw dictionaries must not spread across the architecture if a stable typed model is justified.

Each evidence block should support:
- source media id
- timestamp start/end or point timestamp
- transcript excerpt/reference
- frame reference when applicable
- screen analysis when applicable
- confidence
- provenance

## 4.5 Screen understanding
Use a layered strategy:
1. Local/basic detection first where sufficient.
2. OCR/hash change detection to avoid redundant vision calls.
3. Vision LLM only when enabled and allowed by privacy policy.

Do not require a remote provider for core operation.

## 4.6 Documentation generation modes

### A. Human documentation
Generate a documentation bundle appropriate for tutorials/process recordings.

Minimum:
```text
manual/
  MANUAL.md
  assets/
    step-001.webp
    step-002.webp
  metadata.json
```

Optional but desirable:
- standalone HTML rendering
- PDF export only if it does not introduce excessive coupling/dependency cost

`MANUAL.md` should contain when applicable:
- title
- purpose
- prerequisites
- numbered procedure
- relevant screenshot per step
- warnings/notes
- expected outcome
- troubleshooting
- glossary
- source timestamp deep-reference

Generated instructions must be grounded in source evidence.

### B. AI-ready knowledge package
Generate a machine-readable package designed for RAG/agents.

Minimum:
```text
ai-package/
  knowledge.md
  manifest.json
  steps.json
  chunks.jsonl
  assets/
```

The contract must be versioned, e.g.:

```json
{
  "schema_version": "1.0",
  "source": {},
  "procedures": [],
  "artifacts": [],
  "generated_at": "..."
}
```

A procedural step must be able to carry fields equivalent to:
- id
- order
- title
- instruction
- action
- target
- timestamp / timestamp range
- transcript evidence reference
- frame reference
- confidence
- tags

Do not force fields when evidence cannot support them.

## 4.7 Confidence and hallucination control
Generated procedures cannot be treated as factual merely because an LLM returned them.

Required rules:
- Every concrete generated step must point to source evidence.
- Unsupported claims must be omitted or flagged.
- Low-confidence content must be marked for human review.
- The system must distinguish generated interpretation from captured evidence.
- Never fabricate UI labels, menu names, commands or values that were not present in transcript/visual evidence.

Recommended confidence states:
- high
- medium
- low / review-required

## 4.8 Human review
Provide a basic workflow to review generated documentation before treating it as final.

Minimum capabilities:
- see each step with evidence
- edit instruction text
- remove invalid step
- identify low-confidence items
- regenerate documentation from approved structured content without retranscribing media

---

# 5. Existing meeting/document intelligence

Preserve and integrate useful current behavior:
- faster-whisper local transcription
- language handling
- routing by project
- handler/plugin architecture
- MarkItDown document ingestion
- OCR / image hash
- optional vision LLM
- current privacy guard
- current external-AI redaction policy
- filesystem boundary protection
- content-hash/idempotency behavior

Refactor only where needed to avoid parallel implementations of the same concepts.

The documentation engine should consume reusable core services rather than duplicate `MeetingDevHandler` logic.

---

# 6. Architecture requirements

## 6.1 Separation
Recommended logical boundaries:

```text
media/
transcription/
vision/
alignment/
evidence/
documentation/
export/
dashboard/
```

Exact directories are implementation-owned. The goal is separation of responsibilities, testability and reuse.

## 6.2 Stable result contracts
Avoid bare booleans for non-trivial pipeline stages.
Use explicit typed results/errors where failure/retry/skipped states matter.

## 6.3 Idempotency
Reprocessing the same input must not accidentally duplicate outputs.

The project-lead must define behavior for:
- unchanged media
- media changed at same path
- documentation regeneration only
- failed partial run
- user-requested force re-run

## 6.4 Observability
Every execution should expose enough data to diagnose failures.

Capture at least:
- run id
- source media
- stage
- start/end timestamps
- duration
- result
- failure reason
- retryability where relevant
- model/provider metadata when AI is used, without leaking secrets

User-facing logs must not expose secrets or private absolute paths unnecessarily.

---

# 7. Privacy and security

Existing privacy-first principles remain release requirements.

## Mandatory
- Dashboard stays localhost-only by default and fail-closed.
- Safe filesystem boundary remains enforced.
- Upload paths and file operations must not permit traversal.
- External LLM stays disabled by default.
- Confidential project classification continues to block remote LLM usage.
- Image/frame upload requires explicit permission according to current policy.
- Secret redaction applies at the external-provider boundary.
- Generated artifacts must not accidentally contain API keys, authorization headers or environment values.
- File deletion and mutating operations remain protected against inappropriate browser-origin requests according to the existing local security model.

## Public repository hygiene — P0 release blocker
Before publishing/promoting the project:
- scan current working tree for secrets and private identifiers
- scan git history, not only current files
- verify no real client recordings/transcripts/screenshots exist
- verify screenshots/demo data are synthetic
- verify no real client identifiers remain in public history unless intentionally public and safe
- resolve the currently divergent/re-written history cleanly
- do not weaken branch protection permanently merely to make the cleanup convenient
- restore normal protection after any explicitly approved history rewrite

The final release evidence must record the resulting clean commit SHA.

---

# 8. Packaging and first-run UX

A new technical user should be able to get from clone to first successful transcription without reverse engineering the repository.

Required:
- Python version validation
- FFmpeg validation
- clear optional dependency checks
- configuration template generation/copy guidance
- safe sample project configuration
- synthetic sample or documented sample workflow
- actionable error messages

Keep supported CLI entry points.

Prefer cross-platform Python commands for public docs. Windows helper scripts may remain as convenience wrappers.

---

# 9. README / portfolio presentation

README should become a product landing page + engineering reference.

Top section must quickly communicate:
- what the product does
- local-first/privacy value
- video → documentation capability
- one strong current screenshot/GIF
- installation
- quick demo

Then document:
- architecture
- pipeline
- human documentation output example
- AI package example
- security/privacy model
- testing strategy
- extensibility

Do not use real customer/client data in examples.

Add badges only if they represent real automated checks.

---

# 10. Release readiness

Prepare release artifacts and documentation for an initial polished release after all gates pass.

Required:
- coherent semantic version
- changelog/release notes
- clean release commit
- successful CI at release commit
- updated screenshots
- installation tested from clean environment
- license present
- security/privacy docs current

A GitHub release may be created only when the repository state is clean and all mandatory gates are green.

---

# 11. Testing requirements

The project-lead owns test implementation and must add/modify tests for all changed behavior.

## 11.1 Unit tests (UT)
At minimum cover:
- timestamp/PTS parsing
- temporal alignment
- evidence creation
- confidence rules
- documentation step generation/validation
- manifest/schema serialization
- artifact path rules
- idempotency/re-run decisions
- state mapping for dashboard
- configuration validation
- privacy gating of new vision/documentation paths

Tests must be deterministic and must not require paid external services.

## 11.2 Integration tests
At minimum:
- synthetic media → transcription adapter/stub → frame extraction metadata → alignment
- evidence → documentation bundle
- evidence → AI package
- document ingestion coexisting with video evidence
- privacy guard integration
- output regeneration without re-running expensive upstream stages

Use real FFmpeg in integration coverage where appropriate and available in CI.

## 11.3 End-to-end tests
Extend Playwright/browser E2E to cover the actual user journey with synthetic data.

Minimum E2E scenarios:
1. Dashboard loads successfully.
2. Header contains all mandatory controls/icons.
3. Upload or synthetic fixture appears as a job.
4. Full pipeline can be triggered using a controlled test fixture/stubbed expensive stage.
5. Pipeline state updates visibly.
6. Transcript can be opened.
7. Documentation can be opened.
8. Timestamp/evidence navigation works.
9. Human documentation review/edit can persist.
10. AI package details/download access works where implemented.
11. Delete requires confirmation and behaves safely.
12. Logs/status view is reachable.

Capture screenshots as CI artifacts.

## 11.4 Smoke tests
Create a fast release smoke suite.

Must validate:
- package imports
- settings load with safe defaults
- dashboard boots on localhost
- health endpoint or equivalent responds
- FFmpeg detection path works
- synthetic basic transcription pipeline can initialize
- documentation renderer can generate artifacts from a tiny fixture

Smoke should fail fast and provide actionable output.

## 11.5 Regression tests
Existing behavior that must not regress:
- current audio transcription
- project routing
- language handling
- transcript editing
- upload/delete/save/run endpoints
- local-only dashboard enforcement
- SafePathResolver protections
- external LLM opt-in
- confidential data remote-blocking
- document conversion tests
- current synthetic screenshot workflow

When fixing any defect discovered during this delivery, add a regression test where practical.

## 11.6 Security tests
At minimum add/retain automated checks for:
- path traversal
- unsafe upload filenames
- unsupported file types
- oversized/abusive upload policy if currently unbounded
- host/origin/token protections
- external AI privacy gates
- secret leakage into generated artifacts/logs
- unsafe archive/document handling where applicable
- history/current-tree secret scans in release procedure
- dependency audit

## 11.7 Performance / resource checks
Not every run needs a benchmark gate, but establish practical regression signals for:
- long video frame explosion prevention
- memory-safe processing of large media
- bounded number of vision analyses
- no repeated expensive transcription during documentation-only regeneration

Document expected behavior for CPU-only operation.

---

# 12. CI quality gates

The existing gates remain and must be updated when new code requires them.

Mandatory green gates for final delivery:
- Ruff / lint
- Pyright/type validation
- UT on supported Python matrix
- integration tests
- security suite
- pip-audit / dependency audit
- secret scan
- E2E
- smoke
- any new documentation/schema validation

No gate may be silently skipped and reported as success if its required dependency is unexpectedly unavailable.

Optional features may have explicit SKIPPED semantics only when the skip is intentional, documented and does not hide a release-critical failure.

---

# 13. Autonomous project-lead validation loop

The project-lead must execute this loop until completion:

```text
1. Read this US + repository memory/rules.
2. Inspect current code and baseline tests.
3. Create implementation plan internally.
4. Implement a coherent slice.
5. Run relevant narrow tests.
6. Diagnose failures.
7. Fix root cause.
8. Add regression coverage where appropriate.
9. Continue remaining slices.
10. Run full UT + integration + security + smoke + E2E + regression suite.
11. Run lint/type/dependency/secret gates.
12. Perform clean-install validation.
13. Perform synthetic full user journey.
14. Inspect generated human manual and AI package for grounding/provenance.
15. Fix every release-blocking issue found.
16. Repeat full applicable gates.
17. Stop only when all Definition of Done items are satisfied or a true external blocker requires owner action.
```

Time/iteration count is not a reason to stop early.

Do not replace failed validation with a TODO.
Do not mark functionality complete solely because code was written.

If an external blocker exists, document exactly:
- blocker
- evidence
- what was already completed
- single owner action required
- exact continuation point

---

# 14. Definition of Done

This US is DONE only when all applicable statements are true:

- [ ] Product branding is Zo Whisper Studio in public surfaces.
- [ ] Approved futuristic dashboard is implemented, responsive and usable.
- [ ] Header retains all mandatory controls/icons.
- [ ] Existing core transcription flow still works.
- [ ] Video ingestion works for supported formats.
- [ ] Selected visual frames retain real source timestamps/PTS.
- [ ] Transcript and visual evidence can be temporally aligned.
- [ ] Evidence/provenance model exists and is persisted/exportable.
- [ ] Human manual generation works from synthetic video fixture.
- [ ] AI-ready package generation works from the same source.
- [ ] Every generated procedural step is grounded or flagged for review.
- [ ] Documentation can be reviewed/edited without retranscribing.
- [ ] External AI remains opt-in and privacy-gated.
- [ ] No secrets/private client data exist in release tree/artifacts.
- [ ] Public git history hygiene is explicitly validated before promotion.
- [ ] README/documentation accurately describes implementation.
- [ ] Installation succeeds from a clean supported environment.
- [ ] UT pass.
- [ ] Integration tests pass.
- [ ] Smoke tests pass.
- [ ] E2E tests pass.
- [ ] Regression tests pass.
- [ ] Security tests pass.
- [ ] Lint/type checks pass.
- [ ] Dependency and secret scans pass.
- [ ] CI is green at final commit.
- [ ] Updated synthetic screenshots/demo assets exist.
- [ ] Release notes/changelog are ready.
- [ ] Final handoff includes validation evidence and remaining non-blocking ideas separately.

---

# 15. Final handoff required from project-lead

The project-lead must return a concise completion report containing:

## What changed
Major functional/architectural changes only.

## Generated product outputs
Paths/examples for:
- human manual
- AI package
- screenshots

## Validation evidence
For each gate:
- command/workflow
- result
- relevant counts

## Security/privacy evidence
- current-tree scan
- history scan/rewrite status
- external LLM default state
- synthetic-data verification

## Release status
One of:
- `READY_FOR_OWNER_AUDIT`
- `BLOCKED_EXTERNAL_ACTION`

Do not use `DONE` if any mandatory gate is red or unverified.

---

# 16. Out of scope unless required by implementation

- Hosted multi-tenant SaaS.
- User billing.
- Cloud GPU infrastructure.
- Mobile application.
- Enterprise SSO.
- Exclusive subscriber licensing/access enforcement.
- Autonomous execution of procedures learned from videos; this release produces structured knowledge suitable for future agents, but does not execute those procedures automatically.

---

# 17. Owner audit after implementation

After the project-lead reports `READY_FOR_OWNER_AUDIT`, Juan + ChatGPT will independently audit:
- repo/code changes
- CI evidence
- actual UI
- synthetic full run
- generated manual quality
- generated AI package quality/schema
- security/privacy state
- public-release readiness

Only after that audit should the project be actively promoted on social networks as the polished public release.
