# S46 speech reconciliation

The 222 intervals originally marked uncertain (202.774 s) were matched individually to adjacent transcript text, VAD regions, local ASR, audio energy and transcript overlap. Nine other intervals are supplemental candidates and are reported separately.

## Original uncertain intervals
- Raw: 222 intervals / 202.774s
- Neighbor or word-boundary represented: 109.034s (129 intervals)
- Still NEEDS_REVIEW: 93.740s / 93 intervals
- Conservative effective speech coverage: 91.63%
- Optimistic ceiling if all unresolved spans are explained: 96.22%

## Supplemental candidates
- 9 intervals; original classes: {'ACTUAL_MISSING_SPEECH': 8, 'FALSE_POSITIVE_VAD_CANDIDATE': 1}
- Current classifications: {'WORD_BOUNDARY_FRAGMENT': 6, 'ALREADY_COVERED_BY_NEIGHBOR': 1, 'MEANINGFUL_MISSING_SPEECH': 1, 'FALSE_POSITIVE_VAD': 1}
- Meaningful missing candidate: 1.180s

- Contextual recovery windows: 23/79 large-v3 windows checkpointed; 56 remain queued. Recovered text remains separate pending neighbor deduplication.
- Canonical transcript remains unchanged until recovered text is compared with neighboring segments.
- Gate: NEEDS_REVIEW pending contextual recovery of the remaining intervals; raw VAD uncertainty is not treated as missing speech.

Classification counts for the original 222 intervals:

- ALREADY_COVERED_BY_NEIGHBOR: 3 / 2.886s
- NEEDS_REVIEW: 93 / 93.740s
- WORD_BOUNDARY_FRAGMENT: 126 / 106.148s
