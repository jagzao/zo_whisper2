# P&G PARTIAL candidate recovery windows

- Sources: 8; word timestamp gaps >1.5s: 987; merged 5s-context candidate windows: 448.
 - Every interval is an unreviewed timestamp/VAD candidate. A gap does not establish speech or missing content. Local ASR is `STANDING_APPROVED`; all 448 windows are prepared with stable IDs and remain `PREPARED` pending semantic confirmation. No ASR has run.

| Source | Media reach | Speech coverage | Uncovered speech | Word gaps >1.5s | Review windows | Tail status |
|---|---:|---:|---:|---:|---:|---|
| pg-ccb11a4619acaa92 | 91.22% | 90.56% | 309.64s | 100 | 61 | 343.668s media gap |
| pg-e3d73ded7776de64 | 25.89% | 85.17% | 248.728s | 63 | 36 | 5446.806s media gap; VAD NOT ASSESSED |
| pg-e37b41cb13677886 | 99.68% | 89.67% | 190.69s | 76 | 45 | 6.836s media gap |
| pg-58194dc5b0eb5cc6 | 99.84% | 86.4% | 387.212s | 94 | 57 | 5.025s media gap |
| pg-98250af646a5c138 | 98.71% | 90.8% | 294.542s | 102 | 59 | 46.791s media gap |
| pg-896f3fb2e5862a02 | 86.9% | 79.34% | 547.508s | 312 | 76 | 588.361s media gap; prior tail VAD reviewed (0.992s unsupported speech) |
| pg-611c4b9e32914de6 | 78.85% | 93.58% | 207.916s | 87 | 60 | 960.197s media gap |
| pg-4957e30bcb15f2bf | 99.85% | 80.85% | 364.596s | 153 | 54 | 5.154s media gap |

Windows merge overlapping 5s context around known major VAD gaps and word-timestamp gaps over 1.5s. These windows are for semantic review and micro-gap reconciliation; they are not confirmed speech. Session13?s 5,446.806s tail remains `NOT_ASSESSED` and is excluded from ASR targeting pending VAD/tail classification. The queue remains serial: pg-1 VAD first; then cheap semantic review and confirmed PARTIAL recovery; remaining PARTIAL; seven missing sources.
