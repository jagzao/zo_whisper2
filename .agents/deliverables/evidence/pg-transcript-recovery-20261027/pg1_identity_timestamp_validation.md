# P&G pg-1 identity and timestamp checkpoint - 2026-10-27

- Source: `Videos/py_pg/pg_AMS KAP – App Support – Session-20261008_150120UTC-Meeting Recording.mp4`
- Identity: HIGH; embedded audio provenance basename matches source; metadata and sidecar duration 2760.448s; ffprobe duration 2760.448500s.
- Sidecar SHA-256: `c9924e2af81a8c6488131c5f4674e7d4c7ce269d8524d5832caedc4a304e8215`
- Segments: 1,140; words: 4,431; invalid segment/word timestamps: 0; segment/word start ordering monotonic.
- Media reach: 99.82%; last word 2755.430s; trailing interval about 5.019s.
- Segment-envelope interval union: 76.44%; word interval union: 1783.540s (64.61%).
- Candidate word-timestamp gaps over 1.5s: 110. These are timestamp gaps, not established speech gaps. Largest: 110.59s (159.52-270.11) and 88.74s (16.58-105.32); both lie within single segments and need VAD/context review. Full top-20 list is in the JSON.
- State: NEEDS_REVIEW. Speech coverage, meaningful internal gaps, and final-gap class remain unassessed. No retranscription and no canonical sidecar modification.
- Resource guard: WAITING_RESOURCES for one-source VAD. Free RAM was 4.0/29.6 GB; model-runtime processes were present; no ASR/FFmpeg process was observed; CPU load could not be read.
- Next action: run pg-1 VAD/speech-coverage audit alone when resource headroom is safe.
