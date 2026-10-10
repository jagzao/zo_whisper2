# PLAN-ZMI-DKR-005 - Upload approval and pending processing queue

## Parent
`.agents/deliverables/US-ZMI-DKR-005-automatic-upload-processing.md`

## Work packages

1. Keep validated uploads in resumable staging until the user approves a batch.
2. Promote only the approved upload IDs, then start or queue one full run;
   manual `Process pending` promotes all ready staged uploads.
3. Keep unapproved staged sessions out of startup recovery; resume approved
   media from the normal input folders after restart.
4. Support selecting multiple files with two concurrent resumable uploads and
   independent per-file status.
5. Include `Video_compress/` items in `/api/files` and honor project video
   folders in the compressor.
6. Rebuild the local Docker service and verify the served API and UI after the
   active video-processing run finishes.
7. Use atomic, fsynced upload checkpoints and reconcile the `.part` file against
   its committed offset after interruptions.
8. Persist FIFO pipeline jobs and lifecycle events in SQLite; recover interrupted
   jobs on startup and run only one heavy job at a time.
9. Expose queue counts, job history, and event cursors to the dashboard API.
10. Keep Edit available before transcription for manual project assignment;
    route those assignments through compressor and transcription lookup.
11. Verify any Teams VTT/video name pairing against transcript content before
    renaming; duration alone is not sufficient evidence.
12. Make detailed, transcript-grounded tutorial generation project-driven, so
    P&G videos do not depend on a filename containing `tutorial`.
13. Add a durable outbox for tutorial AI packages; send them to Zavi's
    authenticated ingestion API using the configured project ID. Keep retries
    idempotent and keep Zavi/provider credentials out of Whisper.
14. In Zavi, embed imported tutorial chunks with its configured embedding
    provider and preserve source provenance. Keep imported knowledge
    `unverified` until reviewed; scope retrieval to the matching client project.
15. Surface Zavi sync status/retry in Whisper without blocking local pipeline
    completion when Zavi is unavailable.

## Validation

- Targeted dashboard/compressor pytest modules.
- `python scripts/quality.py` and `python scripts/smoke.py`.
- Local container health and `/api/files`, `/api/folders`, `/api/status` checks.
- Verify generated manual/AI package content, durable outbox restart behavior,
  Zavi project mapping, idempotent ingestion, and vector retrieval once linked.

## Risk and rollback

- A process can be lengthy for large media. It runs in a background thread; the
  API returns after queueing and reports live status.
- Data migration uses moves only after target collision and size checks. Source
  files remain untouched until each destination is verified.
