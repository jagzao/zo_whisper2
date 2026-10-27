# P&G logical media/transcript map

One row per logical video. Transcript identity uses embedded `audio_file` provenance, corroborated by processing DB basename and size where present. Similar names without corroboration remain unmatched.

- Logical videos: 20
- Physical segment sidecars discovered: 92 (all projects)
- Physical sidecars matched to these 20 sources: 15
- Duplicate sidecar copies: 3 (0 identical; 3 divergent)
- Transcript states: {'MISSING': 8, 'PARTIAL': 8, 'NEEDS_REVIEW': 4}
- Unassessed logical videos: 0

## Logical sources

- `pg_AMS KAP – App Support – Session-20261008_150120UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=91.22%; speech=90.56%; last=3571.34; file=CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=25.89%; speech=85.17%; last=1903.21; file=CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.68%; speech=89.67%; last=2130.06; file=CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 15-20260916_123040UTC-Meeting Recording.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=2; media=99.1%; speech=82.83%; last=2592.64; file=none
- `pg_AMS KAP – Compliance – Session 16-20260918_122959UTC-Meeting Recording.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=2; media=42.94%; speech=82.7%; last=1482.86; file=none
- `pg_AMS KAP – Compliance – Session 17-20260921_122939UTC-Meeting Recording.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=2; media=49.58%; speech=91.71%; last=912.83; file=none
- `pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.84%; speech=86.4%; last=3186.35; file=CarpetaTranscripciones/py_pg/pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording_segments.json
- `pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording.mp4` — MISSING; match=MANUAL_REVIEW/NONE; sidecars=0; media=None%; speech=None%; last=None; file=none
- `pg_AMS_KAP_-_Compliance_-_Session_2.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=98.71%; speech=90.8%; last=3578.66; file=CarpetaTranscripciones/py_pg/pg_AMS_KAP_-_Compliance_-_Session_2_segments.json
- `pg_Ams_kap_app_support_s10.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=86.9%; speech=79.34%; last=3901.3; file=CarpetaTranscripciones/py_pg/pg_Ams_kap_app_support_s10_segments.json
- `pg_Ams_kap_app_support_s46.mp4` — NEEDS_REVIEW; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.83%; speech=98.85%; low-confidence review=5.73s; last=3612.76; file=CarpetaTranscripciones/py_pg/pg_Ams_kap_app_support_s46_segments.json
- `pg_Ams_kap_compliance_s4.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=78.85%; speech=93.58%; last=3580.11; file=CarpetaTranscripciones/py_pg/pg_Ams_kap_compliance_s4_segments.json
- `pg_Shadow_221026.mp4` — PARTIAL; match=PROCESSING_DB_PROVENANCE/HIGH; sidecars=1; media=99.85%; speech=80.85%; last=3330.63; file=CarpetaTranscripciones/py_pg/pg_Shadow_221026_segments.json

All unmatched sidecar paths are retained in JSON for review. Duplicate files were not deleted. Video SHA-256 is omitted because these source files total about 38 GB; no video was reread solely to hash it.
