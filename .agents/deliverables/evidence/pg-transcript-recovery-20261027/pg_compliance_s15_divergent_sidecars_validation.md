# Compliance Session 15 divergent sidecars

- Identity: HIGH; both sidecars match the same 2,616.192s source and have exact metadata duration.
- Candidate A: 1,077 segments, 4,859 words, 99.10% media reach, monotonic timestamps, no invalid timestamps. Existing VAD audit is 82.83% speech coverage with 391.638s uncovered.
- Candidate B: 647 segments, 4,939 words, 99.10% media reach, monotonic timestamps, no invalid timestamps. No candidate-B VAD audit is established.
- Token sets: 808 shared; 24 A-only; 18 B-only; Jaccard 0.9506.
- Bounded timestamp comparison: B contains plausible speech in several A VAD gaps (including 2,222.22?2,225.94s and 2,232.36?2,235.08s); A and B share closing text around 2,380.47?2,381.55s. This is evidence of candidate divergence, not proof either candidate is complete.
- Decision: `NEEDS_REVIEW`; no canonical candidate selected; canonical transcript unchanged; no ASR started.
- Next: validate source/VAD coverage independently for both candidates after the queued pg-1 VAD audit can safely run; reconcile before promotion.
- Canonical selection: none. No canonical candidate selected: candidate A has an existing partial VAD audit and candidate B has no independent speech-coverage validation; the divergent text cannot be resolved by token overlap alone.

Machine evidence: `pg_compliance_s15_divergent_sidecars_validation.json`.
