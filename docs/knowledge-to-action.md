# Knowledge-to-Action — Zo Media producer

How Zo Media Intelligence turns completed documentation into publishable
knowledge for a Second Brain (Zavi), per SPEC-ZO-KNOWLEDGE-001.

## Project second_brain config

Optional per-project object in `projects.json`:

```json
{
  "second_brain": {
    "enabled": true,
    "project_id": "p-g",
    "domain": "second-brain/p-g",
    "scope": "PROJECT",
    "default_artifact_type": "KT",
    "default_actionability": "REFERENCE",
    "publish_assets": false
  }
}
```

- Absent `second_brain` -> publishing disabled; legacy behavior unchanged.
- `scope=PROJECT` requires `project_id` + `domain`.
- `scope=GLOBAL` requires `domain`; `project_id` may be absent.
- `data_classification=confidential` + `scope=GLOBAL` is rejected.
- `publish_assets=false` by default (frames are not published).
- Unknown enum values are rejected at validation time.

## PROJECT vs GLOBAL

- `PROJECT`: knowledge is private to one Second Brain project (e.g. P&G,
  `project_id=p-g`). Never visible to other projects.
- `GLOBAL`: shared knowledge (e.g. a generic public Azure tutorial).
  Promotion from PROJECT to GLOBAL is an explicit owner action in Zavi —
  Zo never widens scope automatically.

### KnowledgeScope vs Zavi LearningScope

`KnowledgeScope` (PROJECT/GLOBAL) governs where knowledge is stored and who
can retrieve it. Zavi's pre-existing `LearningScope` is an unrelated concept
and is never reused for this feature.

## Knowledge Package v2

When documentation completes for a project with `second_brain.enabled`, Zo
writes `ai-package/knowledge-package.json` (and `ai-package/procedure.json`
for procedural content) next to the existing v1 package outputs:

- deterministic identity: same derived content -> identical `packageId`
  (idempotent reprocessing);
- same `knowledgeId` + changed derivation -> `version` increments;
- a new recording is a new `knowledgeId`; nothing auto-supersedes;
- `provenance.rawTranscriptPublished=false` and
  `provenance.rawMediaPublished=false` always.

Actionability (`REFERENCE|GUIDED|EXECUTABLE`) declares intended use only.
It is never permission to execute: the chain is knowledge -> procedure ->
skill candidate -> capability binding -> VALIDATED -> policy -> approval ->
execute -> postcondition -> receipt (enforced in KAV, not here).

## Raw transcript/media exclusion

The package contains only bounded evidence excerpts (per-step transcript
excerpts and OCR text, clipped to 1200 chars). Raw video/audio/VTT and whole
transcripts are never published. The builder fails closed if a forbidden raw
field ever appears in a package payload.

## Durable outbox and retries

Published packages are enqueued on a durable local outbox under
`DATA_ROOT/knowledge-outbox/`:

```
pending/    waiting for delivery
publishing/ claimed by a publisher pass (crash-safe, reclaimed on restart)
published/  acknowledged by the Second Brain
failed/     terminal or retry-exhausted (inspectable)
ledger.json compact idempotency + observability ledger
```

- Writes and moves are atomic; a crash never leaves a half-published state.
- Retries are bounded (5 attempts) with exponential backoff (30s..1h). No
  busy loop; publish cycles are time-boxed.
- Documentation generation always succeeds even when the publisher is
  unavailable — the package simply waits in `pending/`.
- The same `packageId` is never logically published twice.

Publisher adapters: `FILE_OUTBOX` (local deterministic bridge) and
`ZAVI_API` (`ZAVI_KNOWLEDGE_URL` + `ZAVI_KNOWLEDGE_TOKEN` env). Zo never
holds a Supabase service-role credential.

## K'ab projectKey

Phone-captured sessions may carry an explicit `projectKey` chosen from the
authenticated catalog endpoint `GET /kab/v1/projects` (safe fields only:
key, display name, scope default, artifact default). The key persists in
session metadata and the consolidated session publishes through the same
package builder as the desktop pipeline.

- No filename heuristics: a session without a resolvable `projectKey`
  completes processing normally, but Second Brain publishing is disabled
  for that session.
- Old sessions without `projectKey` keep working exactly as before.

## Observability

`knowledge-outbox/ledger.json` powers a compact snapshot (pending/published/
failed counts, last package id, last typed result/error code). No secrets,
tokens, or transcripts are ever logged.
