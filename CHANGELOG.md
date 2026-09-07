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
  instruction comes only from captured evidence — the transcript excerpt
  (`confidence: "high"`), or local OCR text read off the frame
  (`confidence: "medium"`, always attempted when a frame is available). When
  both exist the instruction combines them (`evidence_source:
  "transcript_ocr"`, confidence stays "high"). A
  privacy-gated vision-LLM description is attempted only when both come up
  empty, and is kept as a separate, clearly-labeled `visual_description` —
  an unverified interpretation, never merged into the instruction and never
  raising confidence. A frame with neither is `confidence: "low"` instead of
  guessed.
- **Human review UI** (§4.8): the dashboard's DOCS tab renders each step as
  an editable card — instruction text, confidence/evidence-source/reviewed
  badges, Save/Remove actions — plus AI-package download links and a
  Regenerate button. `update_step`/`remove_step`/`regenerate_from_steps()`
  persist edits and rebuild both bundles without re-transcribing or
  re-running OCR/vision.
- **Dashboard**: an Overview card (files processed, media duration
  processed, success rate, average processing time), a real (log-derived,
  not fabricated) 8-stage pipeline visualization, a **DOCS** tab in the file
  workspace rendering the generated manual/AI-package, and a Documentation
  action in the files table. Backend status strings (`completed_routed`,
  `failed_routed`, ...) now render as human-readable labels.
- `scripts/smoke.py`: a fast, browser-free smoke harness (core imports,
  settings, FFmpeg detection, dashboard boot, documentation engine against a
  tiny fixture) — new required CI job ahead of the E2E job.
- `scripts/security.py::check_denylisted_identifiers_in_history`: the
  private-identifier denylist check now also scans full git history
  (commit messages + diffs across every ref), not only the current tree —
  automates the one-time manual audit `docs/GIT_HISTORY_CLEANUP.md` already
  documented into a repeatable regression check.

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
- `regenerate_from_steps()` read a `source` block from `steps.json` that
  `_write_steps_json` never actually wrote — duration/language/
  extraction_method silently reset to `0.0`/`"unknown"` on every
  regeneration. `steps.json` now persists `source` alongside the steps.
- Each step's dashboard thumbnail (`frame_url`) 404'd — it was built
  relative to `manual_dir` (matching `MANUAL.md`'s own `assets/...` image
  references) instead of `frames_parent`, where the raw frame actually
  lives.

## [1.0.0] — Initial public release

Local-first transcription pipeline: `faster-whisper` transcription,
declarative per-project routing, keyframe extraction + timestamp mapping
for tutorial videos, optional privacy-gated multimodal LLM enrichment,
security-hardened dashboard (`SafePathResolver`, localhost-only, per-process
token), and fail-closed quality/security/dependency/secret-scan CI gates.
