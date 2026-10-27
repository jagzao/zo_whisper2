# P&G pg-1 identity and timestamp checkpoint ? 2026-10-27

- Source: `Videos/py_pg/pg_AMS KAP ? App Support ? Session-20261008_150120UTC-Meeting Recording.mp4`
- Identity: HIGH; embedded audio provenance basename matches source; metadata and sidecar durations match exactly at 2760.448 s; ffprobe reports 2760.448500 s.
- Sidecar SHA-256: `c9924e2af81a8c6488131c5f4674e7d4c7ce269d8524d5832caedc4a304e8215`
- Segments: 1,140; words: 4,431; invalid segment/word timestamps: 0; segment and word ordering monotonic.
- Media reach: 99.82%; final segment end 2755.430 s; trailing media interval 5.019 s.
- Segment interval union: 76.44%; largest envelope gaps are listed in the JSON. These are not classified as missing speech without VAD.
- State: NEEDS_REVIEW. Speech coverage, meaningful internal gaps, and final-gap class remain unassessed. No retranscription and no canonical sidecar modification.
- Resource guard: WAITING_RESOURCES for one-source VAD. Free RAM was 4.0/29.6 GB, a local model runtime (`model_host`, Ollama) was present, and CPU load could not be read. No ASR or FFmpeg process was observed.
- Next action: run pg-1 VAD/speech-coverage audit alone when resource headroom is safe.
