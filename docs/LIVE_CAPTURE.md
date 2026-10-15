# Live Capture

Live Capture is available from the Whisper dashboard. Select the useful screen region before recording when the camera includes surrounding space; the normalized crop is saved with the session and is used for applicable frame extraction. The original recording is retained.

Allow camera and, when needed, microphone access in the browser. The dashboard shows recording and upload states. Recording is sent in bounded chunks while capture continues. Use **Cancelar subida** to abort an in-flight upload; retry is available afterward. Use **Cancelar procesamiento** for queued or active processing. The dashboard shows **Cancelando** until cancellation completes. A cancelled item can be processed again or explicitly deleted.

If the recording has no usable audio, the video remains available with `AUDIO_MISSING` / `TRANSCRIPT_REQUIRED`; documentation processing does not fail just because audio is absent. Supply a transcript later from the session controls. A late transcript is associated loosely with the session and is not treated as second-by-second synchronized.

Capture sessions store creation and recording timestamps, session and chunk identity/order, processing and audio/transcript states, and crop metadata. Interrupted sessions are reconciled on restart where possible; incomplete uploads can be retried. Media cleanup only presents advisory candidates. Original media is never automatically deleted; deletion requires an explicit user action.

Automated media checks use synthetic fixtures only.
