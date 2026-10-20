# DELTA-ZMI-DOCS-V2-011 — Video table date column

## Status
FROZEN_FOR_IMPLEMENTATION

## Review base
Current branch head:
`654e9b6269282895f9cb7f3d9738bb0cc4f18200`

## Goal
Add a sortable Date column to the dashboard media table without changing Documentation V2 semantics.

## Product decision
For current filesystem-backed media rows, "Date" means the media file's filesystem modification timestamp.

Reason:
- it exists for every current video/audio row;
- it requires no expensive ffprobe metadata read per table render;
- it is deterministic and does not confuse transcription modification time with media date.

Expose the raw media timestamp as ISO-8601 from the API.
Do not derive date from filename.
Do not use transcription modified time.

Future Live Capture sessions will have their own createdAt/startedAt semantics; that is separate.

## API
In `GET /api/files`, each media item must include:
- `date`: timezone-aware/local ISO string derived from `path.stat().st_mtime`
- optionally `date_epoch`: numeric epoch seconds if useful for deterministic sorting

Do not expose absolute paths.

## UI
Add a sortable column immediately before Actions:
- header label: `Date`
- sort key: `date`

Placing it immediately before Actions preserves the current numeric positions of Name..Transcription and avoids breaking existing E2E selectors that rely on Status being column 6.

Render compact local date/time:
- if valid date: localized date + time
- if absent/invalid: `-`

Sorting must use raw timestamp/epoch, not formatted display text.

## Tests
Add/adjust targeted tests:
1. /api/files includes date for synthetic media.
2. date is valid ISO and corresponds to media file mtime within tolerance.
3. dashboard contains sortable Date header.
4. sortFiles('date') compares timestamps numerically.
5. rendered row contains a non-empty Date cell for synthetic files.
6. existing Status column remains column 6.
7. existing E2E selectors do not regress.

## Execution
Implement this UI delta together with the currently active host-E2E remediation cycle.

Run targeted dashboard/API tests and then retry host E2E.

Do not:
- create worktree;
- process real media;
- resume Live Capture;
- merge/deploy.
