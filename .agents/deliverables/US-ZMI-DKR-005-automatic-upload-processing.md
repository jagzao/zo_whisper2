# US-ZMI-DKR-005 - Upload approval and pending processing queue

## Status
`SPEC`

## Owner-approved scope

Uploads to the dashboard must be stored in the configured `DATA_ROOT` staging
area, then ask once per completed batch whether to add them to `RUN Full`.
Approval promotes them into the pipeline input folders and starts or queues one
full run. Declined uploads remain staged and are not processed after restart
until approved. Approved pending work resumes after an application restart.
The manual `Process pending` action remains available.
Both file transfer checkpoints and processing jobs must survive restarts. A
screen-suspended browser resumes by reconciling its saved upload ID with the
server's durable byte offset. The host runs at most one heavy pipeline job;
additional processing requests wait in a SQLite-backed FIFO queue. Compose caps
CPU at two cores by default, configurable with `ZMI_CPUS`. Queue state
changes are recorded as durable events. Failed jobs retry at most three times;
jobs interrupted by a restart are recovered within the same retry limit.

Project selection must continue through filename-prefix routing and configured
project folders. The active Docker data volume is authoritative; do not use the
source checkout as a media directory.

Processed videos are also project knowledge sources. Whisper must generate a
detailed, transcript-grounded tutorial package (human manual plus AI chunks)
for project videos, including P&G videos even when their filename lacks the
`tutorial` marker. The package must be embedded and ingested into the matching
Zavi client project (for example, P&G), with document/chunk provenance and
project isolation. Ingestion and embedding must be idempotent and retryable;
temporary Zavi/provider outages must leave durable pending work. Whisper must
not store Zavi's Supabase service-role key. Imported transcript-derived chunks
remain unverified in Zavi until human review.

## Acceptance criteria

1. Valid uploads stay in resumable staging until the owner approves the batch;
   declined uploads never enter a pipeline scan.
2. Batch approval promotes only that batch's upload IDs and starts `RUN Full`,
   or queues one follow-up full run if processing is already active. Other
   declined batches stay staged.
3. Approved unfinished media resumes at dashboard startup; unapproved staging
   files remain untouched.
4. `/api/files` includes promoted queued files using opaque
   `MediaRoot.VIDEO_COMPRESS` identifiers.
5. Compression destination honors the matched project's `videos_subfolder`.
6. The dashboard accepts multiple selected/dropped files and uploads at most two
   concurrently, with independent progress and error status per file.
7. The manual `Process pending` button starts or queues full processing and skips
   work already recorded as completed.
8. Upload offsets advance only after chunk data is flushed to disk; after a crash,
   the server reconciles file length with the last committed offset.
9. Jobs and lifecycle events are committed transactionally in SQLite; a job
   interrupted while running returns to the queue on application startup.
10. Only one pipeline worker runs at a time; queue status and recent events are
    visible through `/api/status` and `/api/events`.
11. Full, compress, and transcribe requests all enter the same queue; each job
    gets up to three total attempts before it is marked failed.
12. Edit stays available for files without a transcription to assign or clear a
    manual project override. Manual assignment controls compression routing.
13. Transcript edits work for media in `Video_compress`, `Videos`, and `audio`.
14. The container CPU limit defaults to two cores and is configurable.
15. Every processed project video produces a detailed tutorial from its
    transcript and timestamp-aligned keyframes; steps distinguish observed
    instructions from low-confidence gaps and never invent actions.
16. The tutorial's AI package is queued for Zavi ingestion under the exact
    configured Zavi project ID, embedded using Zavi's configured provider, and
    remains retryable across restarts without duplicate documents/chunks.
17. Zavi knowledge records retain source video, transcript, timestamps, and
    tutorial provenance; imported evidence starts `unverified` and is isolated
    to its project in client mode.
18. Zavi integration reports pending/synced/error status in Whisper, without
    blocking local transcription or tutorial generation when Zavi is offline.

## Non-goals

- No cloud processing or external LLM calls.
- No deletion of the original media during data migration.
- No automatic reprocessing of files already marked complete.
- No automatic Teams VTT pairing or file rename based only on duration/date;
  verify transcript content before changing a media title.
- No insertion into Zavi interview/candidate facts; video knowledge belongs to
  the matching client project and requires Zavi's authenticated ingestion path.
