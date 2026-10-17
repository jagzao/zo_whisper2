# TEST-MATRIX-ZMI-LIFECYCLE-001

## Compression

- L01 valid output retains streams and duration and is smaller -> provenance complete, source removed only after publish/hash verification.
- L02 encoder failure/missing output/corrupt container/no video stream/invalid duration -> source retained, failure surfaced.
- L03 audio policy mismatch or duration difference above `max(2s, 5%)` -> source retained.
- L04 output same size/larger/under minimum reduction -> source retained.
- L05 collision, atomic rename failure, persistence/index failure, hash mismatch -> no source removal; retry safe and idempotent.
- L06 crash after publish before cleanup -> retry proves linked output and completes safely without overwrite.
- L07 cleanup failure -> `CLEANUP_PENDING`, bytes saved/status accurate; unrelated paths never touched.

## Live Capture

- L08 three or more ACKed fragments arrive out of order -> exactly one final assembled in sequence, full expected duration within tolerance, playable via native browser player.
- L09 missing/unACKed/server-missing/duplicate fragment -> finalization blocked or reports incomplete; no false completed status.
- L10 final hash/duration/manifest invalid -> retain all source fragments and prior final; no cleanup.
- L11 processing failure, partial mapping, audio missing, cancellation, restart -> recoverable fragments retained.
- L12 all chunks processed + finalized mappings + verified final -> session-owned fragments/intermediates removed; final, manifest, docs remain.

## UI/data/docs

- L13 duration column formats <1h `MM:SS`, >=1h `H:MM:SS`, from persisted/probed metadata.
- L14 delete action always visible; active capture/upload/processing disabled with correct reason; ready user media enabled; internal chunks absent.
- L15 crop touch drag creates visible nonzero rectangle; pointer capture works outside bounds; cancel closes cleanly; portrait/landscape/object-fit positions map to video coordinates.
- L16 Clear Crop adjacent to crop controls; desktop mouse and mobile touch both work.
- L17 regeneration uses persisted evidence; spies fail if transcription, ffmpeg/keyframes, OCR or vision execute; new version recorded and selectable; reprocess separate.
- L18 mobile and desktop regeneration status/actions render and errors are understandable.
- L19 localhost/LAN share backend root and normalized video/project/job/docs/worker state plus served SHA.
- L20 synthetic full lifecycle and Host E2E prove final video plays completely and cleanup state is accurate.
- L21 production deployment health, served revision, data parity, rollback reference; no user-data deletion during test.

Use synthetic media and isolated test roots. Store machine-readable results under existing ignored `artifacts/gates/`; no media/transcript fixtures from real users.
