# P&G 20-source identity and provenance audit

- Logical sources: 20; mapped source sizes matched: 20; sidecar files: 16; sidecar SHA-256 matches: 16; missing sources: 7; provenance review flags: 0.
- Sidecars with invalid segment timestamps: 0; segment/word order monotonic: 16/16 and 16/16; source audio basename matches: 16/16.
- Zero-duration word timestamps: 803 total across candidates; retained as word-timing defects, separate from segment boundary validity.
 - Source-media SHA-256 not computed to avoid large-media I/O; source canonical path, exact file size and mapped duration checked.

| Source ID | Transcript state | Candidates | Reach | Provenance |
|---|---|---:|---:|---|
| pg-1 | NEEDS_REVIEW | 1 | 99.82% | MATCHED |
| pg-ccb11a4619acaa92 | PARTIAL | 1 | 91.22% | MATCHED |
| pg-3 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-e3d73ded7776de64 | PARTIAL | 1 | 25.89% | MATCHED |
| pg-e37b41cb13677886 | PARTIAL | 1 | 99.68% | MATCHED |
| pg-7ec100f076b0e0a0 | NEEDS_REVIEW | 2 | 99.10%, 99.10% | MATCHED |
| pg-27753be62f40a4fa | NEEDS_REVIEW | 2 | 42.94%, 42.94% | MATCHED |
| pg-cdcc12a6c7eea9bc | NEEDS_REVIEW | 2 | 49.58%, 49.57% | MATCHED |
| pg-9 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-10 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-11 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-12 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-13 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-58194dc5b0eb5cc6 | PARTIAL | 1 | 99.84% | MATCHED |
| pg-15 | MISSING | 0 | ? | SOURCE_VERIFIED_NO_SIDECAR |
| pg-98250af646a5c138 | PARTIAL | 1 | 98.71% | MATCHED |
| pg-896f3fb2e5862a02 | PARTIAL | 1 | 86.90% | MATCHED |
| pg-09eb7fdd89877b64 | NEEDS_REVIEW | 1 | 99.83% | MATCHED |
| pg-611c4b9e32914de6 | PARTIAL | 1 | 78.85% | MATCHED |
| pg-4957e30bcb15f2bf | PARTIAL | 1 | 99.85% | MATCHED |

All 20 canonical source paths exist at the recorded sizes. All 16 sidecar files match manifest SHA-256 and reference the corresponding source basename. All sidecar segment timestamps are valid and ordered. Divergent candidates remain separate. Seven sources have no candidate sidecar and remain genuinely missing in the current inventory.
