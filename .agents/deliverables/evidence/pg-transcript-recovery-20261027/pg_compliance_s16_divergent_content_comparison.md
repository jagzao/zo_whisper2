# Compliance Session 16 candidate comparison

- Linear token sets: 568 shared; A-only 23; B-only 34; Jaccard 0.9088.
- Existing VAD major gap 911.08?914.65s is absent from candidate A, while candidate B has a segment spanning 911.06?919.18s with short acknowledgements. Candidate B plausibly adds speech there.
- This supports divergence and a candidate-specific advantage for the gap; it does not prove B coverage or transcript accuracy. Retain both; no canonical promotion.
- Manifest content hashes (A, B): 5b9ec2ed73a4685e8b1c6e722c6d8cdde93b7a817226c9489b3ce626458af391, c56131a7d1c2362edf104174371dbf01281f0d49d269f1ab71d9fe883e880d47; both file hashes match the provenance manifest.
- Canonical selection: none. No canonical candidate selected: both candidates stop at ~1,483s/42.94% of the 3,453.376s source; candidate B fills one sampled A VAD gap, but B coverage and remaining source speech are unvalidated.

Machine evidence: `pg_compliance_s16_divergent_content_comparison.json`.
