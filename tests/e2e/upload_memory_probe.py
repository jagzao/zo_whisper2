from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("ZMI_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
CONTAINER = os.environ.get("ZMI_CONTAINER", "whisper-zmi-docker-zmi-1")
REPORT = Path("upload_memory_probe_report.json")


def memory_mb() -> float:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", CONTAINER],
        check=True, capture_output=True, text=True,
    )
    match = re.search(r"([\d.]+)(MiB|GiB)", result.stdout)
    if not match:
        raise RuntimeError(f"Cannot parse Docker memory: {result.stdout}")
    value = float(match.group(1))
    return value * (1024 if match.group(2) == "GiB" else 1)


def create_wav(path: Path, megabytes: int = 24) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        frames = megabytes * 1024 * 1024 // 2
        block = bytes(256 * 1024)
        while frames:
            count = min(frames, len(block) // 2)
            output.writeframesraw(block[:count * 2])
            frames -= count


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="whisper-synthetic-upload-") as temp:
        fixture_dir = Path(temp)
        fixtures = []
        for index in range(6):
            path = fixture_dir / f"zmi_memprobe_{index}.wav"
            create_wav(path)
            fixtures.append(path)

        baseline = memory_mb()
        peak = [baseline]
        stop = threading.Event()

        def sample_memory() -> None:
            while not stop.wait(0.5):
                try:
                    peak[0] = max(peak[0], memory_mb())
                except Exception:
                    pass

        monitor = threading.Thread(target=sample_memory, daemon=True)
        monitor.start()
        results = []
        uploaded_names = []
        upload_responses = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("response", lambda response: upload_responses.append(response.json())
                    if "/api/upload" in response.url and response.ok else None)
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.locator("#uploadProject").select_option(label="Zo Interviews")
            page.locator("#fileInput").set_input_files([str(path) for path in fixtures])
            if page.locator("#uploadQueue [data-upload-id]").count() != 6:
                raise AssertionError("Six synthetic files were not queued")
            page.locator("#startUploadBatch").click()
            page.wait_for_function("""() => [...document.querySelectorAll('[data-upload-id]')].length === 6 &&
              [...document.querySelectorAll('[data-upload-id]')].every(row => row.innerText.includes('OK '))""", timeout=120000)
            for path in fixtures:
                row = page.locator("[data-upload-id]").filter(has_text=path.name)
                if row.count() != 1 or "OK " not in row.inner_text():
                    results.append({"file": path.name, "status": "FAIL"})
                else:
                    results.append({"file": path.name, "status": "PASS"})
            uploaded_names = [item["name"] for item in upload_responses if item.get("name")]
            token = page.evaluate("DASHBOARD_TOKEN")
            for name in uploaded_names:
                response = page.evaluate("""async ([name, token]) => fetch('/api/file?id=' + encodeURIComponent('video_compress:' + name), {
                  method: 'DELETE', headers: {'X-Local-Dashboard-Token': token}
                }).then(r => r.json())""", [name, token])
                if not response.get("ok"):
                    results.append({"cleanup": name, "status": "FAIL", "detail": response})
            browser.close()
        stop.set()
        monitor.join(timeout=3)
        peak[0] = max(peak[0], memory_mb())
        report = {
            "fixture_megabytes_each": 24,
            "simultaneous_files": 6,
            "baseline_mib": round(baseline, 1),
            "peak_mib": round(peak[0], 1),
            "delta_mib": round(peak[0] - baseline, 1),
            "memory_bound_mib": 300,
            "results": results,
        }
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if len(uploaded_names) == 6 and peak[0] - baseline <= 300 and all(r["status"] == "PASS" for r in results if "status" in r) else 1


if __name__ == "__main__":
    raise SystemExit(main())
