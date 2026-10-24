from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


DESKTOP_URL = os.environ.get("ZMI_DESKTOP_URL", "http://127.0.0.1:5000").rstrip("/")
LAN_URL = os.environ.get("ZMI_LAN_URL", "https://127.0.0.1:5001").rstrip("/")
CHUNK_SIZE = 8 * 1024 * 1024
REPORT: list[dict[str, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    REPORT.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")


def expected_revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def make_video(path: Path, seconds: int, bitrate: str = "16M") -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=24", "-t", str(seconds), "-an", "-c:v", "libx264",
        "-preset", "ultrafast", "-b:v", bitrate, "-minrate", bitrate, "-maxrate", bitrate,
        "-bufsize", "32M", "-movflags", "+faststart", str(path),
    ], check=True)


def sessions(base: str) -> list[dict]:
    response = requests.get(f"{base}/api/uploads", timeout=20)
    response.raise_for_status()
    return response.json().get("sessions", [])


def wait_for_session(base: str, filename: str, timeout: int = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = next((item for item in sessions(base) if item.get("filename") == filename), None)
        if found:
            return found
        time.sleep(0.2)
    raise TimeoutError(f"No upload session appeared for {filename}")


def wait_for_completed(page, filename: str, timeout: int = 90) -> None:
    row = page.locator("#uploadQueue [data-upload-id]").filter(has_text=filename)
    page.wait_for_function("name => [...document.querySelectorAll('#uploadQueue [data-upload-id]')].some(row => row.innerText.includes(name) && row.innerText.includes('Completed'))", arg=filename, timeout=timeout * 1000)


def inspect_identity(playwright, url: str, revision: str) -> None:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(ignore_https_errors=True, service_workers="block")
    page = context.new_page()
    responses = []
    page.on("response", lambda response: responses.append(response))
    try:
        root = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#filesList", timeout=30000)
        header = root.headers.get("x-whisper-build", "") if root else ""
        meta = page.locator('meta[name="whisper-build"]').get_attribute("content") or ""
        build = page.locator("#buildVersion").inner_text()
        check(f"{url}_build_identity", header == revision == meta and revision[:12] in build, f"header={header}; meta={meta}; badge={build}; expected={revision}")
        check(f"{url}_html_cache_identity", root is not None and "no-store" in root.headers.get("cache-control", ""), root.headers.get("cache-control", "") if root else "no response")
        source = page.locator('script[src*="upload_reliability.js"]').get_attribute("src") or ""
        check(f"{url}_static_build_query", f"v={revision}" in source, source)
        page.wait_for_function("document.getElementById('metric-videos') && document.getElementById('metric-audio') && document.getElementById('metric-transcribed')")
        ui_metrics = page.evaluate("""() => ({videos:Number(document.getElementById('metric-videos').textContent), audio:Number(document.getElementById('metric-audio').textContent), transcribed:Number(document.getElementById('metric-transcribed').textContent)})""")
        api_metrics = requests.get(f"{url}/api/files", timeout=30).json().get("metrics", {})
        check(f"{url}_logical_counters_match_api", all(ui_metrics.get(key) == api_metrics.get(key) for key in ("videos", "audio", "transcribed")), f"ui={ui_metrics}; api={api_metrics}")
        helper = next((response for response in responses if "upload_reliability.js" in response.url), None)
        check(f"{url}_static_cache_identity", bool(helper and f"v={revision}" in helper.url and "no-store" in helper.headers.get("cache-control", "")), helper.url + " " + (helper.headers.get("cache-control", "") if helper else "missing helper response"))
        registrations = page.evaluate("async () => navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0")
        check(f"{url}_no_service_worker", registrations == 0, f"registrations={registrations}")
    finally:
        context.close()
        browser.close()


def main() -> int:
    revision = expected_revision()
    test_id = uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix="zmi-upload-ui-") as temp:
        root = Path(temp)
        resume_file = root / f"safe-resume-{test_id}.mp4"
        second_file = root / f"safe-two-a-{test_id}.mp4"
        third_file = root / f"safe-two-b-{test_id}.mp4"
        make_video(resume_file, 30)
        make_video(second_file, 2, "2M")
        make_video(third_file, 2, "2M")
        check("resume_fixture_crosses_chunk_boundary", resume_file.stat().st_size > CHUNK_SIZE, f"bytes={resume_file.stat().st_size}")
        uploaded_names = [resume_file.name, second_file.name, third_file.name]
        session_ids: set[str] = set()
        job_ids: set[str] = set()
        browser = None
        context = None
        page = None
        cleanup_token = ""
        playwright = sync_playwright().start()
        try:
            inspect_identity(playwright, DESKTOP_URL, revision)
            inspect_identity(playwright, LAN_URL, revision)
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True, service_workers="block")
            page = context.new_page()
            errors: list[str] = []
            upload_requests: list[str] = []
            finalize_responses: list[dict] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: upload_requests.append(request.url) if "/api/uploads" in request.url else None)
            page.on("response", lambda response: finalize_responses.append(response.json()) if response.url.endswith("/finalize") and response.ok else None)
            page.add_init_script("""(() => {
                  window.__zmiUploadMode = 'fail';
                  const nativeFetch = window.fetch.bind(window);
                  window.fetch = (input, init = {}) => {
                    const url = String(input);
                    const mode = window.__zmiUploadMode;
                    if (url.includes('/api/uploads/') && url.endsWith('/chunks/1') && mode === 'fail') {
                      window.__zmiChunkOneFailures = (window.__zmiChunkOneFailures || 0) + 1;
                      return Promise.reject(new TypeError('Synthetic interruption after first ACK'));
                    }
                    if (url.includes('/api/uploads/') && url.endsWith('/chunks/1') && mode === 'hold') {
                      window.__zmiChunkOneBlocked = true;
                      return new Promise((resolve, reject) => {
                        const signal = init.signal;
                        if (signal?.aborted) return reject(new DOMException('aborted', 'AbortError'));
                        signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), {once:true});
                      });
                    }
                    return nativeFetch(input, init);
                  };
                })();""")
            page.goto(DESKTOP_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#filesList", timeout=30000)
            cleanup_token = page.evaluate("typeof DASHBOARD_TOKEN === 'string' ? DASHBOARD_TOKEN : ''")
            page.wait_for_function("[...document.querySelector('#uploadProject').options].some(option => option.value.toLowerCase() === 'p&g')", timeout=20000)
            project = page.locator("#uploadProject").input_value()
            check("pg_default_project", project.lower() == "p&g", project)

            page.locator("#fileInput").set_input_files(str(resume_file))
            first = wait_for_session(DESKTOP_URL, resume_file.name)
            session_ids.add(first["id"])
            check("new_file_autostarts_with_session", first.get("state") == "UPLOADING", f"session={first['id']} state={first.get('state')}")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                first = next(item for item in sessions(DESKTOP_URL) if item["id"] == first["id"])
                if 0 in first.get("received", []):
                    break
                time.sleep(0.2)
            check("first_chunk_ack_observed", 0 in first.get("received", []), f"received={first.get('received')}")
            check("bytes_acknowledged", first.get("size", 0) > 0 and first.get("last_ack_at") is not None, f"size={first.get('size')}; ack={first.get('last_ack_at')}")
            page.wait_for_function("name => [...document.querySelectorAll('#uploadQueue [data-upload-id]')].some(row => row.innerText.includes(name) && row.innerText.includes('Failed'))", arg=resume_file.name, timeout=60000)
            failed = next(item for item in sessions(DESKTOP_URL) if item["id"] == first["id"])
            check("failed_upload_keeps_acked_chunk", failed.get("received") == [0], f"received={failed.get('received')}")

            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#uploadQueue [data-upload-id]", timeout=20000)
            page.evaluate("window.__zmiUploadMode = 'hold'")
            page.locator("#fileInput").set_input_files(str(resume_file))
            page.wait_for_function("window.__zmiChunkOneBlocked === true", timeout=30000)
            resumed_row = page.locator("#uploadQueue [data-upload-id]").filter(has_text=resume_file.name)
            page.wait_for_function("name => { const row=[...document.querySelectorAll('#uploadQueue [data-upload-id]')].find(item=>item.innerText.includes(name)); return row && row.innerText.includes('8.0 MB /'); }", arg=resume_file.name, timeout=15000)
            check("upload_reselect_failed", "8.0 MB /" in resumed_row.inner_text(), resumed_row.inner_text())
            resumed = next(item for item in sessions(DESKTOP_URL) if item["id"] == first["id"])
            check("reselect_reuses_session_and_ack", resumed["id"] == first["id"] and resumed.get("received") == [0], f"id={resumed['id']}; received={resumed.get('received')}")
            page.locator("#uploadQueue [data-upload-id]").filter(has_text=resume_file.name).get_by_role("button", name="Pause").click()
            page.wait_for_function("name => [...document.querySelectorAll('#uploadQueue [data-upload-id]')].some(row => row.innerText.includes(name) && row.innerText.includes('PAUSED'))", arg=resume_file.name, timeout=15000)
            paused = next(item for item in sessions(DESKTOP_URL) if item["id"] == first["id"])
            check("pause_preserves_ack_map", paused.get("received") == [0], f"received={paused.get('received')}")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#uploadQueue [data-upload-id]", timeout=20000)
            page.evaluate("window.__zmiUploadMode = 'off'")
            page.locator("#fileInput").set_input_files(str(resume_file))
            wait_for_completed(page, resume_file.name)
            completed = next(item for item in sessions(DESKTOP_URL) if item["id"] == first["id"])
            check("upload_reselect_paused", completed.get("logical_state") == "COMPLETED", f"state={completed.get('logical_state')} acked={len(completed.get('received', []))}")

            page.locator("#fileInput").set_input_files([str(second_file), str(third_file)])
            for path in (second_file, third_file):
                wait_for_completed(page, path.name)
            both = [item for item in sessions(DESKTOP_URL) if item.get("filename") in {second_file.name, third_file.name}]
            session_ids.update(item["id"] for item in both)
            check("two_files_auto_start_and_complete", len(both) == 2 and all(item.get("logical_state") == "COMPLETED" for item in both), json.dumps([{key: item.get(key) for key in ("filename", "id", "logical_state", "project_id")} for item in both]))
            check("served_upload_network_activity", any("/api/uploads/preflight" in url for url in upload_requests) and any("/chunks/0" in url for url in upload_requests), f"requests={len(upload_requests)}")
            check("all_uploads_keep_pg", all(item.get("project_id") == project for item in [completed, *both]), json.dumps([item.get("project_id") for item in [completed, *both]]))
            check("browser_has_no_js_errors", not errors, " | ".join(errors))
            check("finalize_requests_succeeded", len(finalize_responses) >= 3, f"successful finalize responses={len(finalize_responses)}")
            job_ids.update(str(item["job_id"]) for item in finalize_responses if item.get("job_id"))
        except Exception as error:
            try:
                queue = page.locator("#uploadQueue").inner_text(timeout=2000) if page and not page.is_closed() else "unavailable"
            except Exception:
                queue = "unavailable"
            recent = upload_requests[-12:] if "upload_requests" in locals() else []
            check("served_browser_upload_flow", False, f"{type(error).__name__}: {error}; queue={queue}; requests={json.dumps(recent)}")
        finally:
            headers = {"X-Local-Dashboard-Token": cleanup_token, "Origin": DESKTOP_URL} if cleanup_token else {}
            if cleanup_token:
                try:
                    session_ids.update(item["id"] for item in sessions(DESKTOP_URL) if item.get("filename") in uploaded_names)
                except requests.RequestException:
                    pass
                for job_id in job_ids:
                    try:
                        requests.post(f"{DESKTOP_URL}/api/worker/jobs/{job_id}/cancel", headers=headers, timeout=10)
                    except requests.RequestException:
                        pass
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        files = requests.get(f"{DESKTOP_URL}/api/files", timeout=20).json().get("files", [])
                        targets = [item for item in files if any(name in str(item.get("name", "")) for name in uploaded_names)]
                        if not targets:
                            break
                        for item in targets:
                            if item.get("delete_allowed"):
                                requests.delete(f"{DESKTOP_URL}/api/file", params={"id": item["media_id"]}, headers=headers, timeout=20)
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                for session_id in session_ids:
                    try:
                        requests.delete(f"{DESKTOP_URL}/api/uploads/{session_id}", headers=headers, timeout=10)
                    except requests.RequestException:
                        pass
                try:
                    remaining = [item for item in requests.get(f"{DESKTOP_URL}/api/files", timeout=20).json().get("files", [])
                                 if any(name in str(item.get("name", "")) for name in uploaded_names)]
                    check("test_media_cleanup", not remaining, json.dumps([item.get("name") for item in remaining]))
                    remaining_sessions = [item for item in sessions(DESKTOP_URL) if item.get("filename") in uploaded_names]
                    check("test_upload_session_cleanup", not remaining_sessions, json.dumps([item.get("filename") for item in remaining_sessions]))
                except requests.RequestException as error:
                    check("test_artifact_cleanup", False, str(error))
            if context:
                context.close()
            if browser:
                browser.close()
            playwright.stop()
    output = Path(os.environ.get("UPLOAD_UI_REPORT", "resumable_upload_ui_report.json"))
    output.write_text(json.dumps({"revision": revision, "checks": REPORT}, indent=2), encoding="utf-8")
    failures = [item for item in REPORT if item["status"] != "PASS"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
