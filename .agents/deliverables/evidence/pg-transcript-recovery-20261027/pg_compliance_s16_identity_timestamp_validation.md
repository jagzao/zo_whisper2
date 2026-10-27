# Compliance Session 16 sidecar validation

- Source duration: 3,453.376s; source basename and embedded audio references match. Identity: HIGH.
- Two divergent candidates: 518 segments/2,998 words and 329 segments/2,980 words. Both end near 1,482.9s (42.94% source media reach); sidecar duration is 1,483.072s. Segment and word order are monotonic; segment timestamps are valid. Each contains zero-duration word timestamps (52 and 45 respectively), an ASR word-timing defect, not segment boundary corruption.
- Existing VAD audit applies to candidate A: 82.70% speech coverage; 218.278s uncovered; one major 3.570s interval. Candidate B coverage not independently validated.
- State: `NEEDS_TARGETED_RECOVERY`; both candidates retained; no canonical selection or transcript change. Reconcile uncovered speech and compare candidate B before contextual recovery. No full-source retranscription.

Machine evidence: `pg_compliance_s16_identity_timestamp_validation.json`.
