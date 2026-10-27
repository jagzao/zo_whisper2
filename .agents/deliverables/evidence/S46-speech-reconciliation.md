# S46 speech reconciliation

- Recovery windows: 83/83
- Effective speech coverage: 98.85%
- Original manual-review residual: 22.780 s across 19 contextual intervals, including the 4.920 s prior recovery window.
- Semantically classified residual: 19 intervals / 22.780 s.
- Already represented: 13.338 s.
- Unintelligible: 2.944 s.
- Courtesy-only missing speech: 0.768 s; non-material.
- Low-confidence audio requiring source-audio review: 5.730 s (gap-062 0.810 s; prior-recovery-3443 4.920 s).
- Speech gate: NEEDS_REVIEW; remaining low-confidence audio could contain meaningful content and cannot be cleared from text-only evidence.
- Recovered fragment gap-073: DUPLICATE_EXISTING_CONTENT; excluded.
- Recovered fragment gap-148: NEW_VALID_CONTENT; inserted into a provenance-linked reconciled transcript version. Original canonical transcript was preserved.
- No audio evidence was available for the low-confidence spans; none was presumed noise or non-speech.

## Residual interval classifications

- `gap-001` 156.630?158.540 s (1.910s): **ALREADY_REPRESENTED** ? Neighbor transcript explicitly says the group will wait for Joni.
- `gap-014` 383.490?385.168 s (1.678s): **UNINTELLIGIBLE** ? Recognizers disagree on a garbled phrase; adjacent transcript captures the screen closing.
- `gap-059` 1041.200?1041.968 s (0.768s): **MEANINGFUL_MISSING_SPEECH** ? Courtesy acknowledgement only; no operational or technical knowledge.
- `gap-062` 1077.870?1078.680 s (0.810s): **LOW_CONFIDENCE** ? Large-v3 candidate ?source code is GitHub? conflicts with small-ASR ?data?; requires source-audio review.
- `gap-069` 1322.180?1322.840 s (0.660s): **ALREADY_REPRESENTED** ? Canonical transcript immediately contains the same question about loading/adding information and an admin portal.
- `gap-088` 1804.784?1805.430 s (0.646s): **UNINTELLIGIBLE** ? Short unclear phrase; no technical proposition recoverable.
- `gap-098` 1963.216?1963.720 s (0.504s): **ALREADY_REPRESENTED** ? Canonical transcript says ?Just kind of let it run.?
- `gap-102` 2085.060?2087.290 s (2.230s): **ALREADY_REPRESENTED** ? Canonical transcript asks what NTID means and defines it as the Windows username.
- `gap-117` 2335.520?2336.300 s (0.780s): **ALREADY_REPRESENTED** ? Canonical transcript says they manage a couple of applications.
- `gap-128` 2504.496?2505.310 s (0.814s): **ALREADY_REPRESENTED** ? SQL is stated in the neighboring canonical segment.
- `gap-144` 2760.960?2761.456 s (0.496s): **ALREADY_REPRESENTED** ? Transition into the next question; no separate technical proposition.
- `gap-163` 3044.840?3045.440 s (0.600s): **ALREADY_REPRESENTED** ? Neighboring canonical text already mentions Java and the possibility of a job.
- `gap-202` 3411.440?3412.060 s (0.620s): **ALREADY_REPRESENTED** ? Neighboring canonical segments repeat that the meeting is wrapping up.
- `gap-206` 3441.500?3442.580 s (1.080s): **ALREADY_REPRESENTED** ? Canonical text includes ?I think it was this one? and the address to Julie.
- `gap-209` 3487.750?3489.776 s (2.026s): **ALREADY_REPRESENTED** ? Canonical text already includes asking the app owner for a tour inside the interface.
- `gap-212` 3519.310?3519.930 s (0.620s): **UNINTELLIGIBLE** ? ASR phrase conflicts with adjacent upload-to-SharePoint context and lacks a second clear reading.
- `gap-223` 3590.530?3591.620 s (1.090s): **ALREADY_REPRESENTED** ? Canonical transcript says ?Anything else from Decapmini??
- `gap-224` 3593.280?3593.808 s (0.528s): **ALREADY_REPRESENTED** ? Same closing prompt as gap-223; transcript contains it.
- `prior-recovery-3443` 3443.680?3448.600 s (4.920s): **LOW_CONFIDENCE** ? Two ASR passes disagree on a 4.92s reply; its latter clause duplicates neighboring ?do not worry / not in use? text.

## Category totals

- ALREADY_REPRESENTED: 13 intervals / 13.338s
- UNINTELLIGIBLE: 3 intervals / 2.944s
- MEANINGFUL_MISSING_SPEECH: 1 intervals / 0.768s
- LOW_CONFIDENCE: 2 intervals / 5.730s
