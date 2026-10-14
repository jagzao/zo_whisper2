# EPIC-ZMI-CAPTURE-001 — Live Capture to Knowledge

## Status
FROZEN_FOR_IMPLEMENTATION

## Goal
Add a first-class Live Capture feature to the existing Zo Media Intelligence dashboard so the user can record a physical screen/process through a webcam/camera, upload progressively while recording continues, process sealed segments in the background, and produce one session-level evidence-grounded Documentation V2 artifact.

This epic extends the current local-first product. It does not convert the dashboard into a remotely exposed service.

## Product outcome

```text
Camera / microphone
      |
      v
Browser Live Capture
      |
      +-- local preview + ROI mask
      +-- audio-level warning
      +-- progressive chunk upload
      |
      v
Durable Capture Session
      |
      +-- 10-minute logical segments
      +-- sealed media validation
      +-- recoverable queue
      |
      v
Segment Processing while recording continues
      |
      +-- keyframes
      +-- Whisper when usable audio exists
      +-- persisted timestamped transcript segments
      |
      v
Session Evidence Aggregation
      |
      +-- absolute session timestamps
      +-- frames from all segments
      +-- active transcript
      |
      v
Documentation Synthesis V2
      |
      +-- MANUAL.md / MANUAL.pdf
      +-- semantic AI package
      +-- Knowledge Package
      +-- optional Zavi publishing
```

## Core decisions

1. **Portal first.**
   Immediate capture source is the browser camera opened from the current Flask dashboard on the same machine.

2. **Do not weaken current dashboard security.**
   The dashboard remains localhost-only. No LAN Host/Origin exception is introduced in this epic.

3. **Android remains a future transport adapter.**
   The domain must support `capture_source=BROWSER_CAMERA` now and reserve `ANDROID_COMPANION` for the existing CameraX direction later. The capture/session service must not depend on browser-only concepts.

4. **Progressive upload != partial semantic manual.**
   Small chunks are uploaded continuously. A logical media segment is sealed every 10 minutes by default. Sealed segments may be transcribed/keyframed while the next segment is still recording. Documentation synthesis is session-level and happens after the recording stops and required evidence is ready.

5. **Evidence is session-level.**
   Segment boundaries are implementation details. The final manual must not become one document per segment.

6. **External transcript is a first-class source.**
   A transcript may arrive after recording. TXT/VTT/SRT/paste are accepted. If it has no timestamps, preserve it as untimed evidence with `timecoded=false` and `alignment=none`. Never fabricate alignment.

7. **Missing audio does not destroy the recording.**
   Video/frames can still be preserved and processed. If there is no usable transcript, session state becomes `WAITING_FOR_EXTERNAL_TRANSCRIPT` instead of inventing content.

8. **ROI/mask is a privacy and quality tool.**
   User can select a rectangular region of the camera preview. When enabled, only that region is encoded into the recorded stream before upload. Full source frames are not uploaded for that capture.

9. **Retention is advisory, never automatic.**
   Completed source media that has valid documentation and has not been viewed for a configurable number of days can be suggested for deletion. Deletion always requires explicit user action.

10. **Documentation V2 is the sink.**
    Do not create a parallel documentation engine for capture sessions.

## Browser target
V1 target:
- Chromium-based desktop browsers on Windows;
- localhost secure-context behavior;
- webcam/USB camera + microphone.

Graceful unsupported-browser messaging is required.
Safari/mobile/remote-browser parity is not required in V1.

## Default capture parameters
- logical segment duration: 600 seconds (10 min);
- progressive MediaRecorder timeslice/upload chunk: 5 seconds;
- max logical segment duration configurable 5–15 min, default 10;
- preferred source resolution: 1920x1080 when available;
- ROI output preserves crop detail and does not upscale beyond source pixels;
- preferred capture FPS: 15 for documentation-oriented recording;
- codec negotiation through `MediaRecorder.isTypeSupported`, preferring WebM + Opus.

Exact bitrate may be browser-selected unless a bounded tested value is needed.

## Storage lifecycle defaults
Advisory thresholds:
- eligible suggestion: 90 days since source media last viewed;
- stronger stale indicator: 180 days.

Never auto-delete.

Delete-source action may remove:
- sealed capture media;
- raw uploaded microchunks already represented by sealed media.

It must retain:
- session manifest;
- active transcript;
- evidence metadata;
- screenshots/keyframes needed by documentation;
- semantic manual/package;
- knowledge package/publish receipt.

## Out of scope
- remote public SaaS ingestion;
- weakening localhost-only dashboard;
- remote Android TLS/pairing implementation;
- live WebRTC streaming;
- real-time semantic LLM synthesis during recording;
- diarization;
- automatic source deletion;
- perspective/projective correction;
- cloud object storage;
- billing/multitenancy;
- real client media in committed tests.
