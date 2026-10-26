# S46 speech gap audit

Source: `pg_Ams_kap_app_support_s46.mp4`

## Metrics

- video_duration_seconds: 3618.944
- vad_speech_seconds: 2042.496
- canonical_transcribed_speech_seconds: 1761.414
- previous_dual_asr_candidate_seconds: 4.92
- new_dual_asr_candidate_seconds: 8.36
- uncovered_speech_seconds_after_candidates: 267.802
- meaningful_uncovered_speech_seconds: 202.774
- effective_speech_coverage_percent: 89.69
- raw_speech_coverage_percent_original: 86.24
- raw_speech_coverage_percent_with_recovery: 86.89
- silence_boundary_seconds_excluded_from_effective_denominator: 63.838
- transcript_state: NEEDS_REVIEW
- speech_quality_gate: FAIL

## Interval classifications

- ACTUAL_MISSING_SPEECH: 8 intervals / 8.360s
- FALSE_POSITIVE_VAD_CANDIDATE: 1 intervals / 1.190s
- UNCERTAIN: 222 intervals / 202.774s

All 231 formerly unresolved intervals were individually run through local small-model ASR. 10 plausible candidates were checked with a second local model; 8 were semantically corroborated. Those spans are classified as actual missing speech for coverage accounting but remain supplemental evidence, not canonical transcript text. The remaining intervals require review; no transcript was overwritten.
