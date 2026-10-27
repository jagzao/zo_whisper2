# App Support S10 sidecar validation

- Identity: HIGH; source duration 4,489.661s.
- Candidate: 1,188 segments, 5,469 words; 86.90% media reach; segment/word ordering monotonic; no invalid segment timestamps.
- Existing VAD: 79.34% speech coverage; 547.508s uncovered; three major internal gaps. Prior tail review classified the 588.361s tail with 0.992s VAD speech lacking supported ASR. State: `NEEDS_TARGETED_RECOVERY`; canonical sidecar unchanged, no ASR.
- Next: continue semantic review of aggregate uncovered intervals, target only meaningful gaps, preserve original sidecar.

Machine evidence: `pg_app_support_s10_identity_timestamp_validation.json`.
