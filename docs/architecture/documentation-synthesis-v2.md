# Documentation Synthesis V2

Documentation V2 keeps captured media evidence distinct from derived
knowledge. It retains the legacy `manual/steps.json` compatibility format,
while producing a semantic manual and retrieval package when grounded
synthesis is available.

## Outputs

For a processed `{recording}_Frames/` directory:

```text
evidence/
  evidence.jsonl             # bounded source excerpts and provenance
  EVIDENCE_TIMELINE.md       # chronological evidence view
  review-queue.json          # low/no-evidence items needing human review
manual/
  MANUAL.md                  # semantic sections and evidence references
  MANUAL.pdf                 # printable semantic manual
  steps.json                 # legacy evidence-step compatibility
ai-package/
  manifest.json
  chunks.jsonl               # semantic sections/claims/procedures
  knowledge.md
  knowledge-package.json     # when Second Brain publishing is enabled
```

Evidence IDs are deterministic for unchanged persisted evidence. Synthesis
does not rewrite that evidence. Every factual claim and procedure step must
cite known evidence; unsupported synthesis is rejected and cannot replace a
last-good semantic manual or publish to the Second Brain. Model output cannot
mark content human reviewed.

## Documentation modes

Set `documentation.mode` in a project entry in `projects.json`:

`AUTO`, `TUTORIAL`, `KT_SESSION`, `PROCESS_WALKTHROUGH`, `MEETING`,
`ARCHITECTURE`, `INCIDENT`, or `REFERENCE`.

An explicit documentation mode takes precedence over artifact mappings.
Filename suffixes such as `_tutorial` are hints only. AUTO may use the bounded
classifier when synthesis is allowed and otherwise falls back safely to
REFERENCE. A KT session or meeting may have zero procedures; a procedure is
emitted only when ordered operational actions are supported by evidence.

## Privacy and synthesis

The existing provider policy remains authoritative. Confidential projects
cannot send evidence to a remote LLM; the request is blocked before dispatch.
An unavailable or blocked provider still leaves the Evidence Plane available
and reports a typed synthesis status. V2 compacts inputs deterministically,
uses bounded structured JSON synthesis, permits at most one malformed-output
repair attempt, and does not call a model once per frame. Whole transcripts,
media, and VTT files are not included in Knowledge Packages.

## Regeneration

Regenerate a previously processed recording using saved `frame_mapping.json`,
`manual/steps.json`, frames, and persisted evidence:

```bat
python -m transcript_pipeline.documentation.regenerate_v2 "path\to\recording_Frames"
```

Optional flags:

- `--mode KT_SESSION` explicitly overrides the resolved mode for this run.
- `--evidence-only` writes evidence outputs without synthesis.
- `--projects-config path\to\projects.json --project ProjectName` loads
  project privacy and Second Brain settings.
- `--json` prints the detailed result.

This path does not invoke Whisper, FFmpeg keyframe extraction, OCR, vision, or
recompression. Existing review and legacy step-edit functions remain
available.

## Knowledge-to-Action boundary

Knowledge Package V2 maps the semantic document title and executive summary,
then carries semantic sections and optional real procedures. PROJECT/GLOBAL
scope, project isolation, privacy checks, and the durable publisher outbox
remain in force. Knowledge and actionability labels are not execution
authority: only the existing validated procedure-to-capability chain can
authorize execution.
