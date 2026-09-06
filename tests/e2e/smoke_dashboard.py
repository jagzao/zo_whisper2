"""Dashboard smoke test using Playwright.

Verifies functionality and captures screenshots of each key section.
Generates a JSON report with passed/failed checks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

DASHBOARD_URL = "http://127.0.0.1:5000"
TIMEOUT_MS = 30000
SCREENSHOTS: list[str] = []
REPORT: list[dict] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    REPORT.append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")
    return condition


def screenshot(page, name: str) -> str:
    path = f"dashboard_{name}.png"
    page.screenshot(path=path, full_page=False)
    SCREENSHOTS.append(path)
    print(f"Screenshot: {path}")
    return path


def fetch_files() -> list[dict]:
    r = requests.get(f"{DASHBOARD_URL}/api/files", timeout=10)
    r.raise_for_status()
    return r.json().get("files", [])


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return 1

    files = fetch_files()
    target = next(
        (f for f in files if f.get("transcription") and f["transcription"].get("id")),
        None,
    )
    if not target:
        print("No files with a transcription available to test the modal")
        return 1

    print(f"Test file: {target['name']}")
    all_ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        # Registered globally, from the very start: an unhandled native
        # confirm()/alert() dialog blocks the renderer indefinitely (no
        # timeout fires) rather than raising — confirmed the hard way when a
        # narrower, conditionally-registered handler still let one run
        # through and hung the whole suite for the full outer 300s timeout.
        dialogs_seen: list[str] = []

        def _auto_accept_dialog(dialog):
            dialogs_seen.append(dialog.message)
            dialog.accept()

        page.on("dialog", _auto_accept_dialog)
        page.on("console", lambda msg: print(f"[CONSOLE {msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda exc: print(f"[PAGEERROR] {exc}"))

        page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
        page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)

        # Home
        screenshot(page, "home")
        rows = page.locator("#filesList table tbody tr").count()
        all_ok &= check("files_table", rows > 0 and rows <= 5, f"{rows} rows (page 1)")
        all_ok &= check("dropzone_visible", page.locator("#dropzone").is_visible())
        all_ok &= check("folders_visible", page.locator("#folders .folder").count() == 4)
        all_ok &= check(
            "pagination_visible",
            page.locator("#filesPaginationTop button").count() > 0
            or page.locator("#filesPagination button").count() > 0,
        )

        # Operational metrics + pipeline stepper (US-001 §3.3/§3.4)
        all_ok &= check("metrics_visible", page.locator("#metrics .metric").count() == 4)
        all_ok &= check(
            "pipeline_stepper_visible", page.locator("#pipelineStepper .pipeline-stage").count() == 8
        )
        # Backend status strings must render as human-readable labels, not raw
        # (e.g. "completed_routed").
        status_texts = page.locator("#filesList table tbody tr td:nth-child(6) .status").all_inner_texts()
        all_ok &= check(
            "status_labels_human_readable",
            all("_" not in t for t in status_texts),
            f"{status_texts}",
        )

        # Filter by the test file's own project (avoids hardcoding a project name)
        project_name = target.get("project")
        if project_name:
            page.locator("#projectFilter").select_option(project_name)
            page.wait_for_timeout(400)
            filtered_rows = page.locator("#filesList table tbody tr").count()
            all_ok &= check("project_filter", filtered_rows > 0 and filtered_rows <= 5, f"{filtered_rows} rows")

        # Sort by name desc
        page.locator('th[data-sort="name"]').click()
        page.wait_for_timeout(300)
        page.locator('th[data-sort="name"]').click()
        page.wait_for_timeout(300)
        icon_text = page.locator('th[data-sort="name"] .sort-icon').text_content() or ""
        is_desc = icon_text not in ("", "?", "?")
        detail = "desc icon" if is_desc else f"icon={icon_text.encode('ascii','replace').decode()}"
        all_ok &= check("sort_name_desc", is_desc, detail)

        # Clear filters
        page.locator("#projectFilter").select_option("")
        page.wait_for_timeout(400)
        rows_after = page.locator("#filesList table tbody tr").count()
        all_ok &= check("clear_filter", rows_after > 0, f"{rows_after} rows")

        # Header buttons
        for label in ("Projects", "Logs", "Help"):
            all_ok &= check(
                f"header_{label}", page.locator(f'button[aria-label="{label}"]').count() == 1
            )

        # Preview modal
        row = page.locator(f"#filesList table tbody tr:has-text('{target['name']}')")
        ver_button = row.locator("button[aria-label='View']")
        edit_button = row.locator("button[aria-label='Edit']")
        all_ok &= check("view_btn_enabled", ver_button.is_enabled())
        all_ok &= check("edit_btn_enabled", edit_button.is_enabled())

        ver_button.click()
        page.wait_for_selector("#previewModal:not(.hidden)", timeout=TIMEOUT_MS)
        page.wait_for_timeout(1000)
        all_ok &= check("player_present", page.locator("#editorMedia").count() > 0)
        tx_text = page.locator("#transcriptList").inner_text(timeout=5000)
        all_ok &= check(
            "transcription_loaded", len(tx_text) > 100, f"{len(tx_text)} chars"
        )
        screenshot(page, "preview")

        # Search + highlight (use a real word from the transcription)
        tx_text = page.locator("#transcriptList").inner_text(timeout=5000)
        search_word = next((w for w in tx_text.split() if len(w) >= 5 and w.isalpha()), "the")
        page.locator("#txSearch").fill(search_word)
        page.wait_for_timeout(600)
        marks = page.locator("#transcriptList .segment mark").count()
        count_text = page.locator("#searchCount").text_content() or ""
        all_ok &= check(
            "search_highlight", marks > 0, f"'{search_word}' -> {marks} marks, {count_text}"
        )
        screenshot(page, "editor")

        # Timestamp/evidence navigation (US-001 §11.3 #8): clicking a
        # transcript segment must seek the player to that segment's start.
        # search_highlight (above) left #txSearch filled — filterSegments()
        # hides (display:none) every non-matching segment, so clear it first
        # or "2 segments available" below would really mean "2 still visible".
        page.locator("#txSearch").fill("")
        page.wait_for_timeout(300)

        segments = page.locator("#transcriptList .segment:visible")
        if segments.count() >= 2:
            target_segment = segments.nth(1)
            expected_start = float(target_segment.get_attribute("data-start"))
            target_segment.click()
            page.wait_for_timeout(300)
            actual_time = page.eval_on_selector("#editorMedia", "el => el.currentTime")
            media_duration = page.eval_on_selector("#editorMedia", "el => el.duration") or 0
            # The mock fixture's real audio file is a few seconds of silence
            # regardless of the (much longer) duration its fake metadata
            # claims — a browser clamps any seek beyond the real file length
            # to that real duration, so a segment starting past it lands at
            # ~media_duration, not at its nominal `data-start`. Both outcomes
            # prove seekTo() actually drove the player; only an unchanged/
            # zero currentTime would indicate navigation didn't work.
            near_expected = abs(actual_time - expected_start) < 1.0
            clamped_to_real_duration = media_duration > 0 and abs(actual_time - media_duration) < 1.0
            all_ok &= check(
                "timestamp_navigation_seeks_player",
                near_expected or clamped_to_real_duration,
                f"expected ~{expected_start}s, got {actual_time}s (media duration {media_duration}s)",
            )
        else:
            print("[SKIP] timestamp_navigation_seeks_player: fewer than 2 segments available")

        # Frames tab
        page.locator("#tabFrames").click()
        page.wait_for_timeout(1500)
        screenshot(page, "frames")
        all_ok &= check(
            "frames_tab_visible",
            page.locator("#framesGrid .frame-card").count() > 0
            or page.locator("#framesGrid").inner_text(timeout=2000) != "",
        )

        page.locator("#previewModal .close-x").click()
        page.wait_for_selector("#previewModal.hidden", state="hidden", timeout=TIMEOUT_MS)

        # Edit modal — kept right after this same file's preview modal closes
        # (rather than after the heavier Documentation-tab section below),
        # so it isn't affected by whatever browser-side load that section
        # accumulates (a second modal, its own media element, several
        # fetch/PATCH round-trips).
        edit_button.click()
        page.wait_for_selector("#editModal:not(.hidden)", timeout=TIMEOUT_MS)
        # editTranscription() shows a "Loading..." placeholder synchronously,
        # then fills the real text once its own async fetch resolves — wait
        # for that, rather than a fixed sleep that can flake under load.
        page.wait_for_function(
            "document.getElementById('editTxText').value !== 'Loading...'", timeout=TIMEOUT_MS
        )
        textarea = page.locator("#editTxText")
        tx_value = textarea.input_value()
        all_ok &= check(
            "edit_loaded", len(tx_value.strip()) > 10, f"{len(tx_value)} chars"
        )
        screenshot(page, "edit")
        page.locator("#editModal .close-x").click()
        page.wait_for_selector("#editModal.hidden", state="hidden", timeout=TIMEOUT_MS)

        # Documentation tab (US-001 §3.6/§4.6) — only meaningful for a file
        # the video-to-documentation engine actually ran on (the mock data's
        # "tutorial" fixture, via generate_mock_data.py's
        # make_tutorial_documentation()). Skips cleanly if that fixture
        # wasn't generated in this environment, rather than failing the
        # whole smoke run over an optional fixture.
        tutorial_doc = next((f for f in files if (f.get("documentation") or {}).get("has_manual")), None)
        if tutorial_doc:
            tx = tutorial_doc.get("transcription") or {}
            page.evaluate(
                "([mid, tid]) => preview(encodeURIComponent(mid), tid ? encodeURIComponent(tid) : '', false)",
                [tutorial_doc["media_id"], tx.get("id", "")],
            )
            page.wait_for_selector("#previewModal:not(.hidden)", timeout=TIMEOUT_MS)
            page.wait_for_timeout(500)
            page.locator("#tabDocs").click()
            page.wait_for_timeout(1000)
            docs_text = page.locator("#docsContent").inner_text(timeout=5000)
            all_ok &= check("docs_tab_renders_manual", len(docs_text) > 20, f"{len(docs_text)} chars")

            # AI package download access (§11.3 #10).
            download_links = page.locator("#docsContent .ai-package-link")
            all_ok &= check("ai_package_download_links_present", download_links.count() >= 2, f"{download_links.count()} links")

            # Human review edit persists without retranscribing (§11.3 #9, §4.8).
            # Checked entirely in-page (re-reads the DOM after the save's own
            # loadDocs() re-render) rather than a side HTTP call from this
            # script — the dev server is single-threaded and the preview
            # modal's <audio>/<video> element can be mid-stream at this point,
            # so a second, independent connection can queue for a long time.
            step_cards = page.locator(".doc-step")
            if step_cards.count() > 0:
                first_step = step_cards.first
                step_id = first_step.get_attribute("data-step-id")
                textarea = first_step.locator("textarea")
                textarea.fill("Reviewed and edited by the E2E smoke test.")
                first_step.locator("button:has-text('Save')").click()

                edit_persisted = False
                try:
                    # saveStepEdit() replaces just this one card's outerHTML
                    # from the PATCH response (no full-panel reload) — poll
                    # for that, and specifically for the `reviewed` badge,
                    # not just the textarea's value: the value alone is
                    # already true right after our own `.fill()`, before Save
                    # is even clicked, so checking it alone could resolve
                    # against pre-save DOM state without proving a server
                    # round-trip happened.
                    page.wait_for_function(
                        """(stepId) => {
                            const card = document.querySelector(`.doc-step[data-step-id="${stepId}"]`);
                            if (!card) return false;
                            const el = card.querySelector('textarea');
                            const reviewed = card.querySelector('.doc-step-header').innerText.includes('reviewed');
                            return el && el.value === 'Reviewed and edited by the E2E smoke test.' && reviewed;
                        }""",
                        arg=step_id,
                        timeout=TIMEOUT_MS,
                    )
                    edit_persisted = True
                except Exception as e:
                    print(f"[INFO] review_edit_persists poll did not resolve: {e}")

                reloaded_step = page.locator(f'.doc-step[data-step-id="{step_id}"]')
                new_value = reloaded_step.locator("textarea").input_value() if reloaded_step.count() else ""
                reviewed_badge = reloaded_step.locator(".doc-step-header:has-text(\"reviewed\")").count() if reloaded_step.count() else 0
                all_ok &= check(
                    "review_edit_persists",
                    edit_persisted and reviewed_badge > 0,
                    f"textarea after reload: {new_value!r}, reviewed badge count: {reviewed_badge}",
                )
            else:
                print("[SKIP] review_edit_persists: no editable steps rendered")

            screenshot(page, "docs")
            page.locator("#previewModal .close-x").click()
            page.wait_for_selector("#previewModal.hidden", state="hidden", timeout=TIMEOUT_MS)
        else:
            print("[SKIP] docs_tab_renders_manual: no file with generated documentation found")

        # Header modals
        for label, modal, item_selector in (
            ("Projects", "#projectsModal", ".project-item"),
            ("Logs", "#logsModal", ""),
            ("Help", "#helpModal", ""),
        ):
            page.locator(f'button[aria-label="{label}"]').click()
            page.wait_for_selector(f"{modal}:not(.hidden)", timeout=TIMEOUT_MS)
            if item_selector:
                count = page.locator(f"{modal} {item_selector}").count()
                all_ok &= check(f"{label.lower()}_modal_items", count > 0, f"{count} items")
            screenshot(page, label.lower())
            page.locator(f"{modal} .close-x").click()
            page.wait_for_selector(f"{modal}.hidden", state="hidden", timeout=TIMEOUT_MS)

        # Upload appears as a job (§11.3 #3). Uploads land in Video_compress/
        # (pending compression/routing) — NOT the Files→Transcriptions table,
        # which only lists already-organized Videos/audio — so "appears as a
        # job" is checked against the upload queue message and the
        # VIDEO_COMPRESS folder count the app itself uses for this signal.
        def fetch_folders() -> dict:
            # A bounded, exception-safe `requests` call — NOT page.evaluate()
            # with an async fetch(), which has no timeout parameter at all
            # in Playwright and hung this suite for the full 300s outer
            # ceiling at least once when a request genuinely stalled.
            try:
                data = requests.get(f"{DASHBOARD_URL}/api/folders", timeout=15).json()
                return {f["name"]: f["count"] for f in data["folders"]}
            except Exception as e:
                print(f"[INFO] fetch_folders failed: {e}")
                return {}

        folders_before = fetch_folders()
        # Manual temp dir (not tempfile.TemporaryDirectory()'s auto-cleanup,
        # which raises if the OS still has the file open) — Chromium can
        # hold its own handle on an uploaded file briefly after the
        # multipart POST completes; ignore_errors sidesteps that instead of
        # racing it.
        tmp = tempfile.mkdtemp(prefix="e2e_smoke_")
        try:
            upload_path = Path(tmp) / "e2e_smoke_upload.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(upload_path)],
                check=True, capture_output=True, timeout=30,
            )
            page.set_input_files("#fileInput", str(upload_path))
            try:
                page.wait_for_function(
                    "document.getElementById('uploadQueue').innerText.trim() !== ''", timeout=TIMEOUT_MS
                )
                queue_text = page.locator("#uploadQueue").inner_text(timeout=5000)
                all_ok &= check("upload_appears_as_job", "e2e_smoke_upload" in queue_text, queue_text[:200])
            except Exception as e:
                all_ok &= check("upload_appears_as_job", False, f"did not resolve: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        folders_after = fetch_folders()
        all_ok &= check(
            "upload_increments_pending_compress_count",
            folders_after.get("Video_compress", 0) > folders_before.get("Video_compress", 0),
            f"Video_compress: {folders_before.get('Video_compress')} -> {folders_after.get('Video_compress')}",
        )
        # Clean up the queued-but-not-yet-processed upload directly — no UI
        # affordance exists to remove a Video_compress-pending file (only
        # already-routed Videos/audio entries are deletable from the table).
        for f in Path("Video_compress").glob("*e2e_smoke_upload*"):
            f.unlink()

        # Delete requires confirmation and behaves safely (§11.3 #11) —
        # against a disposable file created directly in Videos/ so it's
        # immediately visible in the Files→Transcriptions table.
        delete_target = Path("Videos") / "e2e_smoke_delete_target.mp4"
        delete_target.unlink(missing_ok=True)  # defensive: stale leftover from a previous crashed run
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1", str(delete_target)],
            check=True, capture_output=True, timeout=30,
        )
        try:
            page.locator("#fileFilter").fill("e2e_smoke_delete_target")
            try:
                page.wait_for_function(
                    "document.querySelectorAll(\"#filesList table tbody tr\").length === 1", timeout=TIMEOUT_MS
                )
            except Exception as e:
                print(f"[INFO] delete_target row did not appear: {e}")
            deletable_row = page.locator("#filesList table tbody tr:has-text('e2e_smoke_delete_target')")
            all_ok &= check("delete_target_listed", deletable_row.count() == 1, f"{deletable_row.count()} rows")

            if deletable_row.count() == 1:
                dialogs_before = len(dialogs_seen)
                deletable_row.locator("button[aria-label='Delete']").click()
                try:
                    page.wait_for_function(
                        "document.querySelectorAll(\"#filesList table tbody tr\").length === 0"
                        " || !document.body.innerText.includes('e2e_smoke_delete_target')",
                        timeout=TIMEOUT_MS,
                    )
                except Exception as e:
                    print(f"[INFO] delete confirmation did not resolve: {e}")
                all_ok &= check("delete_shows_confirmation_dialog", len(dialogs_seen) > dialogs_before)
                remaining = page.locator("#filesList table tbody tr:has-text('e2e_smoke_delete_target')").count()
                all_ok &= check("delete_confirmed_removes_file", remaining == 0, f"{remaining} rows remain")
        finally:
            delete_target.unlink(missing_ok=True)  # in case the in-UI delete didn't complete
            page.locator("#fileFilter").fill("")
            page.wait_for_timeout(300)

        browser.close()

    # Report
    Path("dashboard_report.json").write_text(
        json.dumps({"checks": REPORT, "screenshots": SCREENSHOTS}, indent=2),
        encoding="utf-8",
    )
    print("\nReport saved: dashboard_report.json")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
