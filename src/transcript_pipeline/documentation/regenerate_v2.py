"""V2 regeneration command.

Deterministic regeneration from already processed frames directory.
No Whisper/FFmpeg/OCR/vision calls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from transcript_pipeline.documentation.orchestration import generate_documentation_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate V2 documentation from persisted evidence.")
    parser.add_argument("frames_dir", help="Path to processed frames directory")
    parser.add_argument("--mode", help="Override documentation mode")
    parser.add_argument("--no-upstream-work", action="store_true", help="Guard against upstream work")
    args = parser.parse_args()
    
    frames_dir = Path(args.frames_dir)
    if not frames_dir.exists():
        print(f"Error: frames directory {frames_dir} does not exist", file=sys.stderr)
        return 1
    
    # TODO: implement guard against upstream work (monkeypatch)
    
    # Infer video name from frame_mapping.json
    mapping_path = frames_dir / "frame_mapping.json"
    if not mapping_path.exists():
        print(f"Error: frame_mapping.json not found", file=sys.stderr)
        return 1
    
    import json
    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    video_name = data.get("video_info", {}).get("name", "unknown")
    
    # Build project config with optional mode override
    project_config = None
    if args.mode:
        project_config = {"documentation": {"mode": args.mode}}
    
    result = generate_documentation_v2(
        frames_dir=frames_dir,
        video_name=video_name,
        project_config=project_config,
    )
    
    print(json.dumps(result, indent=2))
    
    if result.get("status") == "ready":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())