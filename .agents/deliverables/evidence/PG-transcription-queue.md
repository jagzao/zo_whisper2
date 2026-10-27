# P&G transcription queue

Persistent one-source-at-a-time queue. Existing sidecar candidates are ahead of missing transcripts; recovery outputs remain candidates until source comparison and coverage validation.

- NEEDS_FULL_TRANSCRIPTION: 7
- NEEDS_REVIEW: 2
- NEEDS_TARGETED_RECOVERY: 11

## Work items

- `pg_AMS KAP – App Support – Session-20261008_150120UTC-Meeting Recording.mp4` - NEEDS_REVIEW: run one-source VAD/speech-coverage, internal-gap, and final-gap audit when resource headroom is safe; do not retranscribe. Progress: identity HIGH; 1,140 segments/4,431 words valid; reach 99.82%; 110 timestamp gaps >1.5s await VAD; WAITING_RESOURCES.
- `pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording.mp4` - NEEDS_TARGETED_RECOVERY: reconcile existing VAD gaps in 309.64s uncovered speech, then run contextual recovery only for confirmed meaningful gaps; preserve canonical sidecar. Progress: identity HIGH; 714 segments/7,788 words valid; reach 91.22%; speech coverage 90.56%; 309.64s uncovered.
- `pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording.mp4` - NEEDS_TARGETED_RECOVERY: audit VAD/speech in the 5,446.806s tail; then target recovery for confirmed meaningful gaps, preserving the original sidecar. Progress: identity HIGH; 755 segments/4,101 words valid; reach 25.89%; speech coverage 85.17%; 248.728s uncovered; 5,446.806s tail unclassified.
- `pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording.mp4` - NEEDS_TARGETED_RECOVERY: reconcile 190.69s of uncovered speech and five major VAD gaps; run contextual recovery only for confirmed meaningful intervals; preserve original sidecar. Progress: identity HIGH; 544 segments/4,091 words valid; reach 99.68%; speech coverage 89.67%; 190.69s uncovered; five major gaps.
- `pg_AMS KAP ? Compliance ? Session 15-20260916_123040UTC-Meeting Recording.mp4` - NEEDS_TARGETED_RECOVERY: keep both sidecars unpromoted; candidate B adds plausible speech in several candidate-A VAD gaps, but candidate B coverage is unvalidated. Identity HIGH; 1,077/647 segments; 99.10% media reach each; candidate A coverage 82.83%, candidate B not validated; 808 shared tokens; canonical unchanged.
- `pg_AMS KAP ? Compliance ? Session 16-20260918_122959UTC-Meeting Recording.mp4` - NEEDS_TARGETED_RECOVERY: two divergent candidates, each reaches 42.94%; candidate A VAD speech coverage 82.70%, 218.278s uncovered; candidate B not independently assessed; preserve both and reconcile before targeted recovery. Segments monotonic; zero-duration word timing flags 52/45.
- `pg_AMS KAP ? Compliance ? Session 17-20260921_122939UTC-Meeting Recording.mp4` - NEEDS_REVIEW: two divergent sidecars reach 49.58%; candidate A VAD shows 91.71% coverage/65.178s uncovered but does not classify ~928.386s untranscribed tail; candidate B coverage unvalidated. Both retained; no canonical promotion.
- `pg_AMS KAP ? Compliance ? Session 7-20260824_123002UTC-Meeting Recording.mp4` - NEEDS_TARGETED_RECOVERY: identity HIGH; 945 segments/6,680 words valid; reach 99.84%; VAD speech 86.40%, 387.212s uncovered, four major gaps; contextual recovery only after gap classification.
- `pg_AMS_KAP_-_Compliance_-_Session_2.mp4` - NEEDS_TARGETED_RECOVERY: identity HIGH; 771 segments/8,347 words valid; reach 98.71%; VAD speech 90.80%, 294.542s uncovered, three major gaps; contextual recovery only after gap classification.
- `pg_Ams_kap_app_support_s10.mp4` - NEEDS_TARGETED_RECOVERY: 3 VAD gaps and 588.361s tail reviewed; tail has 0.992s VAD speech without supported ASR. Continue internal VAD-gap audit; aggregate uncovered remains 547.508s..
- `pg_Ams_kap_compliance_s4.mp4` - NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery.
- `pg_Shadow_221026.mp4` - NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery.
- `pg_Ams_kap_app_support_s46.mp4` - NEEDS_REVIEW: review source audio for gap-062 (0.810s) and prior-recovery-3443 (4.920s); 83/83 contextual windows complete.
- `pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
- `pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
- `pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
- `pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
- `pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
- `pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
- `pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording.mp4` - NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated.
