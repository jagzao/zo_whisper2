# AUDIT-ZO-KNOWLEDGE-001 — Knowledge-to-Action Readiness

## Scope

Cross-repository audit for:
- `jagzao/zo_whisper2` — knowledge producer;
- `jagzao/zavi` — Second Brain storage/retrieval;
- `jagzao/zavi-kab` — KAV/skills execution runtime.

Primary use cases:
1. P&G tutorial/KT content must become project-private Second Brain knowledge.
2. General technical tutorials (for example Azure Data Factory) may become global knowledge.
3. KAV must eventually be able to use validated procedural knowledge to perform an action, not only answer questions.

## Architectural conclusion

The current stack has most primitives, but the three systems are not connected by a safe, versioned knowledge contract.

The missing architecture is:

```
Zo Media Intelligence
  -> derived Knowledge Package
  -> durable Knowledge Outbox / Publisher
  -> Zavi Second Brain
       -> Evidence Plane (documents/chunks)
       -> Canonical Knowledge Plane (normalized entries)
       -> Procedure/Skill candidates
  -> KAV Skill Runtime
       -> capability binding
       -> approval/policy
       -> execution
       -> verification receipt
```

The core design rule is:

> Knowledge says HOW. Capabilities determine CAN. Policy determines MAY. Verification determines DID.

## Existing strengths

### Zo Media Intelligence
- already emits `MANUAL.md`, `MANUAL.pdf`, `steps.json`, `manifest.json`, `chunks.jsonl`, `knowledge.md`;
- procedural steps preserve timestamp, confidence, evidence source, transcript/OCR evidence and review status;
- project routing and data classification already exist;
- K'ab now produces segmented, consolidated tutorial/course artifacts.

### Zavi
- normalized Second Brain exists in `zavi_knowledge_entries`;
- project-scoped evidence/vector RAG exists in `zavi_knowledge_documents` / `zavi_knowledge_chunks`;
- vector ingestion is idempotent by content/embedding fingerprint;
- retrieval already has project isolation;
- learning provenance/scope exists for interview learning.

### KAV / zavi-kab
- `SkillsRuntime` exists;
- skills have parameters, steps, source and risk tag;
- `TeachMode` exists;
- handlers execute validated parameter maps;
- runtime already has structured lifecycle/progress contracts.

## Critical semantic decision

### New enum: KnowledgeScope

```
PROJECT
GLOBAL
```

This enum is NOT the existing Zavi `LearningScope`.

They answer different questions:

- `LearningScope`: how far an interview-learning observation may propagate
  (`SESSION_ONLY | VACANCY | CANDIDATE_GLOBAL | KNOWLEDGE_GLOBAL`).
- `KnowledgeScope`: who is allowed to retrieve/use a knowledge artifact
  (`PROJECT | GLOBAL`).

Reusing `LearningScope` for project privacy would create ambiguous and unsafe behavior.

### Default policy

- Knowledge produced while inside a named project defaults to `PROJECT`.
- `PROJECT` requires a concrete project/domain id.
- Knowledge may become `GLOBAL` only through explicit project configuration or explicit owner promotion.
- Automatic PROJECT -> GLOBAL promotion is forbidden.
- A `confidential` Zo Media project can never auto-publish as GLOBAL.
- `data_classification` and `KnowledgeScope` remain separate dimensions.

Example:
- P&G tutorial -> `PROJECT`, project `p-g`.
- generic Azure Data Factory tutorial -> `GLOBAL`.

## Second dimension: actionability

New enum:

```
REFERENCE
GUIDED
EXECUTABLE
```

Meaning:
- REFERENCE: may support answers/retrieval only.
- GUIDED: may be used to guide a human through a procedure.
- EXECUTABLE: may become an executable skill candidate.

`EXECUTABLE` does NOT authorize execution by itself.

Actual execution also requires:
- validated skill status;
- compatible registered capability/tool;
- valid parameters;
- current credential/permission availability;
- policy/approval gate;
- postcondition verification.

## Third dimension: artifact type

Producer-side `KnowledgeArtifactType`:

```
TUTORIAL
PROCEDURE
KT
TROUBLESHOOTING
INCIDENT
POLICY
DECISION
APPLICATION
REFERENCE
```

This is not forced to replace Zavi's legacy `KnowledgeEntryType` or `KnowledgeKind`.
A deterministic mapping layer converts producer artifacts into consumer types.

## P0 gaps

### GAP-KNOW-001 — Zo AI package has no scope or Second Brain identity
Current package has source video, procedures and evidence, but no:
- project id;
- Second Brain domain;
- KnowledgeScope;
- actionability;
- artifact type;
- source hash;
- stable knowledge id/version;
- supersedes relation;
- publisher schema version.

### GAP-KNOW-002 — no durable publisher
Documentation generation ends on disk.
There is no:
- knowledge outbox;
- idempotency key;
- retry state;
- publish ledger;
- consumer acknowledgement;
- conflict/version handling.

### GAP-KNOW-003 — Zavi project RAG cannot combine project + global knowledge
Current vector/lexical retrieval filters exact `project_id`.
Global knowledge would have to be duplicated into every project.

Required query invariant:
```
allowed(scope, activeProject) =
  scope == GLOBAL
  OR (scope == PROJECT AND projectId == activeProject)
```

### GAP-KNOW-004 — normalized Second Brain has no project visibility boundary
`secondBrainRetrieval.ts` currently retrieves normalized entries without a project/scope field.
Project-confidential data MUST NOT be inserted there until scope-aware retrieval exists.

### GAP-KNOW-005 — raw derived package cannot safely become a skill
The current procedure model is evidence-grounded text.
`ProceduralStep.to_dict()` emits `action=null`, `target=null`.
There is no typed capability/tool binding.

### GAP-KNOW-006 — KAV skills lack knowledge provenance and execution governance
Current `Skill` has:
- id/name/description;
- string parameters;
- string steps;
- source;
- riskTag.

Missing:
- knowledge id/version;
- KnowledgeScope/project;
- capability requirements;
- execution status;
- approval policy;
- pre/postconditions;
- rollback metadata;
- evidence references;
- execution receipt.

## P1 gaps

### GAP-KNOW-007 — no explicit project-to-Second-Brain mapping in Zo projects
Need a project config such as:
```json
{
  "second_brain": {
    "enabled": true,
    "project_id": "p-g",
    "domain": "second-brain/p-g",
    "scope": "PROJECT",
    "default_actionability": "REFERENCE"
  }
}
```

### GAP-KNOW-008 — K'ab session lacks explicit knowledge/project identity
K'ab course capture must not rely on filename heuristics.
The sender contract needs an explicit optional `projectKey` / project identity selected at session creation.

### GAP-KNOW-009 — no safe PROJECT -> GLOBAL promotion workflow
Promotion must:
- require owner action;
- sanitize project/client-specific context;
- create a new GLOBAL artifact/version;
- keep provenance;
- never mutate the original PROJECT artifact into global visibility.

### GAP-KNOW-010 — no knowledge version/supersede semantics across new recordings
Reprocessing the same source must be idempotent.
A new recording must not automatically supersede an old one by fuzzy similarity.
Supersession must be explicit.

### GAP-KNOW-011 — no unpublish/revoke propagation
A deleted/deprecated source must be able to:
- mark its document/chunks superseded/deprecated;
- disable skill candidates derived from it;
- prevent stale executable skill selection.

### GAP-KNOW-012 — evidence publishing privacy
P&G raw video/audio/VTT/full transcript must not be uploaded to Second Brain.
Only derived structured knowledge + bounded evidence excerpts/metadata are publishable by default.
Frame/image publishing must remain separately policy-controlled.

## P2 gaps

- execution receipts are not fed back as evidence;
- no skill success/failure telemetry to improve confidence;
- no automated reusable-knowledge suggestion from project-private knowledge;
- no semantic deduplication across global tutorials;
- no automated capability discovery for procedures;
- no real Azure Data Factory tool binding yet.

## Second Brain model decision

Second Brain is explicitly two planes:

### Evidence Plane
`zavi_knowledge_documents` + `zavi_knowledge_chunks`

Purpose:
- retain derived knowledge/evidence from a source;
- vector/lexical retrieval;
- project/global isolation;
- version/status/source provenance.

Whisper/ZMI packages land here first.

### Canonical Knowledge Plane
`zavi_knowledge_entries`

Purpose:
- normalized, curated, reusable concepts/procedures;
- verification lifecycle;
- ready-answer/structured knowledge.

Imported tutorials are NOT silently promoted to canonical verified knowledge.

This preserves the current trust model:
source-derived material can answer with provenance while canonical promotion remains controlled.

## KAV execution decision

A tutorial can produce:
```
knowledge package
 -> procedure candidate
 -> skill candidate
 -> validated skill
 -> executable action
```

Never:
```
video transcript -> arbitrary tool calls
```

The Skill Runtime executes a validated binding, not raw prose.

## Security invariants

1. Project scope is enforced in storage/retrieval queries, never prompt-only.
2. P&G PROJECT knowledge is never visible to another project.
3. GLOBAL + active PROJECT may be retrieved together.
4. Confidential source cannot become GLOBAL automatically.
5. Raw transcripts/media are not Second Brain inputs.
6. Knowledge never carries runtime credentials.
7. EXECUTABLE knowledge is not executable until skill validation/binding succeeds.
8. PROJECT executable skills can run only when the active project matches.
9. Superseded/deprecated procedures cannot be selected for new execution.
10. Any write/destructive skill still passes KAV approval/policy gates.
