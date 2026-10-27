# P&G recovery-window triage

- Raw windows: 448; after dedup/context merge: 385.
- Classifications: {"ALREADY_COVERED_BY_NEIGHBOR": 66, "NEEDS_VAD": 187, "TRANSCRIPT_BOUNDARY_GAP": 107, "VAD_CONFIRMED_GAP": 25}.
- NEEDS_ASR (existing VAD gap): 25; NEEDS_VAD (timestamp-only): 187; discarded as likely silence/non-speech: 0.
- No Whisper run, new VAD, or audio-energy pass was run. Local ASR is standing-approved; candidate windows remain prepared and ordered by source.
- Boundary-gap and already-covered classifications are metadata cues, not audio truth; they stay out of ASR unless new evidence overturns them.

| Source | Raw | After dedup/merge | VAD gap | Needs VAD | Boundary/covered |
|---|---:|---:|---:|---:|---:|
| pg-ccb11a4619acaa92 | 61 | 56 | 4 | 19 | 33 |
| pg-e3d73ded7776de64 | 36 | 29 | 1 | 17 | 11 |
| pg-e37b41cb13677886 | 45 | 40 | 2 | 24 | 14 |
| pg-58194dc5b0eb5cc6 | 57 | 52 | 4 | 18 | 30 |
| pg-98250af646a5c138 | 59 | 53 | 3 | 23 | 27 |
| pg-896f3fb2e5862a02 | 76 | 52 | 3 | 42 | 7 |
| pg-611c4b9e32914de6 | 60 | 58 | 6 | 16 | 36 |
| pg-4957e30bcb15f2bf | 54 | 45 | 2 | 28 | 15 |
