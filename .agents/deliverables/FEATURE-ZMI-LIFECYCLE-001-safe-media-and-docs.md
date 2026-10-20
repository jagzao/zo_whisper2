# FEATURE-ZMI-LIFECYCLE-001 — Safe media retention and documentation

## Intent

Complete compression, temporary cleanup and documentation regeneration as one traceable user workflow.

## Behavior

- The compressor only removes a source after staged and published optimized output passes media integrity/duration/stream/size checks and provenance is persisted.
- A failure retains the source and reports a deterministic reason/state.
- Live Capture keeps ACKed fragments until the final is validated and all mapped processing completes; then it removes only session-owned temporary pieces.
- Final media, provenance/manifest and generated docs remain available.
- Regenerate Documentation rebuilds from persisted evidence, preserves versions, and does not silently trigger reprocessing.
- Ready user media has a visible deterministic delete action; prohibited states show disabled action and reason. Internal chunks remain hidden.
- Mobile crop uses Pointer Events and visible rectangle geometry. Desktop and LAN share one backend/data root.

## Non-goals

- General-purpose media garbage collection or age-only deletion.
- Deleting user originals that are not tied to a validated optimized output.
- Reprocessing or retranscribing as part of documentation regeneration.
- Second Brain publishing or unrelated knowledge-publisher changes.
