# SPEC-ZO-KNOWLEDGE-001 — Cross-repo Knowledge Contracts

## 1. Core enums

### KnowledgeScope

```
PROJECT
GLOBAL
```

Rules:
- required on every published knowledge package;
- default for project-derived media: `PROJECT`;
- `PROJECT` requires `projectId`;
- `GLOBAL` is explicit;
- confidential source + GLOBAL is invalid;
- no automatic widening from PROJECT to GLOBAL.

### KnowledgeActionability

```
REFERENCE
GUIDED
EXECUTABLE
```

This declares intended use, not permission to execute.

### KnowledgeArtifactType

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

### SkillValidationStatus

```
CANDIDATE
VALIDATED
DISABLED
SUPERSEDED
```

Only VALIDATED skills may execute.

### ApprovalPolicy

```
NONE
BEFORE_WRITE
ALWAYS
```

Actual KAV policy may impose a stricter approval than the skill asks for.

## 2. Zo project configuration

Add an optional `second_brain` object to project config.

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

Validation:
- absent -> publishing disabled (backward-compatible);
- enabled=true + scope=PROJECT -> project_id/domain required;
- enabled=true + scope=GLOBAL -> project_id may be absent but domain remains explicit;
- data_classification=confidential + scope=GLOBAL -> invalid;
- publish_assets=false by default;
- unknown enum values rejected.

Examples:

P&G:
```json
{
  "data_classification": "confidential",
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

Generic tutorials:
```json
{
  "data_classification": "public",
  "second_brain": {
    "enabled": true,
    "domain": "second-brain/global",
    "scope": "GLOBAL",
    "default_artifact_type": "TUTORIAL",
    "default_actionability": "GUIDED",
    "publish_assets": false
  }
}
```

## 3. Knowledge Package v2

File:
`ai-package/knowledge-package.json`

Required shape:

```json
{
  "schemaVersion": 2,
  "packageId": "sha256:...",
  "knowledgeId": "stable-id",
  "version": 1,
  "scope": "PROJECT",
  "projectId": "p-g",
  "domain": "second-brain/p-g",
  "artifactType": "TUTORIAL",
  "actionability": "GUIDED",
  "dataClassification": "confidential",
  "status": "ACTIVE",
  "source": {
    "sourceId": "sha256:...",
    "sourceHash": "sha256:...",
    "mediaName": "...",
    "mediaType": "video",
    "durationSeconds": 1200,
    "language": "en",
    "generatedAt": "...",
    "pipelineVersion": "..."
  },
  "provenance": {
    "producer": "zo-media-intelligence",
    "projectMatch": "explicit|routing|default",
    "rawTranscriptPublished": false,
    "rawMediaPublished": false
  },
  "knowledge": {
    "title": "...",
    "summary": "...",
    "tags": [],
    "procedures": []
  },
  "evidence": [],
  "supersedesKnowledgeId": null
}
```

### Identity

- `sourceId`: stable hash/id of source media/session.
- `packageId`: deterministic hash of package canonical payload + schema version.
- `knowledgeId`: stable logical identity persisted once assigned.
- reprocessing same source and unchanged derived content -> same package id / idempotent no-op.
- changed derivation for same knowledgeId -> version increments.
- a new recording is a new knowledgeId unless explicit `supersedesKnowledgeId` is provided.
- fuzzy similarity must never auto-supersede.

## 4. Procedure v1

Embedded in package or separately emitted as:
`ai-package/procedure.json`

```json
{
  "schemaVersion": 1,
  "procedureId": "...",
  "knowledgeId": "...",
  "version": 1,
  "scope": "GLOBAL",
  "projectId": null,
  "actionability": "EXECUTABLE",
  "title": "Create an Azure Data Factory pipeline",
  "parameters": [],
  "steps": [
    {
      "id": "...",
      "order": 1,
      "instruction": "...",
      "timestamp": 34.2,
      "evidence": {
        "transcriptExcerpt": "...",
        "ocrText": "...",
        "frameRef": "...",
        "sourceSegmentIndex": null,
        "confidence": "high",
        "reviewed": true
      },
      "semanticAction": null,
      "semanticTarget": null
    }
  ],
  "preconditions": [],
  "expectedOutcomes": []
}
```

Important:
- observed procedure text can exist without semanticAction/tool binding;
- no executable tool call is invented by Zo Media;
- bounded evidence excerpts are allowed; whole raw transcript is not.

## 5. Publisher outbox

Local durable directory under DATA_ROOT:

```
knowledge-outbox/
  pending/
  publishing/
  published/
  failed/
  ledger.json
```

Each item:
```json
{
  "packageId": "...",
  "attempt": 0,
  "state": "PENDING",
  "createdAt": "...",
  "nextAttemptAt": "...",
  "lastErrorCode": null
}
```

Properties:
- atomic writes/moves;
- bounded retry + backoff;
- docs generation succeeds even when Second Brain is unavailable;
- same packageId never publishes twice logically;
- no unbounded loop;
- no raw secret in ledger.

## 6. Publisher transport boundary

Define an interface:

```
publish(package) -> ACK | RETRYABLE_FAILURE | TERMINAL_FAILURE
```

Adapters:
- FILE_OUTBOX / local bridge;
- ZAVI_API.

ZMI must never contain Supabase service-role credentials.

## 7. Zavi import contract

Suggested endpoint:
`POST /api/knowledge/import`

Requirements:
- authenticated server boundary;
- Zod schema validation;
- idempotency by packageId;
- PROJECT requires mapped project;
- GLOBAL confidential package rejected;
- stores evidence plane first;
- embeddings generated by existing Zavi ingestion pipeline;
- raw media/transcript fields rejected if package claims forbidden data.

## 8. Storage scope

### Evidence plane

Add to `zavi_knowledge_documents` and `zavi_knowledge_chunks`:
- `knowledge_scope`;
- `actionability`;
- `origin_project_id`;
- `knowledge_id`;
- `knowledge_version`;
- `package_id`;
- `artifact_type`.

Existing rows preserve current behavior:
- existing documents/chunks default `PROJECT`.

Global storage uses an internal storage partition constant, e.g.
`__global__`, while `origin_project_id` keeps source provenance.
The reserved partition is never exposed as a user project.

### Canonical plane

Add to `zavi_knowledge_entries`:
- `knowledge_scope` default GLOBAL for existing curated entries;
- `scope_project_id` nullable;
- `actionability` default REFERENCE;
- `knowledge_id`/version where applicable.

Do not reuse `learning_scope`.

## 9. Retrieval contract

Given active project P:

```
allowed(row, P) =
    row.scope == GLOBAL
    OR (row.scope == PROJECT AND row.projectId == P)
```

Apply to:
- lexical retrieval;
- pgvector RPC;
- normalized Second Brain retrieval;
- procedure search;
- skill selection.

Expected:
- active P&G -> GLOBAL + P&G;
- active Gravity -> GLOBAL + Gravity;
- no active project -> GLOBAL only;
- never P&G while another project is active.

## 10. Promotion contract

PROJECT -> GLOBAL creates a new promoted artifact.

Requirements:
- explicit owner approval;
- sanitization/review;
- original PROJECT artifact remains;
- promoted artifact links to source provenance;
- confidential classification blocks promotion until explicitly reclassified by owner;
- no automated LLM promotion decision.

## 11. Skill candidate contract

KAV does not execute raw procedure text.

```json
{
  "skillId": "azure.adf.create-pipeline",
  "knowledgeRef": {
    "knowledgeId": "...",
    "version": 2,
    "scope": "GLOBAL",
    "projectId": null
  },
  "status": "VALIDATED",
  "requiredCapabilities": [
    "azure.datafactory.createPipeline"
  ],
  "parameters": [],
  "approvalPolicy": "BEFORE_WRITE",
  "riskTag": "MEDIUM",
  "preconditions": [],
  "postconditions": [],
  "rollback": {
    "supported": false
  },
  "evidenceRefs": []
}
```

### Execution rule

```
scope allowed
AND status == VALIDATED
AND required capabilities available
AND required credentials/permissions available
AND policy permits
AND approval satisfied
=> execute
```

Otherwise:
- missing capability -> GUIDED_ONLY / structured failure;
- scope mismatch -> DENY;
- candidate/unverified -> DENY;
- missing approval -> WAITING_APPROVAL.

## 12. Execution receipt

After execution:

```json
{
  "executionId": "...",
  "skillId": "...",
  "skillVersion": 1,
  "knowledgeId": "...",
  "knowledgeVersion": 2,
  "projectId": "...",
  "startedAt": "...",
  "completedAt": "...",
  "result": "SUCCESS|FAILURE|PARTIAL",
  "postconditions": [],
  "evidence": [],
  "rollback": null
}
```

Receipt may become evidence, but never automatically rewrites canonical knowledge as true.

## 13. K'ab project identity extension

For future Android sender integration, session creation adds an optional explicit project identity selected from an authorized project catalog.

No filename heuristic is authoritative for phone-captured course media.

A safe future endpoint may expose:
`GET /kab/v1/projects`
with only safe fields:
- project key;
- display name;
- KnowledgeScope default;
- artifact type default.

No prompts, filesystem paths, secrets or internal configuration are exposed.
