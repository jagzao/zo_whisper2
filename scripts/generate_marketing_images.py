"""Generates the three marketing PNGs for the community launch (Task D).

All data is synthetic (from docs/assets/generate_mock_data.py) — never real
client data. The dashboard is started locally, driven with Playwright, and
the three screenshots are written to docs/marketing/:

  hero-dashboard.png          — home: file list (filtered to a synthetic
                                project), metrics, pipeline stepper.
  pipeline-evidence.png       — the tutorial file's workspace, TRANSCRIPT tab:
                                timestamped segments + the player showing a
                                frame (transcript + timestamp + frame).
  generated-documentation.png — the tutorial file's DOCS tab: the generated
                                MANUAL.md rendered as steps with evidence
                                source badges + the AI package summary.

Run:
    python scripts/generate_marketing_images.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "marketing"
DASHBOARD_URL = "http://127.0.0.1:5000"
PYTHON = sys.executable
TIMEOUT_MS = 30000

# A name substring that only the mock-data generator's synthetic files match
# (the mock northwind files), so filtering the file list to it guarantees
# only synthetic rows appear — the mock files carry no project rule in
# projects.json, so the project filter can't be used to isolate them.
SYNTHETIC_FILTER = "northwind"


def _server_cmd() -> list[str]:
    return [PYTHON, str(ROOT / "dashboard.py")]


def _wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(DASHBOARD_URL, timeout=1.0) as _:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _drain_output(stream, sink: list[str]) -> None:
    """Continuously reads lines from `stream` into `sink` for the process's
    whole lifetime — without this the subprocess pipe fills and the server
    blocks (see scripts/e2e.py for the full rationale)."""
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
    except (ValueError, OSError):
        pass


def _ensure_mock_data() -> None:
    subprocess.run(
        [PYTHON, str(ROOT / "docs" / "assets" / "generate_mock_data.py")],
        cwd=str(ROOT), check=True, capture_output=True, text=True, timeout=300,
    )


def _find_tutorial_file(page) -> dict:
    """Returns the mock tutorial file dict (the one with generated docs)."""
    files = page.evaluate("() => window._allFiles")
    for f in files:
        if (f.get("documentation") or {}).get("has_manual"):
            return f
    raise RuntimeError("no file with generated documentation found")


def _open_workspace(page, file_info: dict, tab: str) -> None:
    tx = file_info.get("transcription") or {}
    page.evaluate(
        "([mid, tid]) => preview(encodeURIComponent(mid), tid ? encodeURIComponent(tid) : '', false)",
        [file_info["media_id"], tx.get("id", "")],
    )
    page.wait_for_selector("#previewModal:not(.hidden)", timeout=TIMEOUT_MS)
    page.wait_for_timeout(800)
    page.locator(f"#tab{tab}").click()
    page.wait_for_timeout(1200)


def _capture(page, name: str) -> Path:
    out = OUT_DIR / name
    page.screenshot(path=str(out), full_page=False)
    return out


def main() -> int:
    _ensure_mock_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")

    server = subprocess.Popen(
        _server_cmd(), cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    server_output: list[str] = []
    threading.Thread(target=_drain_output, args=(server.stdout, server_output), daemon=True).start()

    try:
        if not _wait_for_server():
            print("[FAIL] dashboard did not start", file=sys.stderr)
            return 1

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("dialog", lambda d: d.accept())
            page.goto(DASHBOARD_URL, timeout=TIMEOUT_MS)
            page.wait_for_selector("#filesList", timeout=TIMEOUT_MS)
            page.wait_for_timeout(1500)

            # ── hero-dashboard.png ────────────────────────────────────────
            # Filter the file list to a purely-synthetic name substring so no
            # real client rows appear; metrics/stepper are aggregate counts.
            page.locator("#fileFilter").fill(SYNTHETIC_FILTER)
            page.wait_for_timeout(800)
            hero = _capture(page, "hero-dashboard.png")
            print(f"[OK] {hero}")

            # ── pipeline-evidence.png ─────────────────────────────────────
            # Tutorial workspace, TRANSCRIPT tab: timestamped segments on the
            # left, the player showing a frame on the right. Seek the player
            # to the first segment so a real frame is visible.
            tutorial = _find_tutorial_file(page)
            _open_workspace(page, tutorial, "Transcript")
            page.locator("#transcriptList .segment").first.click()
            page.wait_for_timeout(1200)
            evidence = _capture(page, "pipeline-evidence.png")
            print(f"[OK] {evidence}")

            # ── generated-documentation.png ──────────────────────────────
            # DOCS tab: the generated MANUAL.md rendered as step cards with
            # evidence source badges + the AI package summary.
            page.locator("#tabDocs").click()
            page.wait_for_timeout(1500)
            page.wait_for_selector("#docsContent .doc-step", timeout=TIMEOUT_MS)
            page.wait_for_timeout(800)
            docs = _capture(page, "generated-documentation.png")
            print(f"[OK] {docs}")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()

    for name in ("hero-dashboard.png", "pipeline-evidence.png", "generated-documentation.png"):
        path = OUT_DIR / name
        size = path.stat().st_size if path.exists() else 0
        print(f"[SIZE] {name}: {size} bytes")
        if size < 50 * 1024:
            print(f"[WARN] {name} is smaller than 50KB", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())