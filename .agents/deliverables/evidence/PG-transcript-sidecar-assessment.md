# P&G transcript identity and readiness assessment

20 logical readable videos, reconciled by embedded `audio_file`, normalized aliases, and processing database path/size. Similar filenames alone were not used as high-confidence identity.

- Logical/readable videos: 20/20
- Matched physical sidecars: 15
- Distinct logical transcript sources: 12
- Duplicate sidecar copies: 3 (0 identical; 3 divergent)
- States: {'MISSING': 8, 'PARTIAL': 8, 'NEEDS_REVIEW': 4}
- Unassessed logical transcripts: 0

- Previous nine exact-name misses reclassified: 8 actually missing; 1 recovered by processing-DB provenance (Session 7).
Divergent copies for Sessions 15–17 have the same source-media identity but different segment content; no canonical sidecar was chosen pending coverage comparison. All copies remain preserved.

## Logical sources

- `pg_AMS KAP – App Support – Session-20261008_150120UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=91.22%; speech=90.56%; canonical=CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=25.89%; speech=85.17%; canonical=CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.68%; speech=89.67%; canonical=CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 15-20260916_123040UTC-Meeting Recording.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=2; media=99.1%; speech=82.83%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 16-20260918_122959UTC-Meeting Recording.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=2; media=42.94%; speech=82.7%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 17-20260921_122939UTC-Meeting Recording.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=2; media=49.58%; speech=91.71%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.84%; speech=86.4%; canonical=CarpetaTranscripciones/py_pg/pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; canonical=pending review
- `pg_AMS_KAP_-_Compliance_-_Session_2.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=98.71%; speech=90.8%; canonical=CarpetaTranscripciones/py_pg/pg_AMS_KAP_-_Compliance_-_Session_2_segments.json
- `pg_Ams_kap_app_support_s10.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=86.9%; speech=79.34%; canonical=CarpetaTranscripciones/py_pg/pg_Ams_kap_app_support_s10_segments.json
- `pg_Ams_kap_app_support_s46.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.83%; speech=98.85%; low-confidence audio review=5.730s; canonical=CarpetaTranscripciones/py_pg/pg_Ams_kap_app_support_s46_segments.json
- `pg_Ams_kap_compliance_s4.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=78.85%; speech=93.58%; canonical=CarpetaTranscripciones/py_pg/pg_Ams_kap_compliance_s4_segments.json
- `pg_Shadow_221026.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.85%; speech=80.85%; canonical=CarpetaTranscripciones/py_pg/pg_Shadow_221026_segments.json

Missing transcripts are queued for full large-v3 transcription after source revalidation. Partial transcripts and divergent copies are queued for targeted recovery/assessment. No duplicates were deleted; no full documentation corpus was generated.
