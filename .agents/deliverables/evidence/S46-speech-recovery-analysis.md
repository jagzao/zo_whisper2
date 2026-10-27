# S46 contextual speech recovery analysis

- Windows complete: 83/83
- Recovered candidate speech: 2.268 seconds
- Duplicate/neighbor-covered text: 74.792 seconds
- False-positive/low-energy intervals: 0.0 seconds
- Initial algorithmic residual: 22.78 seconds across 19 intervals; subsequent semantic review dispositioned each interval as shown in `S46-speech-reconciliation.md`.
- Canonical transcript changed: no

## Interval classification

- ALREADY_COVERED_BY_NEIGHBOR: 74 intervals / 74.792s
- NEEDS_REVIEW: 19 intervals / 22.780s
- RECOVERED_SPEECH_CANDIDATE: 2 intervals / 2.268s

## Original uncertain 222 intervals

- ALREADY_COVERED_BY_NEIGHBOR: 73 intervals / 73.612s
- NEEDS_REVIEW: 18 intervals / 17.860s
- RECOVERED_SPEECH_CANDIDATE: 2 intervals / 2.268s

Every recovered window is compared to the neighboring canonical transcript and the earlier local ASR. Novel text remains a recovery candidate until coverage is recalculated; duplicate wording is not inserted twice.


## Final semantic review

- Already represented: 13.338 seconds.
- Unintelligible: 2.944 seconds.
- Courtesy-only speech: 0.768 seconds, non-material.
- Low-confidence and still requiring source-audio review: 5.730 seconds.
- Speech gate remains NEEDS_REVIEW pending that audio check.
