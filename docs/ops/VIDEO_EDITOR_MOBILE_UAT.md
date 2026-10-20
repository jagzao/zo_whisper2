# Whisper video editor: phone UAT

Use a Galaxy phone on the same Wi-Fi as the Whisper computer. Install the public
root certificate first by following `MOBILE_LAN_ACCESS.md`; never copy a private
key to the phone. Open:

`https://192.168.50.20:5001/`

## Capture and orientation

1. Open **Capture** and grant camera/microphone access. Select **Auto** quality.
2. Confirm the preview identifies the rear camera and shows its actual width,
   height, and frame rate. Record the displayed values; do not infer them from
   the selector.
3. Rotate to landscape. Confirm the preview uses landscape framing without
   stretching, the timer stays visible, and Start/Stop remain accessible.
4. Draw and adjust the crop with a finger. Rotate back to portrait and landscape;
   confirm the crop stays aligned with the camera image.
5. Start recording, keep it running for more than 30 seconds, then stop. Wait
   until the saved session appears in Videos.
6. Open the recording with **Show**. Verify playback, duration, orientation,
   and resolution. Compare its orientation and dimensions with the values shown
   during capture.

Record phone model, browser, displayed camera settings, and any failure. Desktop
Playwright uses synthetic media and does not count as real-phone UAT.
