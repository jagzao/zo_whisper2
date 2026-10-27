# App Support S4 sidecar validation

- Identity: HIGH; source duration 4540.307s.
- Candidate: 650 segments, 8310 words, 78.85% media reach; segment and word order monotonic; invalid segment timestamps 0; zero-duration word timestamps 153.
- Existing VAD: 93.58% speech coverage; 207.916s uncovered; 6 major gaps. State: `NEEDS_TARGETED_RECOVERY`; no transcript edits or ASR.
- Next: classify uncovered VAD intervals, merge micro-gaps, and target confirmed meaningful speech only; preserve original sidecar.

Machine evidence: `pg_app_support_s4_identity_timestamp_validation.json`.
