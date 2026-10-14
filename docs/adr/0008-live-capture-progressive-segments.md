# ADR 0008 — Live Capture uses progressive chunks and durable logical segments

## Status
Accepted.

## Context
Zo Media Intelligence needs to record long physical/screen-facing camera sessions without holding a multi-hour Blob in browser memory and should begin expensive processing before recording ends.

The dashboard is currently localhost-only and deliberately has no user-account/remote-access security model.

## Decision
Use browser `getUserMedia` + `MediaRecorder` in the existing localhost dashboard.

During each logical segment:
- recorder emits small data chunks on a timeslice;
- chunks upload durably and idempotently;
- at default 10 minutes the recorder is stopped/finalized;
- server seals/validates the segment;
- worker begins keyframe/transcription processing;
- a new recorder starts immediately on the same MediaStream.

Final documentation is generated once at session level.

ROI is implemented before encoding with a canvas capture stream, so when ROI is enabled the server never receives the excluded area.

The domain is transport-neutral and reserves a future Android companion source, but this ADR does not weaken localhost-only access or implement remote LAN ingestion.

## Consequences
Positive:
- bounded browser memory;
- recoverable uploads;
- early processing;
- reuses WebM support and current pipeline;
- future Android transport can reuse session semantics;
- excluded ROI pixels stay local.

Costs:
- tiny recorder restart gap at logical segment boundary;
- durable session/worker state required;
- final session evidence must shift segment timestamps;
- browser compatibility must be explicit.

## External transcript
Transcript is independent from media storage.
Untimed text remains untimed; no artificial alignment.

## Retention
Raw source media deletion is advisory and user-confirmed only.
