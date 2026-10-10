"""Overnight batch: generate MANUAL + STUDY_GUIDE for every processed tutorial.

Polls CarpetaTranscripciones for frame_mapping.json files whose manual bundle
is missing, and regenerates documentation (idempotent). Runs ~22h max, logs to
stdout (visible via docker logs / docker attach).
"""
import time
import traceback
from collections import Counter
from pathlib import Path

from transcript_pipeline.documentation.engine import generate_documentation
from transcript_pipeline.projects import load_projects, match_project

DATA = Path("/data")
BASE = DATA / "CarpetaTranscripciones"
DEADLINE = time.time() + 22 * 3600
MAX_ATTEMPTS = 3

attempts: Counter = Counter()
done: set[str] = set()


def main() -> None:
    try:
        projects = load_projects(DATA / "projects.json")
    except Exception:
        traceback.print_exc()
        projects = []

    while time.time() < DEADLINE:
        try:
            mappings = list(BASE.rglob("frame_mapping.json")) if BASE.exists() else []
            for mapping in mappings:
                frames_dir = mapping.parent
                key = str(frames_dir)
                if key in done or attempts[key] >= MAX_ATTEMPTS:
                    continue
                if (frames_dir / "manual" / "STUDY_GUIDE.md").exists():
                    done.add(key)
                    continue
                name = frames_dir.name
                try:
                    project = match_project(Path(name), projects)
                except Exception:
                    project = None
                attempts[key] += 1
                print(f"[BATCH_DOCS] attempt {attempts[key]} for {name}", flush=True)
                try:
                    result = generate_documentation(frames_dir, name, project_config=project)
                    status = result.get("study_guide")
                    print(f"[BATCH_DOCS] {name}: steps={result.get('step_count')} study_guide={status}", flush=True)
                    if status in ("ok", "blocked", "unavailable"):
                        done.add(key)
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()
        time.sleep(600)
    print("[BATCH_DOCS] deadline reached", flush=True)


if __name__ == "__main__":
    main()
