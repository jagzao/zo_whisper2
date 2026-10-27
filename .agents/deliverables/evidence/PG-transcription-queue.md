# P&G transcription queue

One low-priority local large-v3 worker; a media lock prevents concurrent processing.

- NEEDS_FULL_TRANSCRIPTION: 8
- NEEDS_TARGETED_RECOVERY: 11
- PROCESSING: 1

## Work items

- `pg_AMS KAP – App Support – Session-20261008_150120UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_AMS KAP – Compliance – Session 15-20260916_123040UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: compare divergent sidecars against source speech coverage before choosing canonical
- `pg_AMS KAP – Compliance – Session 16-20260918_122959UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: compare divergent sidecars against source speech coverage before choosing canonical
- `pg_AMS KAP – Compliance – Session 17-20260921_122939UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: compare divergent sidecars against source speech coverage before choosing canonical
- `pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording.mp4` ? NEEDS_FULL_TRANSCRIPTION: full large-v3 transcription after source is revalidated
- `pg_AMS_KAP_-_Compliance_-_Session_2.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_Ams_kap_app_support_s10.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_Ams_kap_app_support_s46.mp4` ? PROCESSING: resume large-v3 contextual recovery; 23/79 windows already checkpointed
- `pg_Ams_kap_compliance_s4.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
- `pg_Shadow_221026.mp4` ? NEEDS_TARGETED_RECOVERY: audit uncovered VAD intervals, then contextual large-v3 recovery
