# P&G PARTIAL candidate recovery windows

- Sources: 8; word timestamp gaps >1.5s: 987; merged contextual windows: 448.
- Priority: 25 P1 windows overlap an existing major VAD gap; 423 P2 windows are timestamp-only candidates. P1 precedes P2 within each source.
- Local ASR: `STANDING_APPROVED`; external P&G processing: `NOT_AUTHORIZED`.
- Window state: PREPARED=448; PROCESSED=0. All windows have stable IDs; no Whisper run has started.

A gap is a candidate only. P1 means existing VAD marked speech absent from ASR coverage; it still requires semantic reconciliation. P2 means timestamps alone; it does not establish speech or missing knowledge.

| Source | Reach | Speech coverage | Uncovered | Word gaps | P1 VAD windows | P2 timestamp windows | Tail status |
|---|---:|---:|---:|---:|---:|---:|---|
| pg-ccb11a4619acaa92 | 91.22% | 90.56% | 309.64s | 100 | 4 | 57 | 343.668s media gap |
| pg-e3d73ded7776de64 | 25.89% | 85.17% | 248.728s | 63 | 1 | 35 | 5446.806s media gap; VAD not assessed |
| pg-e37b41cb13677886 | 99.68% | 89.67% | 190.69s | 76 | 2 | 43 | 6.836s media gap |
| pg-58194dc5b0eb5cc6 | 99.84% | 86.4% | 387.212s | 94 | 4 | 53 | 5.025s media gap |
| pg-98250af646a5c138 | 98.71% | 90.8% | 294.542s | 102 | 3 | 56 | 46.791s media gap |
| pg-896f3fb2e5862a02 | 86.9% | 79.34% | 547.508s | 312 | 3 | 73 | 588.361s media gap; prior tail VAD found 0.992s unsupported speech |
| pg-611c4b9e32914de6 | 78.85% | 93.58% | 207.916s | 87 | 6 | 54 | 960.197s media gap |
| pg-4957e30bcb15f2bf | 99.85% | 80.85% | 364.596s | 153 | 2 | 52 | 5.154s media gap |

Session13?s 5,446.806s tail remains unclassified and is excluded from these ASR windows. Context windows merge overlaps using 5s margins. On restart, use stable `WINDOW_ID` and skip any window with completed status/result hash.
