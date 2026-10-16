# Live Capture mobile UAT

Run on a phone connected to the same Wi-Fi as the Whisper host. Open the current HTTPS LAN URL from the dashboard's LAN access instructions; camera access is unavailable on insecure remote HTTP origins.

1. Open **Videos → New Recording** and confirm the modal fits the viewport without horizontal scrolling.
2. Select an existing **Project** before entering or changing the title.
3. Allow camera access. Confirm the live image appears in the preview before starting. If it does not, verify browser permission, close any other camera app, and retry; the modal must show its preview error.
4. Start recording. Confirm the timer advances, the preview remains live, and upload status reports acknowledged segments.
5. In **Continuous Playlist**, show two synthetic title cards on the source display. Confirm two logical videos appear, each with the selected project. Rename one and confirm.
6. Confirm the modal shows capture-session/logical-video status only; no `chunk-*`, `fragment-*`, or raw `FINALIZED` rows.
7. Cancel an active upload and confirm only that session changes. For a queued/processing user video, cancel and confirm **Cancelando** then **CANCELLED**. A completed video must have no cancel action.
8. Stop recording. Confirm the timer stops, pending upload state settles, and camera tracks are released when the modal closes.

Use synthetic title cards and test content only. Record phone model, OS/browser version, LAN URL (host only), each result, and any browser permission/error text in the release UAT record. Automated Playwright uses synthetic media and does not substitute for this physical-device check.
