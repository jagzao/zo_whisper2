# PLAN-ZMI-CAPTURE-001 — Live Capture implementation

## Status
FROZEN_FOR_IMPLEMENTATION

## Branch
`feat/zmi-live-capture-v1`

## Base
`feat/zmi-documentation-synthesis-v2 @ 5da0ab6df62ec5a6ad59ffbc94f7ecddec7dc18d`

Documentation V2 heavy validation is separate. This branch must not weaken or bypass its contracts.

## CI/CD delivery strategy
Use small vertical slices.
Each slice:
1. implement;
2. targeted deterministic tests;
3. Ruff/typecheck changed surface;
4. commit;
5. push;
6. verify remote SHA;
7. checkpoint.

Do not wait until the whole epic before first push.

## Slice A — Domain + durable session store
Implement:
- capture package/domain models;
- status enums;
- filesystem layout;
- atomic session/segment manifests;
- capture root security resolver integration;
- CRUD/read service methods;
- state transition validation;
- retention eligibility function.

Suggested modules:
`src/transcript_pipeline/capture/models.py`
`store.py`
`service.py`
`retention.py`

Tests:
CAP-08/09/30/31/32/34/36/37/38/39/44/48 relevant subset.

## Slice B — Chunk ingestion + sealing
Implement:
- capture API endpoints for session/create/start/status;
- ordered chunk PUT;
- idempotent hash ACK;
- conflict on same index/different hash;
- segment seal;
- atomic concatenation;
- ffprobe validation;
- queue state.

Do not implement browser recording yet.
Test entirely with synthetic binary/media fixture.

Commit/push.

## Slice C — Browser capture + ROI
Implement vanilla-JS Live Capture UI in existing dashboard:
- setup modal/card;
- camera/mic enumeration;
- permission handling;
- preview;
- ROI overlay selection/reset;
- canvas crop stream;
- audio track composition;
- MediaRecorder codec negotiation;
- 5s default data events;
- 10m logical segment rotation;
- pause/resume/stop state machine;
- bounded IndexedDB unsent chunk queue;
- upload retry;
- visible timers/progress;
- audio analyser warning.

Keep JS modular enough to unit-test state logic; if current repo has no JS test harness, extract deterministic state functions to a small module and test via Playwright only after review; Python/static contract tests may cover generated template/API bindings in light phase.

No framework/build system introduction.

Commit/push.

## Slice D — Durable segment worker
Implement one capture worker:
- filesystem-derived queue;
- worker lifecycle tied safely to dashboard/app composition or dedicated package worker;
- stale PROCESSING recovery;
- one-at-a-time processing;
- ffprobe audio detection;
- keyframe extraction;
- Whisper only when audio stream exists;
- authoritative saved segment transcript;
- no semantic docs per segment;
- bounded retry.

Prefer reuse of one lazily loaded `SimpleScanProcessor` instance.

If existing processor needs an explicit selected-project override, add a backwards-compatible optional project override rather than filename hacks.

Commit/push.

## Slice E — Session evidence aggregation
Implement:
- aggregate all PROCESSED segments;
- shift transcript timestamps by segment start offset;
- shift frame timestamps;
- copy/hardlink frame assets into aggregate frames dir with collision-safe names;
- write session aggregate `*_segments.json`;
- write aggregate `frame_mapping.json`;
- preserve segment provenance;
- active transcript selection.

Do not synthesize per segment.

Commit/push.

## Slice F — External transcript + Documentation V2 finalization
Implement:
- transcript upload/paste endpoints;
- TXT/PLAIN;
- strict VTT/SRT parser;
- active transcript switching;
- untimed semantics;
- WAITING_FOR_EXTERNAL_TRANSCRIPT;
- final Documentation V2 invocation;
- late transcript regeneration with no Whisper/keyframe/OCR rerun when persisted evidence supports it;
- session-level Knowledge Package/publisher only.

Commit/push.

## Slice G — Retention + session UX
Implement:
- session list/details;
- source preview/viewed event;
- retention suggestion badges 90/180d;
- explicit delete-source confirmation/action;
- preservation of derived outputs;
- sourceMediaState audit.

Commit/push.

## Slice H — Fast all-light consolidation
Add:
`scripts/capture_fast_ci.py --slice A..G --all-light`

Behavior mirrors Documentation V2 fast CI:
- no LLM;
- no real media;
- no Docker;
- no full E2E;
- compact JSON;
- raw logs artifacts;
- bounded parallelism.

Run all targeted CAP tests, Ruff, compileall, targeted Pyright.

Push final light commit and stop at READY_FOR_CHATGPT_REVIEW.

## Post-review heavy — NOT NOW
After ChatGPT review and RAM gate:
- full pytest;
- security;
- smoke;
- Playwright camera flow with fake media devices;
- browser refresh/recovery;
- Docker if relevant;
- long synthetic 3h state-machine simulation;
- real webcam acceptance only after deterministic heavy is green.

## Real acceptance — AFTER heavy
Use a non-sensitive test recording:
1. camera points at a screen;
2. select ROI;
3. record > one logical segment;
4. verify segment 1 processes while segment 2 records;
5. stop;
6. inspect generated V2 manual;
7. test no-audio/external untimed transcript;
8. verify retention metadata only, no deletion.

No P&G/client media as the first acceptance.
