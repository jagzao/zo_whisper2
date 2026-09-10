"""Video-to-documentation engine.

Turns a tutorial video's already-persisted `frame_mapping.json` (real frame
PTS + transcript segments aligned by `_integrate_transcription_with_frames`)
into two grounded artifacts:

- a human manual (`manual/MANUAL.md` + `manual/MANUAL.pdf` + `manual/assets/`)
- an AI-ready knowledge package (`ai-package/manifest.json`, `steps.json`,
  `chunks.jsonl`, `knowledge.md`)

Every generated step is grounded in the transcript excerpt found near its
frame's timestamp — never invented — see `models.ProceduralStep` and
`engine.build_steps`.
"""
