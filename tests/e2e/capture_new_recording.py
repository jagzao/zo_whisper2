"""W3/W4/W5 browser scenario: `Videos -> New Recording` capture shell.

Launches Chromium with deterministic fake media devices (no real camera or
microphone), grants camera permission, and proves the frozen W3/W4 journey:

1. The user reaches the capture shell from `Videos -> New Recording` (not only
   the header Capture icon).
2. The recording view exposes camera preview, Normal Recording / Continuous
   Playlist modes, crop control, Save local copy (default unchecked), Start/
   Stop Recording, a visible timer, upload/processing status, and the
   detected-title/logical-video shell with its empty state.
3. W4 fragment cadence/config and stable fragment IDs are deterministic
   (checked through pure state hooks — no 15s wait).
4. Starting capture with the fake device shows a live, incrementing timer.
5. W5: with a 1s deterministic cadence, at least two short fragments are
   durably ACKed while capture keeps running, via the distinct fragment
   endpoint (never the legacy per-fragment processing-chunk finalize), and the
   session keeps its 600s processing chunk_duration_sec with no chunks.
6. Stopping ACKs any remaining fragment and reaches the saved state; the
   synthetic mobile viewport keeps the controls usable.

Synthetic devices/media only. Reports PASS/FAIL checks to JSON like the other
capture e2e scripts.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
TIMEOUT_MS = 30000
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def _sessions() -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/capture/sessions", timeout=10)
    r.raise_for_status()
    return r.json().get("sessions", [])


def _close_safely(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return 1

    sessions_before = {s["sessionId"] for s in _sessions()}
    all_ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            permissions=["camera", "microphone"],
        )
        page = context.new_page()

        browser_errors: list[str] = []
        page.on("console", lambda msg: browser_errors.append(f"console: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: browser_errors.append(f"pageerror: {exc}"))

        try:
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)

            # 1. Videos -> New Recording entry.
            all_ok &= check(
                "videos_section_present",
                page.locator("#videosSection h2").inner_text().strip().lower() == "videos",
                page.locator("#videosSection h2").inner_text(),
            )
            all_ok &= check(
                "new_recording_button_visible",
                page.locator("#newRecordingBtn").is_visible()
                and page.locator("#newRecordingBtn").inner_text().strip() == "New Recording",
            )
            page.locator("#newRecordingBtn").click()
            page.wait_for_selector("#captureModal:not(.hidden)", timeout=TIMEOUT_MS)
            all_ok &= check("new_recording_opens_capture", page.locator("#captureModal:not(.hidden)").count() == 1)
            all_ok &= check("project_required_before_title", page.locator("#captureProject").evaluate("el => el.compareDocumentPosition(document.querySelector('#captureTitle')) & Node.DOCUMENT_POSITION_FOLLOWING") != 0)
            page.locator("#captureStartBtn").click()
            all_ok &= check("start_blocked_without_project", "Select an existing Whisper project" in page.locator("#captureError").inner_text())
            page.wait_for_function("document.querySelectorAll('#captureProject option').length > 1")
            page.locator("#captureProject").select_option(index=1)

            # 2. Required controls exist in the capture shell.
            all_ok &= check("preview_visible", page.locator("#capturePreview").is_visible())
            all_ok &= check(
                "front_and_rear_camera_options",
                page.locator("#captureCameraFacing option").all_text_contents() == ["Back camera", "Front camera"]
                and page.locator("#captureCameraFacing").input_value() == "environment",
            )
            all_ok &= check(
                "crop_clear_next_to_preview_selection",
                page.locator("#captureCropControls").evaluate("el => el.previousElementSibling.classList.contains('capture-preview-wrap')")
                and page.locator("#cropClearBtn").evaluate("el => el.parentElement.id === 'captureCropControls'"),
            )
            all_ok &= check("camera_and_audio_input_modes_visible", page.locator("#captureInputCamera").is_visible() and page.locator("#captureInputAudio").is_visible()
                            and "📷 Camera" in page.locator("#captureInputCamera").inner_text()
                            and "🎤 Audio" in page.locator("#captureInputAudio").inner_text())
            all_ok &= check(
                "normal_mode_visible",
                page.locator("#captureModeNormal").is_visible()
                and "Normal Recording" in page.locator("label[for='captureModeNormal']").inner_text(),
            )
            all_ok &= check(
                "playlist_mode_visible",
                page.locator("#captureModePlaylist").is_visible()
                and "Continuous Playlist" in page.locator("label[for='captureModePlaylist']").inner_text(),
            )
            all_ok &= check("crop_control_visible", page.locator("#cropOverlay").is_visible() and page.locator("#cropClearBtn").is_visible())
            all_ok &= check("save_local_present_unchecked", page.locator("#captureSaveLocal").is_checked() is False)
            all_ok &= check("start_button_visible", page.locator("#captureStartBtn").is_visible())
            all_ok &= check("stop_button_hidden_initially", page.locator("#captureStopBtn").is_hidden())
            all_ok &= check(
                "timer_reset_initial",
                page.locator("#captureTimer").inner_text() == "00:00:00" and page.locator("#captureTimerBadge").is_hidden(),
                page.locator("#captureTimer").inner_text(),
            )
            all_ok &= check("upload_status_visible", page.locator("#captureUploadStatus").is_visible())
            all_ok &= check(
                "logical_videos_shell_empty",
                page.locator("#captureLogicalVideos").is_visible()
                and "No detected titles yet" in page.locator("#captureLogicalVideos").inner_text(),
            )

            # 3. Mode choice is wired (playlist <-> normal).
            page.locator("#captureModePlaylist").check()
            all_ok &= check("playlist_mode_selectable", page.evaluate("() => window.__captureSnapshot().mode") == "playlist")
            page.locator("#captureModeNormal").check()
            all_ok &= check("normal_mode_selectable", page.evaluate("() => window.__captureSnapshot().mode") == "normal")

            # 3b. W4 fragment cadence/config — deterministic, no 15s wait.
            cfg = page.evaluate("() => window.__captureFragmentConfig()")
            all_ok &= check(
                "fragment_target_default",
                cfg.get("targetMs") == 15000 and cfg.get("resolvedMs") == 15000,
                json.dumps(cfg),
            )
            all_ok &= check(
                "fragment_configurable_range_10_30s",
                cfg.get("minMs") == 10000 and cfg.get("maxMs") == 30000,
                f"min={cfg.get('minMs')} max={cfg.get('maxMs')}",
            )
            all_ok &= check(
                "fragment_queue_bounded_4",
                cfg.get("maxPendingFragments") == 4,
                str(cfg.get("maxPendingFragments")),
            )
            page.locator("#captureChunkDuration").fill("10")
            resolved_10 = page.evaluate("() => window.__captureFragmentConfig().resolvedMs")
            page.locator("#captureChunkDuration").fill("30")
            resolved_30 = page.evaluate("() => window.__captureFragmentConfig().resolvedMs")
            page.locator("#captureChunkDuration").fill("15")
            all_ok &= check(
                "fragment_cadence_configurable",
                resolved_10 == 10000 and resolved_30 == 30000,
                f"10s={resolved_10} 30s={resolved_30}",
            )

            # 3c. W4/W5 stable, monotonically increasing fragment IDs.
            seq_a = page.evaluate("() => window.__captureTestFragmentSequence(3)")
            seq_b = page.evaluate("() => window.__captureTestFragmentSequence(3)")
            all_ok &= check(
                "fragment_ids_stable_monotonic",
                bool(seq_a.get("monotonic")) and bool(seq_b.get("monotonic"))
                and seq_a.get("ids") == ["fragment-000001", "fragment-000002", "fragment-000003"]
                and seq_b.get("ids") == ["fragment-000004", "fragment-000005", "fragment-000006"],
                f"a={seq_a} b={seq_b}",
            )

            # Deterministic network observation: every short fragment must go
            # to the distinct fragment endpoint — never the legacy
            # per-fragment processing-chunk finalize.
            fragment_posts: list[str] = []
            legacy_chunk_posts: list[str] = []

            def _observe_request(req) -> None:
                if req.method != "POST":
                    return
                if "/fragments" in req.url:
                    fragment_posts.append(req.url)
                if "/chunks/" in req.url:
                    legacy_chunk_posts.append(req.url)

            page.on("request", _observe_request)

            # 4. Start fake-device capture with a short deterministic cadence
            # (1s) so multiple short fragments are emitted and ACKed while the
            # capture keeps running.
            page.locator("#captureChunkDuration").fill("1")
            page.locator("#captureModePlaylist").check()
            page.wait_for_function("document.querySelectorAll('#captureProject option').length > 1")
            page.locator("#captureProject").select_option(index=1)
            page.evaluate("""() => {
                const mediaDevices = navigator.mediaDevices;
                const original = mediaDevices.getUserMedia.bind(mediaDevices);
                window.__captureRequestedFacingModes = [];
                mediaDevices.getUserMedia = constraints => {
                    const facing = constraints.video && constraints.video.facingMode;
                    window.__captureRequestedFacingModes.push({
                        ideal: facing && facing.ideal || null,
                        exact: facing && facing.exact || null,
                        video: constraints.video,
                        audio: constraints.audio,
                    });
                    const video = facing && facing.exact
                        ? Object.assign({}, constraints.video, {facingMode: {ideal: facing.exact}})
                        : constraints.video;
                    return original(Object.assign({}, constraints, {video}));
                };
            }""")
            page.locator("#captureStartBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS
            )
            all_ok &= check("recording_state", page.locator("#captureState").inner_text() == "Recording")
            all_ok &= check(
                "recording_timer_over_preview",
                page.locator("#captureTimerBadge").is_visible()
                and page.locator("#captureTimerBadge").evaluate("el => el.parentElement.classList.contains('capture-preview-wrap')"),
            )
            all_ok &= check(
                "rear_camera_requested",
                page.evaluate("() => window.__captureRequestedFacingModes[0].ideal") == "environment",
                str(page.evaluate("() => window.__captureRequestedFacingModes[0]")),
            )
            page.evaluate("() => { window.__captureStreamBeforeSwitch = capture.stream; }")
            page.locator("#captureCameraFacing").select_option("user")
            page.wait_for_function("() => { const s=window.__captureSnapshot(); return s.state==='recording' && !s.cameraSwitching && s.activeFacingMode==='user' && !!capture.recorder; }")
            all_ok &= check(
                "front_camera_switch_keeps_recording_stream",
                page.evaluate("() => capture.stream !== window.__captureStreamBeforeSwitch && document.querySelector('#capturePreview').srcObject === capture.stream && capture.recorder.stream === capture.stream"),
                str(page.evaluate("() => window.__captureSnapshot().activeFacingMode")),
            )
            all_ok &= check("front_facing_mode_requested", page.evaluate("() => window.__captureRequestedFacingModes.some(x => x.exact === 'user')"))
            page.evaluate("() => { window.__captureStreamFront = capture.stream; }")
            page.locator("#captureCameraFacing").select_option("environment")
            page.wait_for_function("() => { const s=window.__captureSnapshot(); return s.state==='recording' && !s.cameraSwitching && s.activeFacingMode==='environment' && !!capture.recorder; }")
            all_ok &= check(
                "rear_switch_restores_preview_recording_stream",
                page.evaluate("() => capture.stream !== window.__captureStreamFront && document.querySelector('#capturePreview').srcObject === capture.stream && capture.recorder.stream === capture.stream"),
            )
            preview = page.locator("#capturePreview").evaluate("el => ({width:el.videoWidth, inline:el.playsInline, autoplay:el.autoplay, sameStream:el.srcObject === capture.recorder.stream})")
            all_ok &= check("live_preview_uses_recording_stream", preview["width"] > 0 and preview["inline"] and preview["autoplay"] and preview["sameStream"], json.dumps(preview))
            session_project = page.evaluate("async id => (await (await fetch(`/api/capture/sessions/${id}`)).json()).session.projectId", page.evaluate("window.__captureSnapshot().sessionId"))
            all_ok &= check("capture_project_persisted", session_project == page.locator("#captureProject").input_value(), str(session_project))
            all_ok &= check("stop_button_visible_while_recording", page.locator("#captureStopBtn").is_visible())
            all_ok &= check(
                "preview_has_stream",
                page.evaluate("() => document.getElementById('capturePreview').srcObject !== null"),
            )
            page.wait_for_function(
                "() => { const v = document.getElementById('capturePreview'); return v.readyState >= 2 && v.videoWidth > 0; }",
                timeout=TIMEOUT_MS,
            )
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot(); return !!(s && s.timerSeconds >= 2); }",
                timeout=TIMEOUT_MS,
            )
            timer_text = page.locator("#captureTimer").inner_text()
            all_ok &= check(
                "timer_advances_while_recording",
                timer_text != "00:00:00" and page.evaluate("() => window.__captureSnapshot().timerSeconds") >= 2,
                timer_text,
            )

            # 5. W5: at least 2 short fragments are durably ACKed while capture
            # continues (state stays Recording).
            page.wait_for_function(
                "() => { const s = window.__captureSnapshot && window.__captureSnapshot();"
                " return !!(s && s.ackedFragmentIds.length >= 2 && s.state === 'recording'); }",
                timeout=TIMEOUT_MS,
            )
            mid = page.evaluate("() => window.__captureSnapshot()")
            acked_mid = mid.get("ackedFragmentIds") or []
            all_ok &= check(
                "two_fragment_acks_while_recording",
                len(acked_mid) >= 2 and mid.get("state") == "recording",
                f"acked={acked_mid} state={mid.get('state')}",
            )
            all_ok &= check(
                "fragment_queue_drains_after_ack",
                mid.get("pendingUploads") == 0 and mid.get("stalled") is False,
                f"pending={mid.get('pendingUploads')} stalled={mid.get('stalled')}",
            )
            all_ok &= check(
                "fragments_use_distinct_endpoint",
                len(fragment_posts) >= 2 and not legacy_chunk_posts,
                f"fragments={len(fragment_posts)} legacyChunks={legacy_chunk_posts[:3]}",
            )

            session_id = mid.get("sessionId")
            server_fragments = requests.get(
                f"{DASHBOARD_URL}/api/capture/sessions/{session_id}/fragments", timeout=10
            ).json().get("fragments", [])
            all_ok &= check(
                "fragments_durable_on_server",
                len(server_fragments) >= 2
                and all(f.get("state") == "ACKED" and f.get("mediaSizeBytes", 0) > 0 for f in server_fragments),
                json.dumps([{k: f.get(k) for k in ("fragmentId", "sequence", "state", "mediaSizeBytes")} for f in server_fragments]),
            )
            all_ok &= check(
                "acked_ids_match_server_order",
                [f["fragmentId"] for f in server_fragments][: len(acked_mid)] == list(acked_mid),
                f"server={[f['fragmentId'] for f in server_fragments]} acked={acked_mid}",
            )
            sequences = [f["sequence"] for f in server_fragments]
            all_ok &= check(
                "fragment_sequence_ordered",
                sequences == sorted(sequences) and len(set(sequences)) == len(sequences),
                str(sequences),
            )
            current_session_id = mid.get("sessionId")
            page.wait_for_function("id => { const row = document.querySelector(`#captureJobs [data-session-id=\"${id}\"]`); return !!row && row.innerText.includes('segmentos subidos'); }", arg=current_session_id, timeout=15000)
            jobs_row = page.locator(f"#captureJobs [data-session-id='{current_session_id}']")
            jobs_text = jobs_row.inner_text()
            status_text = page.locator("#captureUploadStatus").inner_text()
            all_ok &= check("user_level_segment_progress_visible", "segmentos subidos" in jobs_text and "segments uploaded" in status_text)
            all_ok &= check("internal_fragment_and_chunk_ids_hidden", all(value not in jobs_text for value in ("chunk-", "fragment-", "FINALIZED")), jobs_text)
            server_session = requests.get(
                f"{DASHBOARD_URL}/api/capture/sessions/{session_id}", timeout=10
            ).json()["session"]
            all_ok &= check("playlist_mode_persisted", server_session.get("captureMode") == "playlist")
            all_ok &= check(
                "short_fragments_not_processing_chunks",
                server_session.get("chunkDurationSec") == 600 and server_session.get("chunks") == [],
                f"chunkDurationSec={server_session.get('chunkDurationSec')} chunks={server_session.get('chunks')}",
            )

            # 6. Stop succeeds and reaches the saved state; the final short
            # fragment is ACKed before the session is finalized.
            page.locator("#captureStopBtn").click()
            page.wait_for_function(
                "document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS
            )
            all_ok &= check("capture_saved_state", page.locator("#captureState").inner_text() == "Saved")

            final = page.evaluate("() => window.__captureSnapshot()")
            acked_final = final.get("ackedFragmentIds") or []
            all_ok &= check(
                "final_fragment_acked_on_stop",
                final.get("pendingUploads") == 0
                and final.get("stalled") is False
                and len(acked_final) >= 2
                and set(acked_final).issubset(set(final.get("fragmentIds") or [])),
                json.dumps({k: final.get(k) for k in ("ackedFragmentIds", "fragmentIds", "pendingUploads")}),
            )
            all_ok &= check(
                "no_legacy_chunk_finalize_from_browser",
                not legacy_chunk_posts,
                str(legacy_chunk_posts[:3]),
            )

            sessions_after = _sessions()
            new_sessions = [s for s in sessions_after if s["sessionId"] not in sessions_before]
            all_ok &= check("capture_session_created", len(new_sessions) == 1, f"{len(new_sessions)} new sessions")
            if new_sessions:
                all_ok &= check("capture_session_finalized", new_sessions[0]["status"] == "FINALIZED", new_sessions[0]["status"])
                all_ok &= check("camera_source_persisted_after_switch", new_sessions[0].get("captureSource") == "environment", str(new_sessions[0].get("captureSource")))
            video_session = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{session_id}", timeout=10).json()["session"]
            all_ok &= check("one_validated_final_media_per_capture", bool(video_session.get("finalMedia"))
                            and video_session["finalMedia"].get("sizeBytes", 0) > 0
                            and len(video_session["finalMedia"].get("processingChunkIds", [])) >= 1,
                            json.dumps(video_session.get("finalMedia")))
            video_rows = [f for f in requests.get(f"{DASHBOARD_URL}/api/files", timeout=30).json().get("files", [])
                          if f.get("capture_session_id") == session_id]
            all_ok &= check("one_user_video_row_for_session", len(video_rows) == 1, str(len(video_rows)))
            if video_session.get("finalMedia"):
                video_stream = requests.get(f"{DASHBOARD_URL}/stream", params={"id": f"Videos:live_capture/{session_id}/{video_session['finalMedia']['relativePath']}"}, timeout=20)
                all_ok &= check("final_video_stream_available", video_stream.status_code == 200 and len(video_stream.content) > 0,
                                f"HTTP {video_stream.status_code}, {len(video_stream.content)} bytes")

            # Synthetic mobile viewport keeps the capture controls usable.
            page.set_viewport_size({"width": 390, "height": 844})
            mobile_ok = page.locator("#capturePreview").is_visible() and (
                page.locator("#captureStartBtn").is_visible() or page.locator("#captureStopBtn").is_visible()
            )
            all_ok &= check("mobile_viewport_capture_controls", mobile_ok)
            mobile_geometry = page.evaluate("""() => {
                const modal=document.querySelector('#captureModal .capture-modal');
                const crop=document.querySelector('#captureCropControls');
                const clear=document.querySelector('#cropClearBtn');
                return {width:innerWidth, documentWidth:document.documentElement.scrollWidth,
                    modalWidth:modal.clientWidth, modalScrollWidth:modal.scrollWidth,
                    cropWidth:crop.clientWidth, clearRight:clear.getBoundingClientRect().right,
                    cropRight:crop.getBoundingClientRect().right,
                    clearAdjacent:clear.parentElement===crop,
                    timerParent:document.querySelector('#captureTimerBadge').parentElement.classList.contains('capture-preview-wrap')};
            }""")
            all_ok &= check(
                "mobile_crop_and_timer_fit",
                mobile_geometry["documentWidth"] <= mobile_geometry["width"] + 1
                and mobile_geometry["modalScrollWidth"] <= mobile_geometry["modalWidth"] + 1
                and mobile_geometry["clearAdjacent"] and mobile_geometry["clearRight"] <= mobile_geometry["cropRight"] + 1
                and mobile_geometry["timerParent"],
                json.dumps(mobile_geometry),
            )
            page.locator("#captureInputAudio").click()
            audio_mode_controls = page.evaluate("""() => ({camera:document.querySelector('#captureCameraFacing').getBoundingClientRect().width > 0, crop:!document.querySelector('#captureCropControls').classList.contains('hidden'), preview:!document.querySelector('#captureAudioPreview').classList.contains('hidden'), kind:window.__captureSnapshot().captureKind})""")
            all_ok &= check(
                "audio_mode_hides_camera_crop_controls",
                page.locator("#captureCameraFacing").is_hidden()
                and page.locator("#captureCropControls").is_hidden()
                and page.locator("#captureAudioPreview").is_visible(),
                json.dumps(audio_mode_controls),
            )
            page.locator("#captureStartBtn").click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Recording'", timeout=TIMEOUT_MS)
            audio_state = page.evaluate("""() => ({snapshot:window.__captureSnapshot(),
                videoTracks:capture.stream.getVideoTracks().length,
                audioTracks:capture.stream.getAudioTracks().length,
                videoHasStream:!!document.getElementById('capturePreview').srcObject,
                audioPreviewVisible:!document.getElementById('captureAudioPreview').classList.contains('hidden'),
                timerVisible:!document.getElementById('captureTimerBadge').classList.contains('hidden'),
                constraints:window.__captureRequestedFacingModes[window.__captureRequestedFacingModes.length-1]})""")
            all_ok &= check(
                "audio_mode_microphone_only_and_timer_visible",
                audio_state["snapshot"]["captureKind"] == "audio"
                and audio_state["videoTracks"] == 0 and audio_state["audioTracks"] > 0
                and not audio_state["videoHasStream"] and audio_state["audioPreviewVisible"] and audio_state["timerVisible"]
                and audio_state["constraints"]["video"] is False and audio_state["constraints"]["audio"] is True,
                json.dumps(audio_state),
            )
            page.wait_for_function("window.__captureSnapshot().timerSeconds >= 1", timeout=5000)
            audio_session_id = page.evaluate("() => window.__captureSnapshot().sessionId")
            audio_session = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{audio_session_id}", timeout=10).json()["session"]
            all_ok &= check(
                "audio_session_project_and_kind_persisted",
                audio_session.get("projectId") == page.locator("#captureProject").input_value()
                and audio_session.get("captureKind") == "audio"
                and audio_session.get("captureSource") == "microphone",
                json.dumps({k:audio_session.get(k) for k in ("projectId", "captureKind", "captureSource")}),
            )
            page.locator("#captureStopBtn").click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Saved'", timeout=TIMEOUT_MS)
            audio_fragments = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{audio_session_id}/fragments", timeout=10).json()["fragments"]
            audio_map = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{audio_session_id}/processing-chunks", timeout=10).json()["processingChunks"]
            all_ok &= check(
                "audio_fragment_and_chunk_inherit_project",
                bool(audio_fragments) and all(f.get("projectId") == audio_session["projectId"] for f in audio_fragments)
                and bool(audio_map) and all(c.get("projectId") == audio_session["projectId"] for c in audio_map),
                f"fragments={len(audio_fragments)} chunks={len(audio_map)}",
            )
            listed = requests.get(f"{DASHBOARD_URL}/api/files", timeout=30).json().get("files", [])
            audio_file = next((f for f in listed if f.get("capture_session_id") == audio_session_id), None)
            all_ok &= check(
                "audio_capture_uses_normal_project_listing",
                bool(audio_file) and audio_file.get("media_kind") == "audio" and audio_file.get("project") == audio_session["projectId"],
                json.dumps({k:audio_file.get(k) for k in ("media_kind", "project", "user_state")} if audio_file else None),
            )
            final_audio_session = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{audio_session_id}", timeout=10).json()["session"]
            all_ok &= check("audio_mode_has_single_final_output", bool(final_audio_session.get("finalMedia"))
                            and final_audio_session["finalMedia"].get("extension") in {".webm", ".m4a", ".wav", ".ogg"},
                            json.dumps(final_audio_session.get("finalMedia")))
            page.locator("#captureModal .close-x").click()
            page.wait_for_function("() => Array.isArray(window._allFiles) && window._allFiles.some(f => f.capture_session_id)", timeout=TIMEOUT_MS)
            if video_rows:
                video_id = video_rows[0]["media_id"]
                row = page.locator(f'tr[data-media-id="{video_id}"]')
                row.locator(".btn-view").click()
                page.wait_for_selector("#editorMedia[controls]", timeout=TIMEOUT_MS)
                all_ok &= check("show_opens_native_video_player", page.locator("#editorMedia").evaluate("el => el.tagName === 'VIDEO' && el.controls")
                                and page.locator("#editorMedia").is_visible())
                page.locator("#previewModal .close-x").click()
            if audio_file:
                audio_row = page.locator(f'tr[data-media-id="{audio_file["media_id"]}"]')
                audio_row.locator(".btn-view").click()
                page.wait_for_selector("#editorMedia[controls]", timeout=TIMEOUT_MS)
                all_ok &= check("show_opens_native_audio_player", page.locator("#editorMedia").evaluate("el => el.tagName === 'AUDIO' && el.controls")
                                and page.locator("#editorMedia").is_visible())
                page.locator("#previewModal .close-x").click()
            page.set_viewport_size({"width": 1280, "height": 900})
        finally:
            all_ok &= check("capture_no_browser_errors", not browser_errors, "; ".join(browser_errors)[:1000])
            _close_safely(page)
            _close_safely(context)
            _close_safely(browser)

    out = Path("capture_new_recording_report.json")
    out.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
