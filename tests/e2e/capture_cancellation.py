"""Synthetic browser check for upload and queued-job cancellation controls."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import requests

DASHBOARD_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000")
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    REPORT.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")
    return condition


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 1

    all_ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        context = browser.new_context(permissions=["camera"], viewport={"width": 390, "height": 844})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.add_init_script("""
                const realFetch = window.fetch.bind(window);
                window.fetch = (input, init = {}) => {
                    if (String(input).includes('/fragments') && init.signal) {
                        window.__uploadStarted = true;
                        return new Promise((resolve, reject) => init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), {once:true}));
                    }
                    return realFetch(input, init);
                };
            """)
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_selector("#filesList")
            page.locator('button[aria-label="Capture"]').click()
            page.wait_for_selector("#captureModal:not(.hidden)")
            page.locator("#captureChunkDuration").fill("1")
            page.wait_for_function("document.querySelectorAll('#captureProject option').length > 1")
            page.locator("#captureProject").select_option(index=1)
            page.locator("#captureStartBtn").click()
            page.wait_for_function("document.getElementById('captureState').textContent === 'Recording'")
            page.wait_for_function("window.__uploadStarted === true", timeout=30000)
            all_ok &= check("cancel_upload_button_visible", page.locator("#captureCancelUploadBtn").is_visible())
            page.locator("#captureCancelUploadBtn").click()
            page.wait_for_function("document.getElementById('captureError').textContent.includes('UPLOAD_CANCELLED')")
            session_id = page.evaluate("window.__captureSnapshot().sessionId")
            snapshot = page.evaluate("window.__captureSnapshot()")
            # W5: an aborted fragment upload is never durably stored, and the
            # queued blob is retained (never marked uploaded) for retry.
            server_fragments = requests.get(
                f"{DASHBOARD_URL}/api/capture/sessions/{session_id}/fragments", timeout=10
            ).json()["fragments"]
            all_ok &= check(
                "upload_aborted_no_durable_fragment",
                server_fragments == [] and snapshot["pendingUploads"] >= 1 and snapshot["stalled"] is True,
                f"fragments={len(server_fragments)} pending={snapshot['pendingUploads']} stalled={snapshot['stalled']}",
            )
            all_ok &= check("upload_retry_available", page.locator("#captureRetryBtn").is_visible())

            unique_title = 'cancel queued job ' + uuid.uuid4().hex[:8]
            created = page.evaluate("""async (title) => {
                const token = DASHBOARD_TOKEN;
                const post = (url, body) => fetch(url, {method:'POST', headers:{'X-Local-Dashboard-Token':token,'Content-Type':'application/json'}, body:JSON.stringify(body)}).then(r=>r.json());
                const session = (await post('/api/capture/sessions', {title, project_id:'Zo Interviews'})).session;
                await post(`/api/capture/sessions/${session.sessionId}/chunks/start`, {});
                await fetch(`/api/capture/sessions/${session.sessionId}/chunks/0/finalize`, {method:'POST', headers:{'X-Local-Dashboard-Token':token,'X-Media-Extension':'.webm','Content-Type':'application/octet-stream'}, body:new Blob(['synthetic video bytes'])});
                return session.sessionId;
            }""", unique_title)
            page.wait_for_function("title => document.getElementById('captureJobs').textContent.includes(title)", arg=unique_title)
            job = page.locator("#captureJobs .row").filter(has_text=unique_title)
            all_ok &= check("queued_cancel_button_visible", job.get_by_role("button", name="Cancelar procesamiento").is_visible())
            job.get_by_role("button", name="Cancelar procesamiento").click()
            job.get_by_text("CANCELLED").wait_for(timeout=10000)
            row_text = job.inner_text()
            buttons_text = job.locator("button").all_text_contents()
            all_ok &= check("cancelled_retry_visible_without_chunk_details", "Procesar de nuevo" in buttons_text and "chunk-" not in row_text and "Eliminar" not in buttons_text, f"{row_text} :: {buttons_text}")
            final = requests.get(f"{DASHBOARD_URL}/api/capture/sessions/{created}", timeout=10).json()["session"]
            all_ok &= check("queued_job_cancelled", final["chunks"][0]["state"] == "CANCELLED")

            active_title = 'cancel active job ' + uuid.uuid4().hex[:8]
            active_id = page.evaluate("""async (title) => {
                const token = DASHBOARD_TOKEN;
                const post = (url, body) => fetch(url, {method:'POST', headers:{'X-Local-Dashboard-Token':token,'Content-Type':'application/json'}, body:JSON.stringify(body)}).then(r=>r.json());
                const session = (await post('/api/capture/sessions', {title, project_id:'Zo Interviews'})).session;
                await post(`/api/capture/sessions/${session.sessionId}/chunks/start`, {});
                await fetch(`/api/capture/sessions/${session.sessionId}/chunks/0/finalize`, {method:'POST', headers:{'X-Local-Dashboard-Token':token,'X-Media-Extension':'.webm','Content-Type':'application/octet-stream'}, body:new Blob(['synthetic active bytes'])});
                return session.sessionId;
            }""", active_title)
            mock_state = {"value": "PROCESSING"}

            def show_active_state(route):
                payload = route.fetch().json()
                for item in payload.get("sessions", []):
                    if item["sessionId"] == active_id:
                        item["chunks"][0]["state"] = mock_state["value"]
                route.fulfill(json=payload)

            def request_active_cancel(route):
                payload = route.fetch().json()
                mock_state["value"] = "CANCEL_REQUESTED"
                payload["session"]["chunks"][0]["state"] = "CANCEL_REQUESTED"
                route.fulfill(json=payload)

            page.route("**/api/capture/sessions", show_active_state)
            page.route(f"**/api/capture/sessions/{active_id}/cancel-processing", request_active_cancel)
            page.evaluate("loadCaptureSessions()")
            active_job = page.locator("#captureJobs .row").filter(has_text=active_title)
            active_job.get_by_role("button", name="Cancelar procesamiento").click()
            active_job.get_by_role("button", name="Cancelando").wait_for()
            all_ok &= check("active_cancel_shows_cancelando", active_job.get_by_role("button", name="Cancelando").is_disabled())
            mock_state["value"] = "CANCELLED"
            page.evaluate("loadCaptureSessions()")
            active_job.get_by_role("button", name="Procesar de nuevo").wait_for()
            all_ok &= check("active_cancel_reaches_cancelled", "CANCELLED" in active_job.inner_text())
            completed_actions = page.evaluate("""() => {
                renderCaptureJobs([{sessionId:'completed-check', title:'Completed check', status:'FINALIZED', chunks:[{state:'PROCESSED'}]}]);
                return document.querySelector('#captureJobs').innerText;
            }""")
            all_ok &= check("completed_job_has_no_cancel_action", "COMPLETED" in completed_actions and "Cancelar" not in completed_actions)
            filtered = page.evaluate("""() => {
                renderCaptureJobs([
                    {sessionId:'test-marked', title:'Visible only to maintainers', isTestSession:true, chunks:[{state:'FINALIZED'}]},
                    {sessionId:'test-named', title:'synthetic fixture', chunks:[{state:'FAILED'}]},
                ]);
                return document.querySelector('#captureJobs').innerText;
            }""")
            all_ok &= check("test_sessions_hidden", filtered == "")
            all_ok &= check("no_browser_errors", not errors, "; ".join(errors))
        finally:
            page.close()
            context.close()
            browser.close()
    Path("capture_cancellation_report.json").write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
