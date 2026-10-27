# P&G source preflight and serial recovery manifest

- No VAD, ASR, or audio extraction was run. `ffprobe` inspected container/stream metadata only.
- pg-1 remains `WAITING_RESOURCES`; active heavy jobs: none.
- P0 source files, sidecars, neighboring context, and window bounds: 8/8 sources and 25/25 windows verified readable/in range.
- Seven MISSING sources: all readable, identity sizes match, audio stream present, probed duration matches inventory, no existing output checkpoint.
- Available storage: 104.48 GB; missing source media total: 2.12 GB. Runner decodes directly from source and saves resumable JSON checkpoints; it creates no audio extraction batch.

## P0 serial order

1. `pg-ccb11a4619acaa92` ? 4 windows; `CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 10-20260902_122954UTC-Meeting Recording_segments.json`
   - `pgw-fcc96462ba068fb4bc7a` 981.840?986.730s (context 976.840?991.730s)
   - `pgw-ec2f50d0e500eb8104e8` 1622.990?1632.290s (context 1617.990?1637.290s)
   - `pgr-cf0a64bb32fc43e7a4ee` 1895.900?1950.740s (context 1890.900?1955.740s)
   - `pgw-bfc9f2faff8d127bf5e1` 3157.530?3167.250s (context 3152.530?3172.250s)
2. `pg-e3d73ded7776de64` ? 1 windows; `CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 13-20260909_122959UTC-Meeting Recording_segments.json`
   - `pgw-d029a307d06e5a5c0691` 1637.780?1649.580s (context 1632.780?1654.580s)
3. `pg-e37b41cb13677886` ? 2 windows; `CarpetaTranscripciones/pg_AMS KAP – Compliance – Session 14-20260911_123025UTC-Meeting Recording_segments.json`
   - `pgw-e57845dd617469b56e40` 808.320?811.580s (context 803.320?816.580s)
   - `pgw-538b27a8f0fdaf4ff1f2` 1967.390?2010.940s (context 1962.390?2015.940s)
4. `pg-58194dc5b0eb5cc6` ? 4 windows; `CarpetaTranscripciones/py_pg/pg_AMS KAP – Compliance – Session 7-20260824_123002UTC-Meeting Recording_segments.json`
   - `pgw-76c354919d894d6acfe7` 1103.810?1156.640s (context 1098.810?1161.640s)
   - `pgw-f37843de1c8e6d0d7590` 1587.980?1591.630s (context 1582.980?1596.630s)
   - `pgr-f4bad58d9fe436599e3a` 2361.920?2387.190s (context 2356.920?2392.190s)
   - `pgw-8d751248ca074ed02785` 2880.910?2884.640s (context 2875.910?2889.640s)
5. `pg-98250af646a5c138` ? 3 windows; `CarpetaTranscripciones/py_pg/pg_AMS_KAP_-_Compliance_-_Session_2_segments.json`
   - `pgw-491ea1087ae0e37adc62` 1227.200?1237.520s (context 1222.200?1242.520s)
   - `pgw-f7c2a37170355cc87875` 2033.720?2037.030s (context 2028.720?2042.030s)
   - `pgw-b0f5b027ce650cf89507` 2336.250?2339.780s (context 2331.250?2344.780s)
6. `pg-896f3fb2e5862a02` ? 3 windows; `CarpetaTranscripciones/py_pg/pg_Ams_kap_app_support_s10_segments.json`
   - `pgr-a43a77dbfdd9ca3c4739` 2113.380?2175.470s (context 2108.380?2180.470s)
   - `pgr-e8d73da62bd869b3a2f8` 2273.660?2481.700s (context 2268.660?2486.700s)
   - `pgr-31dadb87b8b9249dd5b0` 3672.000?3730.600s (context 3667.000?3735.600s)
7. `pg-611c4b9e32914de6` ? 6 windows; `CarpetaTranscripciones/py_pg/pg_Ams_kap_compliance_s4_segments.json`
   - `pgw-1410e9b1022c838b60c3` 1340.910?1355.380s (context 1335.910?1360.380s)
   - `pgw-d0d66b48bd10d8fddbca` 2475.500?2481.090s (context 2470.500?2486.090s)
   - `pgw-4fb209c5fafc8f5a1f0e` 2598.710?2602.590s (context 2593.710?2607.590s)
   - `pgw-78076da87a998a68c157` 2995.870?2999.730s (context 2990.870?3004.730s)
   - `pgw-b7bcd453be1786667b57` 3106.760?3117.180s (context 3101.760?3122.180s)
   - `pgw-7b234d40cb5d678cad2d` 3311.390?3327.150s (context 3306.390?3332.150s)
8. `pg-4957e30bcb15f2bf` ? 2 windows; `CarpetaTranscripciones/py_pg/pg_Shadow_221026_segments.json`
   - `pgr-68c115f633a8cdf63879` 3130.900?3167.940s (context 3125.900?3172.940s)
   - `pgw-8bad404d3afd65c0f335` 3198.340?3290.400s (context 3193.340?3295.400s)

## MISSING source preflight / resume plan

- `pg-3` `Videos/py_pg/pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording.mp4` ? 2607.812s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording_segments.json`; checkpoint absent; 5 serial chunks of up to 600s with 4s overlap; state `QUEUED`.
- `pg-9` `Videos/py_pg/pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording.mp4` ? 3572.032s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording_segments.json`; checkpoint absent; 6 serial chunks of up to 600s with 4s overlap; state `QUEUED`.
- `pg-10` `Videos/py_pg/pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4` ? 3011.456s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording_segments.json`; checkpoint absent; 6 serial chunks of up to 600s with 4s overlap; state `QUEUED`.
- `pg-11` `Videos/py_pg/pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording.mp4` ? 3571.265s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording_segments.json`; checkpoint absent; 6 serial chunks of up to 600s with 4s overlap; state `QUEUED`.
- `pg-12` `Videos/py_pg/pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording.mp4` ? 3383.296s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording_segments.json`; checkpoint absent; 6 serial chunks of up to 600s with 4s overlap; state `QUEUED`.
- `pg-13` `Videos/py_pg/pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording.mp4` ? 3880.768s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording_segments.json`; checkpoint absent; 7 serial chunks of up to 600s with 4s overlap; state `QUEUED`.
- `pg-15` `Videos/py_pg/pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording.mp4` ? 3988.992s; audio stream present; output `.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording_segments.json`; checkpoint absent; 7 serial chunks of up to 600s with 4s overlap; state `QUEUED`.

Output checkpoints are recovery candidates only. Validate media identity, timestamps, speech coverage, and meaningful gaps before marking any transcript VALID or promoting it.

Sessions 16/17 remain NEEDS_REVIEW: Session16 candidates reach ~42.94%; Session17 ~49.58% with ~928.4s tail unclassified. Existing VAD coverage is incomplete; both copies preserved, no canonical selected. See candidate comparison reports listed in JSON.

Queue counts unchanged: VALID=0; PARTIAL=8; NEEDS_REVIEW=5; MISSING=7; FAILED=0.
Recovery counts unchanged: P0=25; P1=187; P2=107 (closed); P3=66; processed=0.
