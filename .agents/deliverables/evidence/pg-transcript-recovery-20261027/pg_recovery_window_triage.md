# P&G recovery-window triage

- Raw windows: 448; after dedup/context merge: 385 (63 context merges; zero duplicate or overlapping raw context windows).
- Priority: P0 VAD-confirmed 25; P1 needs VAD 187; P2 boundary gaps 107; P3 already covered 66.
- Boundary reconciliation: all 107 have neighboring transcript context on both sides; 139 constituent gaps range 1.51?3.99s (median 2.16s); no canonical segment overlap. Retain as P2; no ASR escalation based on metadata alone.
- ASR candidates: 25 P0 only; process sequentially only after pg-1 VAD and safe resource check. P1 requires VAD first. P3 excluded.
- Discarded as likely silence/non-speech: 0. No Whisper, new VAD, or audio-energy pass run; metadata cannot prove silence.
- Resource state: pg-1 VAD remains WAITING_RESOURCES; three samples showed 2.96, 2.94, then 2.81 GB available. No heavy job started.
- Boundary/punctuation and neighbor-text labels are metadata cues, not audio truth.

| Source | Raw | Derived | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|---:|---:|
| pg-ccb11a4619acaa92 | 61 | 56 | 4 | 19 | 22 | 11 |
| pg-e3d73ded7776de64 | 36 | 29 | 1 | 17 | 10 | 1 |
| pg-e37b41cb13677886 | 45 | 40 | 2 | 24 | 8 | 6 |
| pg-58194dc5b0eb5cc6 | 57 | 52 | 4 | 18 | 29 | 1 |
| pg-98250af646a5c138 | 59 | 53 | 3 | 23 | 19 | 8 |
| pg-896f3fb2e5862a02 | 76 | 52 | 3 | 42 | 3 | 4 |
| pg-611c4b9e32914de6 | 60 | 58 | 6 | 16 | 10 | 26 |
| pg-4957e30bcb15f2bf | 54 | 45 | 2 | 28 | 6 | 9 |
