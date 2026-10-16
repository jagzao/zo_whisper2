from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


DESKTOP_URL = os.environ.get("ZMI_DESKTOP_URL", "http://127.0.0.1:5000").rstrip("/")
MOBILE_URL = os.environ.get("ZMI_MOBILE_URL", "https://127.0.0.1:5001").rstrip("/")
REPORT: list[dict] = []
SCRIPT_HASHES: list[str] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    REPORT.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
    print(f"[{REPORT[-1]['status']}] {name}: {detail}")


def expected_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def exercise_url(playwright, url: str, mobile: bool, revision: str) -> bool:
    before = len(REPORT)
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 390 if mobile else 1440, "height": 844 if mobile else 1000},
        is_mobile=mobile,
        has_touch=mobile,
        ignore_https_errors=True,
        service_workers="block",
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.add_init_script(r"""
      const nativeFetch = window.fetch.bind(window);
      window.__uploadHarness = {active:0,maxActive:0,attempts:{},requests:[]};
      window.fetch = (input, init = {}) => {
        if (!String(input).includes('/api/upload')) return nativeFetch(input, init);
        const body = init.body;
        const file = body.get('file');
        const projectId = body.get('project_id') || '';
        const harness = window.__uploadHarness;
        const count = harness.attempts[file.name] = (harness.attempts[file.name] || 0) + 1;
        harness.requests.push({name:file.name, projectId});
        harness.active += 1;
        harness.maxActive = Math.max(harness.maxActive, harness.active);
        let finished = false;
        const finish = () => { if (!finished) { finished = true; harness.active -= 1; } };
        if (file.name === 'fail-first.mp4' && count === 1) {
          finish();
          return Promise.resolve(new Response(JSON.stringify({ok:false,error:'synthetic rejection'}), {status:400,headers:{'Content-Type':'application/json'}}));
        }
        if (file.name === 'cancel-first.wav' && count === 1) {
          return new Promise((resolve,reject) => {
            init.signal.addEventListener('abort', () => { finish(); reject(new DOMException('aborted','AbortError')); }, {once:true});
          });
        }
        return new Promise(resolve => setTimeout(() => {
          finish();
          resolve(new Response(JSON.stringify({ok:true,name:file.name,project_id:projectId}), {status:200,headers:{'Content-Type':'application/json'}}));
        }, 180));
      };
    """)
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#filesList", timeout=20000)
        revision_header = response.headers.get("x-whisper-build", "")
        revision_meta = page.locator('meta[name="whisper-build"]').get_attribute("content") or ""
        build_label = page.locator("#buildVersion").inner_text()
        no_store = "no-store" in response.headers.get("cache-control", "")
        check(f"{url}_revision_matches_head", revision_header == revision == revision_meta, f"header={revision_header} meta={revision_meta} head={revision}")
        check(f"{url}_visible_build_marker", revision[:12] in build_label, build_label)
        check(f"{url}_html_no_store", no_store, response.headers.get("cache-control", ""))
        viewport_safe = page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        check(f"{url}_layout_matches_viewport", viewport_safe)
        registrations = page.evaluate("async () => navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0")
        check(f"{url}_no_stale_service_worker", registrations == 0, f"registrations={registrations}")
        script_text = "\n".join(page.locator("script").evaluate_all("els => els.map(el => el.textContent || '')"))
        script_text = re.sub(r"const DASHBOARD_TOKEN = .*?;", "const DASHBOARD_TOKEN = BUILD_TOKEN;", script_text, count=1)
        SCRIPT_HASHES.append(hashlib.sha256(script_text.encode("utf-8")).hexdigest())

        page.locator("#newRecordingBtn").click()
        page.locator("#captureProject").wait_for(state="visible")
        project = page.locator("#captureProject option").nth(1)
        project_name = project.get_attribute("value")
        if project_name:
            page.locator("#captureProject").select_option(project_name)
        check(f"{url}_capture_project_selector", bool(project_name), str(project_name))
        project_before_title = page.locator("#captureProject").evaluate("el => el.getBoundingClientRect().top < document.querySelector('#captureTitle').getBoundingClientRect().top")
        check(f"{url}_project_precedes_title", project_before_title)
        page.locator("#captureModal .capture-modal").evaluate("el => el.classList.add('hidden')")

        page.locator("#uploadProject").select_option(label=project.inner_text())
        is_multiple = page.locator("#fileInput").evaluate("el => el.multiple")
        check(f"{url}_upload_input_multiple", is_multiple)
        files = [
            {"name": "ok-one.mp4", "mimeType": "video/mp4", "buffer": b"synthetic"},
            {"name": "fail-first.mp4", "mimeType": "video/mp4", "buffer": b"synthetic"},
            {"name": "cancel-first.wav", "mimeType": "audio/wav", "buffer": b"synthetic"},
            {"name": "remove-before-upload.mp3", "mimeType": "audio/mpeg", "buffer": b"synthetic"},
        ]
        page.locator("#fileInput").set_input_files(files)
        selected_names = page.locator("#uploadQueue .upload-file-name").all_inner_texts()
        check(f"{url}_four_files_visible_before_upload", len(selected_names) == 4 and all(f["name"] in " ".join(selected_names) for f in files), " | ".join(selected_names))
        remove_row = page.locator('[data-upload-id]').filter(has_text="remove-before-upload.mp3")
        remove_row.get_by_role("button", name="Remove").click()
        check(f"{url}_remove_single_queued_file", page.locator("#uploadQueue").inner_text().count("remove-before-upload.mp3") == 0)
        page.locator("#dropzone").evaluate("el => { const data = new DataTransfer(); data.items.add(new File(['a'], 'drop-a.mp4', {type:'video/mp4'})); data.items.add(new File(['b'], 'drop-b.mp3', {type:'audio/mpeg'})); el.dispatchEvent(new DragEvent('drop', {bubbles:true,cancelable:true,dataTransfer:data})); }")
        dropped_names = page.locator("#uploadQueue .upload-file-name").all_inner_texts()
        check(f"{url}_multiple_drag_drop", any("drop-a.mp4" in name for name in dropped_names) and any("drop-b.mp3" in name for name in dropped_names))
        for name in ("drop-a.mp4", "drop-b.mp3"):
            page.locator('[data-upload-id]').filter(has_text=name).get_by_role("button", name="Remove").click()
        page.locator("#startUploadBatch").click()

        fail_row = page.locator('[data-upload-id]').filter(has_text="fail-first.mp4")
        fail_row.get_by_role("button", name="Retry").wait_for(timeout=10000)
        cancel_row = page.locator('[data-upload-id]').filter(has_text="cancel-first.wav")
        cancel_row.get_by_role("button", name="Cancelar subida").wait_for(timeout=10000)
        cancel_row.get_by_role("button", name="Cancelar subida").click()
        cancel_row.get_by_role("button", name="Retry").wait_for(timeout=5000)
        check(f"{url}_per_file_cancel_and_retry_available", True)
        fail_row.get_by_role("button", name="Retry").click()
        cancel_row.get_by_role("button", name="Retry").click()
        page.wait_for_function("""() => ['ok-one.mp4','fail-first.mp4','cancel-first.wav'].every(name => {
          const row = [...document.querySelectorAll('[data-upload-id]')].find(el => el.innerText.includes(name));
          return row && row.innerText.includes('OK ');
        })""", timeout=15000)
        check(f"{url}_upload_concurrency_bounded", page.evaluate("window.__uploadHarness.maxActive") == 2, f"maxActive={page.evaluate('window.__uploadHarness.maxActive')}")
        requests = page.evaluate("window.__uploadHarness.requests")
        carries_project = bool(project_name) and all(row["projectId"] == project_name for row in requests)
        check(f"{url}_each_file_keeps_selected_project", carries_project, json.dumps(requests))
        check(f"{url}_one_file_failure_does_not_block_batch", page.locator('[data-upload-id]').filter(has_text="ok-one.mp4").inner_text().find("Uploaded") >= 0 and page.locator('[data-upload-id]').filter(has_text="fail-first.mp4").inner_text().find("Uploaded") >= 0, page.locator("#uploadQueue").inner_text())
        videos_text = page.locator("#filesList").inner_text()
        check(f"{url}_no_raw_chunk_rows", "chunk-000000" not in videos_text and "fragment-000001" not in videos_text)
        check(f"{url}_no_browser_errors", not errors, " | ".join(errors))
    except Exception as exc:
        check(f"{url}_journey_exception", False, str(exc))
    finally:
        context.close()
        browser.close()
    return all(row["status"] == "PASS" for row in REPORT[before:])


def main() -> int:
    revision = expected_revision()
    with sync_playwright() as playwright:
        desktop_pass = exercise_url(playwright, DESKTOP_URL, False, revision)
        mobile_pass = exercise_url(playwright, MOBILE_URL, True, revision)
    matching_scripts = len(SCRIPT_HASHES) == 2 and SCRIPT_HASHES[0] == SCRIPT_HASHES[1]
    check("desktop_mobile_inline_js_matches", matching_scripts, str(SCRIPT_HASHES))
    report_path = Path(os.environ.get("CAPTURE_MULTIFILE_REPORT", "capture_multifile_upload_report.json"))
    report_path.write_text(json.dumps({"checks": REPORT}, indent=2), encoding="utf-8")
    print(f"Report saved: {report_path}")
    return 0 if desktop_pass and mobile_pass and matching_scripts else 1


if __name__ == "__main__":
    sys.exit(main())
