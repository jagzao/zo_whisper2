# TEST-MATRIX-ZMI-CAPTURE-001

## Status
FROZEN_FOR_IMPLEMENTATION

## Domain/store
LC-01 session UUID server-generated
LC-02 atomic session write survives simulated interrupted temp write
LC-03 valid state transitions
LC-04 invalid transition rejected
LC-05 one active recording default
LC-06 ROI normalized validation
LC-07 no arbitrary path in model/API
LC-08 capture root traversal rejected

## Chunks/seal
LC-09 first chunk ACK
LC-10 same chunk/same hash idempotent
LC-11 same chunk/different hash conflict
LC-12 oversized chunk rejected
LC-13 out-of-range sequence rejected
LC-14 seal fails missing chunk
LC-15 chunks concatenated in exact order
LC-16 temp output atomically becomes media
LC-17 ffprobe rejects fake extension/non-media
LC-18 sealed status queues work
LC-19 duplicate seal idempotent

## Browser state / API contract
LC-20 unsupported MediaRecorder clear error
LC-21 permission denied clear error
LC-22 codec fallback order deterministic
LC-23 start creates segment 1
LC-24 10m rotation seals N and starts N+1
LC-25 pause seals current segment
LC-26 resume starts new segment
LC-27 stop seals final segment
LC-28 uploaded ACK releases in-memory Blob reference
LC-29 failed upload remains in durable browser queue
LC-30 bounded retry no infinite loop
LC-31 ROI output contains crop only
LC-32 ROI reset restores full-frame capture
LC-33 audio track retained in ROI canvas stream
LC-34 audio warning is non-blocking
LC-35 3h simulated clock yields >=18 segments without giant aggregate Blob

## Worker
LC-36 QUEUED claimed once
LC-37 stale PROCESSING recovers after restart
LC-38 one local worker concurrency
LC-39 no audio stream skips Whisper
LC-40 audio stream runs Whisper once
LC-41 empty Whisper result => NO_SPEECH_DETECTED
LC-42 keyframes extracted for capture video
LC-43 no per-segment semantic manual/package publish
LC-44 retry bounded
LC-45 selected project override reaches processor without filename hack

## Aggregation
LC-46 transcript timestamps shifted by segment offset
LC-47 frame timestamps shifted
LC-48 frame filenames collision-safe
LC-49 segment provenance retained
LC-50 session segments ordered deterministically
LC-51 aggregate saved segments cover all segment speech
LC-52 aggregate mapping references valid frame assets
LC-53 final docs invoked once per session completion

## External transcript
LC-54 TXT upload untimed NONE alignment
LC-55 paste untimed NONE alignment
LC-56 valid SRT timed/source timestamps
LC-57 valid VTT timed/source timestamps
LC-58 malformed SRT/VTT rejected
LC-59 transcript size bound
LC-60 external transcript preserved alongside Whisper artifact
LC-61 active transcript switch deterministic
LC-62 external untimed transcript never gets fake alignment
LC-63 late transcript regenerates without transcription
LC-64 late transcript regenerates without keyframe extraction
LC-65 late transcript regenerates without OCR when persisted evidence available
LC-66 no usable transcript => WAITING_FOR_EXTERNAL_TRANSCRIPT
LC-67 external transcript exits waiting state

## Documentation/knowledge
LC-68 one session manual, no segment manuals
LC-69 selected DocumentationMode used
LC-70 privacy classification preserved
LC-71 no incomplete publish in waiting state
LC-72 session Knowledge Package only
LC-73 evidence identifies transcript source
LC-74 semantic manual opens from session UI

## Retention
LC-75 <90d no suggestion
LC-76 >=90d eligible suggestion
LC-77 >=180d strong stale indicator
LC-78 incomplete session never eligible
LC-79 waiting transcript never eligible
LC-80 source delete requires explicit action
LC-81 delete source removes heavy media
LC-82 delete source preserves transcript
LC-83 delete source preserves evidence/manual/knowledge
LC-84 deletion audit persisted
LC-85 preview updates lastViewedAt

## Security
LC-86 current localhost Host rule unchanged
LC-87 current Origin rule unchanged
LC-88 mutating capture endpoint requires dashboard token
LC-89 session id cannot escape capture root
LC-90 chunk endpoint cannot overwrite manifest/other segment
LC-91 client MIME not trusted
LC-92 no absolute server path returned
LC-93 transcript upload cannot become executable/path payload
LC-94 no LAN allow-list added
LC-95 synthetic fixtures contain no client data

## Recovery
LC-96 server restart queued work recovered
LC-97 receiving unfinished segment marked RECOVERABLE
LC-98 ACKed chunks survive restart
LC-99 duplicate processing prevented
LC-100 dashboard restart preserves session status truth

## Fast CI
LC-101 slice-specific test manifests
LC-102 all-light includes all capture targeted suites
LC-103 no LLM imported/invoked by fast CI
LC-104 no real camera required by light CI
LC-105 no Docker/Playwright/full pytest in light lane
LC-106 no vacuous assertions in capture tests

## Heavy / post-review
HC-01 Playwright Chromium fake camera permission/recording
HC-02 ROI visual recording smoke with synthetic stream
HC-03 browser reload + unsent IndexedDB recovery
HC-04 concurrent record/upload/worker smoke
HC-05 synthetic 3h state simulation
HC-06 full security regression
HC-07 full pytest
HC-08 Docker/runtime smoke if configured

Heavy is NOT run during implementation.
