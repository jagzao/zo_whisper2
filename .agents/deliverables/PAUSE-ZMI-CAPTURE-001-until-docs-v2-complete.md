# PAUSE-ZMI-CAPTURE-001 — Finish Documentation V2 before continuing Live Capture

## Status
PAUSED_BY_OWNER

## Current Live Capture progress
Remote branch:
`feat/zmi-live-capture-v1`

Current implementation checkpoint at pause:
`8cdc5e37cbb3ec087f272d7f1fdf0642516c2dc9`
(`feat(capture): add durable session domain`)

Treat this as the completed Slice A checkpoint unless later review proves otherwise.

## Owner workflow rule
Do NOT continue Slice B or any later Live Capture implementation while Documentation Synthesis V2 remains unfinished.

Required sequence:
1. finish `feat/zmi-documentation-synthesis-v2`;
2. ChatGPT review;
3. heavy deterministic validation;
4. one real non-sensitive documentation quality acceptance;
5. owner merge/close decision;
6. switch the SAME normal project workspace to `feat/zmi-live-capture-v1`;
7. review Slice A checkpoint;
8. resume from first incomplete slice.

No isolated/parallel worktree is required or desired.

Do not revert valid Slice A work merely because it is paused.
