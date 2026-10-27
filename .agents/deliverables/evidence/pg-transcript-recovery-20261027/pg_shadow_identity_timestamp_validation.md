# Shadow 221026 sidecar validation

- Identity: HIGH; source duration 3335.784s.
- Candidate: 871 segments, 4006 words, 99.85% media reach; segment and word order monotonic; invalid segment timestamps 0; zero-duration word timestamps 34.
- Existing VAD: 80.85% speech coverage; 364.596s uncovered; 3 major gaps. State: `NEEDS_TARGETED_RECOVERY`; no transcript edits or ASR.
- Next: classify uncovered VAD intervals, merge micro-gaps, and target confirmed meaningful speech only; preserve original sidecar.

Machine evidence: `pg_shadow_identity_timestamp_validation.json`.
