# Compliance legacy Session 2 sidecar validation

- Identity: HIGH; source duration 3625.451s; sidecar duration 3625.451s.
- One candidate: 771 segments, 8347 words, 98.71% media reach; segment and word order monotonic; invalid segment timestamps 0; zero-duration word timestamps 135.
- Existing VAD: 90.8% speech coverage; 294.542s uncovered; 3 major gaps. State: `NEEDS_TARGETED_RECOVERY`; no canonical edits or ASR.
- Next: classify uncovered VAD intervals, merge micro-gaps, and target only confirmed meaningful speech while preserving the source sidecar.

Machine evidence: `pg_compliance_legacy_s2_identity_timestamp_validation.json`.
