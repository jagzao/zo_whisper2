# Compliance Session 17 sidecar validation

- Source duration: 1,841.2165s; both sidecars match source basename and have monotonic, valid segment timestamps. Identity: HIGH.
- Two divergent candidates have 621/627 segments and 1,561/1,571 words. Both sidecars report 913.152s and end at ~912.8s (49.58% media reach); each has a small number of zero-duration word timestamps (6/2).
- Existing candidate-A VAD audit: 91.71% speech coverage over measured intervals, 65.178s uncovered, two major gaps. It does not account for the untranscribed half-source tail. Candidate B coverage is not independently validated.
- State: `NEEDS_REVIEW`; both candidates retained, no canonical promotion or transcript edits. Classify the remaining source tail and compare candidate B before selecting or targeted recovery.

Machine evidence: `pg_compliance_s17_identity_timestamp_validation.json`.
