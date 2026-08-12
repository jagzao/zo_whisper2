# Skill: Transcription Pipeline (Whisper + AI Augmentation)

## Context

This is a Windows-first Python pipeline that:
1. Compresses videos (H.265/HEVC, CRF 24-26) via `compress_and_move.py`.
2. Extracts audio and transcribes with `faster-whisper` (`large-v2`, beam_size=10, best_of=5, VAD).
3. Detects tutorial videos (filename contains `tutorial`) and extracts **smart scene-change frames** (not mouse-movement frames).
4. Routes results to project folders (`zo_`, `northwind_`, `jm_`, `interview/entrevista`).

## Key Files & Commands

| Purpose | Path / Command |
|---------|----------------|
| Main orchestrator | `RUN_MAX_QUALITY.bat` |
| Python entry | `master_processor.py` |
| High-quality transcription | `simple_scan.py` |
| Video compression | `compress_and_move.py` |
| Scene frame extraction | `src/transcript_pipeline/media/keyframe_extractor.py` |
| Config (paths, tokens) | `scan_config.env` |
| Output transcriptions | `CarpetaTranscripciones/` |
| Output frames | `Frames/` |

## Critical Environment Variables

```
# scan_config.env
ICECREAM_MUSIC=C:\Users\<user>\Music
ICECREAM_VIDEOS=C:\Users\<user>\Videos
NORTHWIND_PATH=C:\...\northwind
ZO_INTERVIEWS_PATH=C:\...\zo

# Optional pipeline tuning
KEYFRAME_METHOD=smart_scene       # NEW: robust scene-change detection
VIDEO_COMPRESS_CRF=25             # 24-26 recommended
FRAME_EXTRACTION_MAX_FRAMES=50
```

## Feature: Smart Scene Extraction for Tutorials

### Problem
Older `iframe` and basic `scene` methods produced too many frames from cursor movement, UI micro-changes, or minor screen updates. This wasted storage and produced noisy tutorial summaries.

### Solution: `smart_scene` method (in `keyframe_extractor.py`)
- **Pre-filter**: Applies a light Gaussian blur via FFmpeg before scene detection to ignore cursor noise.
- **Threshold**: Uses `gt(scene,0.5)` (stricter than `0.4`) and a 5-second cooldown between frames.
- **Deduplication**: Calculates perceptual hashes (`ahash`) after extraction and removes >90% similar consecutive frames.
- **Limits**: Respects `max_frames` strictly (default 50 for long videos).

### How to Enable

In `scan_config.env` (or your shell environment before running `.bat`):

```env
KEYFRAME_METHOD=smart_scene
```

`simple_scan.py` already reads this variable and passes it to `KeyframeExtractor`.

### Implementation Notes

- The `smart_scene` method is implemented in `src/transcript_pipeline/media/keyframe_extractor.py`.
- It calls FFmpeg twice: once for blurred scene detection, once for deduplication analysis.
- Requires `ffmpeg` and `ffprobe` on PATH.
- Requires `imagehash` Python package for deduplication (raises `RuntimeError` if missing — install with `pip install imagehash pillow`).

## Routing Rules

`master_processor.py` classifies inputs by filename prefix:

| Prefix / Keyword | Target Folder | Handler |
|------------------|---------------|---------|
| `zo_` | `Videos/py_zo/` | - |
| `northwind_` | `Videos/py_northwind/` | `ClientMeetingHandler` |
| `jm_` | `Videos/py_jm/` | - |
| `interview` / `entrevista` | `Videos/zo_Entrevista/` | `ZoHandler` |

## Quality Settings

`simple_scan.py` enforces maximum transcription quality:
- `model = "large-v3"`
- `beam_size = 10`
- `best_of = 5`
- `temperature = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]`
- `vad_filter = True` (if `onnxruntime` available)
- `condition_on_previous_text = True`

## Language Detection (priority order)

1. Filename prefix `es_` / `en_` → explicit
2. `lang.txt` in the file's folder (contains just `es` or `en`) → folder default
3. No signal → Whisper auto-detects

## LLM-Augmented Post-Processing (Optional)

This skill can be extended with LLM calls (provider-agnostic) for:
- **Summary generation** from transcripts (`CarpetaTranscripciones/`).
- **Timestamped QA**: attach relevant frame timestamps to summary paragraphs.
- **Auto-routing confirmation**: ask LLM whether a file should be routed to `northwind` vs `zo`.

Use `.agents/templates/summary.md` as the prompt template.
Use `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` env vars — never hardcode provider.

## Style
- 4-space indentation, type hints, `snake_case` modules, `CamelCase` classes
- No hardcoded absolute paths — use env vars or paths relative to `scan_config.env`
- `black`, `flake8`, `mypy` are **not configured** in this project — do not run them
