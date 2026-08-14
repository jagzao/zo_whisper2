# 0002 — Centralized filesystem boundary (SafePathResolver)

## Status
Accepted

## Context
The dashboard's endpoints previously validated paths inconsistently: two
endpoints (`GET`/`POST /api/transcription`) had **no** guard at all
(arbitrary file read/write from the browser), and four others used
`str(path.resolve()).startswith(str(root.resolve()))`, which is bypassable
by a sibling directory sharing the root's name as a prefix (`C:\whisper`
matches `C:\whisper_evil`) and doesn't normalize case on Windows' NTFS.

## Decision
Introduce `SafePathResolver` (`src/transcript_pipeline/security/path_resolver.py`)
as the single component responsible for validating that a path is inside
an allowed root:
- Explicit `MediaRoot` enum (`AUDIO`, `VIDEOS`, `VIDEO_COMPRESS`,
  `TRANSCRIPTIONS`) — no endpoint invents its own root.
- Containment check via `os.path.normcase` + prefix-with-separator
  comparison, not a bare `Path.is_relative_to()` (which doesn't case-fold
  on Windows) or raw string `startswith`.
- Rejects absolute, rooted, and drive-relative inputs where a relative id
  is expected (`resolve()`).
- Domain exceptions (`PathTraversalError`, `PathNotFoundError`) caught by a
  single Flask `errorhandler` so no endpoint can accidentally leak the
  resolved path in an error message.

Every endpoint that touches a file goes through `SafePathResolver` via the
`_to_media_id()`/`_from_media_id()` helpers in `dashboard/app.py` — the
frontend never sends or receives a raw absolute path; every id is opaque
(`"<root>:<relative>"`) and only resolved to a real filesystem `Path`
server-side. There is no code path left that builds a trusted `Path` from
user input without going through the resolver.

## Consequences
- Fixing the boundary in one place also fixed `scripts/security.py`'s own
  gate: it used to grep `app.py` for three literal strings
  (`"target.resolve()"`, `"startswith(str(root_resolved))"`), which is why
  it never caught the two ungated endpoints. It now runs the real
  `tests/security/` regression suite instead.
- The original design note below is kept for history — the migration it
  describes as a follow-up has since landed: the frontend never receives an
  absolute path (`/api/files` returns a repo-relative string, `/api/folders`
  returns only `{name, count}`, and every mutating/reading endpoint accepts
  only opaque `media_id`s). ~~The `?path=<absolute>` contract with the
  frontend is unchanged for now — the resolver validates the absolute path
  against allowed roots rather than requiring an opaque id. Migrating to
  `media_id`/`transcription_id` (removing absolute-path exposure entirely)
  is a follow-up, not required to close the vulnerability, and is lower
  priority than closing the arbitrary read/write itself.~~
