# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/).

## [1.1.0] — Zo Whisper Studio: Video-to-Documentation

Public rebrand and a new core capability: turning tutorial/screen-recording
videos into a grounded human manual and an AI-ready knowledge package, on
top of the existing transcription pipeline.

### Added

- **Video-to-documentation engine** (`transcript_pipeline.documentation`):
  every tutorial video's already-aligned frame/transcript data now also
  produces `manual/MANUAL.md` (+ `steps.json`, image assets) and
  `ai-package/manifest.json` + `chunks.jsonl` + `knowledge.md`. Every step's
  instruction is the transcript excerpt itself — never LLM-generated — and
  a frame with no nearby transcript is marked `confidence: "low"` instead of
  guessed. `regenerate_from_steps()` rebuilds both bundles from a
  human-edited `steps.json` without re-transcribing. No LLM call involved.
- **Dashboard**: an Overview card (files processed, media duration
  processed, success rate, average processing time), a real (log-derived,
  not fabricated) 8-stage pipeline visualization, a **DOCS** tab in the file
  workspace rendering the generated manual/AI-package, and a Documentation
  action in the files table. Backend status strings (`completed_routed`,
  `failed_routed`, ...) now render as human-readable labels.
- `scripts/smoke.py`: a fast, browser-free smoke harness (core imports,
  settings, FFmpeg detection, dashboard boot, documentation engine against a
  tiny fixture) — new required CI job ahead of the E2E job.

### Changed

- Public product name is now **Zo Whisper Studio** (README, dashboard title/
  header, package description). The importable package and pip distribution
  name (`transcript_pipeline` / `transcript-pipeline`) are unchanged.
- The dashboard's pipeline runner streams subprocess output line-by-line
  instead of blocking until each step fully exits — a long transcription run
  no longer leaves the dashboard showing a stale log for its duration.
- `generate_mock_data.py` also builds a synthetic tutorial fixture (frame
  mapping + real documentation-engine output) so CI/local E2E screenshots
  have real manual/AI-package content to exercise.

### Fixed

- **Release blocker**: `scene`/`smart_scene` keyframe extraction persisted a
  *uniform-estimate* timestamp (`duration / frame_count`) into
  `frame_mapping.json` instead of the real PTS FFmpeg had already detected
  during scene-change detection — any evidence/documentation built on those
  timestamps would cite the wrong moment in the source video. Both methods
  now share a detect-then-precise-seek pipeline and thread the real PTS
  through.
- `docs/assets/watermark.py` crashed on a logo image with no alpha channel.

## [1.0.0] — Initial public release

Local-first transcription pipeline: `faster-whisper` transcription,
declarative per-project routing, keyframe extraction + timestamp mapping
for tutorial videos, optional privacy-gated multimodal LLM enrichment,
security-hardened dashboard (`SafePathResolver`, localhost-only, per-process
token), and fail-closed quality/security/dependency/secret-scan CI gates.
