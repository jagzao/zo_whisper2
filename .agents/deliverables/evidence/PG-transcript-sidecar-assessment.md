# P&G transcript source and speech-coverage assessment

Scope: 20 top-level `Videos/py_pg/*.mp4` logical sources. All passed ffprobe. Segment sidecars were matched by exact source basename throughout `CarpetaTranscripciones`, checked for audio identity, timestamp reach, and VAD speech coverage.

## Current inventory
- Readable media: 20/20
- Physical exact-name sidecar files: 14
- Distinct source videos with a sidecar: 11
- Duplicate sidecar copies: 3
- Speech quality states: {'MISSING': 9, 'PARTIAL': 10, 'NEEDS_REVIEW': 1}
- Full P&G documentation synthesis: FROZEN

## Per-source results

- `pg_AMS KAP – App Support – Session-20261008_150120UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording.mp4` — PARTIAL; media reach=91.22%; speech coverage=90.56%; VAD=3280.8s; uncovered=309.64s; major gaps=4; identity=MATCH.
- `pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording.mp4` — PARTIAL; media reach=25.89%; speech coverage=85.17%; VAD=1677.536s; uncovered=248.728s; major gaps=1; identity=MATCH.
- `pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording.mp4` — PARTIAL; media reach=99.68%; speech coverage=89.67%; VAD=1846.176s; uncovered=190.69s; major gaps=5; identity=MATCH.
- `pg_AMS KAP – Compliance – Session 15-20260916_123040UTC-Meeting Recording.mp4` — PARTIAL; media reach=99.1%; speech coverage=82.83%; VAD=2281.504s; uncovered=391.638s; major gaps=8; identity=MATCH.
- `pg_AMS KAP – Compliance – Session 16-20260918_122959UTC-Meeting Recording.mp4` — PARTIAL; media reach=42.94%; speech coverage=82.7%; VAD=1261.616s; uncovered=218.278s; major gaps=1; identity=MATCH.
- `pg_AMS KAP – Compliance – Session 17-20260921_122939UTC-Meeting Recording.mp4` — PARTIAL; media reach=49.58%; speech coverage=91.71%; VAD=785.968s; uncovered=65.178s; major gaps=2; identity=MATCH.
- `pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording.mp4` — MISSING transcript sidecar; media valid.
- `pg_AMS_KAP_-_Compliance_-_Session_2.mp4` — PARTIAL; media reach=98.71%; speech coverage=90.8%; VAD=3201.76s; uncovered=294.542s; major gaps=3; identity=MATCH.
- `pg_Ams_kap_app_support_s10.mp4` — PARTIAL; media reach=86.9%; speech coverage=79.34%; VAD=2650.048s; uncovered=547.508s; major gaps=3; identity=MATCH.
- `pg_Ams_kap_app_support_s46.mp4` — NEEDS_REVIEW; media reach=99.83%; speech coverage=89.69%; VAD=2042.496s; uncovered=202.774s; major gaps=222; identity=MATCH.
- `pg_Ams_kap_compliance_s4.mp4` — PARTIAL; media reach=78.85%; speech coverage=93.58%; VAD=3236.128s; uncovered=207.916s; major gaps=6; identity=MATCH.
- `pg_Shadow_221026.mp4` — PARTIAL; media reach=99.85%; speech coverage=80.85%; VAD=1904.032s; uncovered=364.596s; major gaps=3; identity=MATCH.

Speech coverage was measured with local Silero VAD. The 10 non-S46 matched sidecars are all PARTIAL; S46 remains NEEDS_REVIEW. Supplemental ASR candidates were not inserted into canonical transcripts. No source was retranscribed and no Session Knowledge Pack was generated in this pass.

The prior tally of 1 VALID / 3 PARTIAL / 6 MISSING / 10 UNASSESSED conflicts with this exact-path inventory. The current 20-video source set contains 11 distinct matching sidecars (14 physical files including 3 duplicates) and 9 unmatched sources; reconcile the older source-qualified identities/manifests before treating the corpus inventory as final.
