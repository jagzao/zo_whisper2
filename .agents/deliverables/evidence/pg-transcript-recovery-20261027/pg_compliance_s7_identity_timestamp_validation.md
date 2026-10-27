# Compliance Session 7 sidecar validation

- Identity: HIGH; source duration 3191.375s; sidecar duration 3191.296s.
- Candidate: 945 segments, 6680 words, 99.84% media reach; segment and word order monotonic; invalid segment timestamps 0; zero-duration word timestamps 66.
- Existing VAD: 86.4% speech coverage; 387.212s uncovered; 4 major gaps. State: `NEEDS_TARGETED_RECOVERY`; no transcript edits or ASR.
- Next: classify uncovered VAD intervals, merge micro-gaps, and target confirmed meaningful speech only; preserve original sidecar.

Machine evidence: `pg_compliance_s7_identity_timestamp_validation.json`.
