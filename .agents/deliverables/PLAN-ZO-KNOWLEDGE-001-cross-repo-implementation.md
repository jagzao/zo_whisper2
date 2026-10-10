# PLAN-ZO-KNOWLEDGE-001 — Cross-repo Implementation Plan

## Source of truth

- `AUDIT-ZO-KNOWLEDGE-001-knowledge-to-action.md`
- `EPIC-ZO-KNOWLEDGE-001-project-aware-knowledge-to-action.md`
- `SPEC-ZO-KNOWLEDGE-001-cross-repo-contracts.md`
- `US-ZO-KNOWLEDGE-001-master.md`

This plan contains the heavy-model design decisions. Local implementation workers MUST NOT re-plan.

## Repository strategy

Use separate branches/worktrees:

### Zo Media
Repo: `jagzao/zo_whisper2`
Base: current `feat/kab-local-ingest-v1`
Implementation branch:
`feat/zmi-knowledge-to-action-v1`

### Zavi
Repo: `jagzao/zavi`
Base: current `main`
Implementation branch:
`feat/knowledge-scope-publishing-v1`

### KAV
Repo: `jagzao/zavi-kab`
Base: current `main`
Implementation branch:
`feat/knowledge-bound-skills-v1`

Do not merge during implementation.

## WP-01 — Zo project knowledge configuration

Files:
- `src/transcript_pipeline/projects.py`
- `projects.json.example`
- project API/dashboard validation tests if project editor exposes these fields.

Implement:
1. constants/enums:
   - `KnowledgeScope = PROJECT|GLOBAL`;
   - `KnowledgeActionability = REFERENCE|GUIDED|EXECUTABLE`;
   - `KnowledgeArtifactType`.
2. validate optional `second_brain` object.
3. publishing disabled when absent.
4. default fail-closed scope = PROJECT for enabled project unless explicitly GLOBAL.
5. confidential + GLOBAL => validation error.
6. do not infer scope from data_classification.
7. add portable examples:
   - confidential project/private brain;
   - public generic tutorials/global.

Tests:
- valid/invalid matrix;
- legacy project compatibility;
- unknown enum;
- missing project id;
- confidential/global blocked.

## WP-02 — Knowledge Package v2 domain model

Create package:
`src/transcript_pipeline/knowledge/`

Suggested files:
- `__init__.py`
- `models.py`
- `identity.py`
- `policy.py`
- `package_builder.py`

Modify:
- `src/transcript_pipeline/documentation/models.py`
- `src/transcript_pipeline/documentation/engine.py`

Implement frozen SPEC:
- typed package model;
- package/source/knowledge IDs;
- procedure model;
- bounded evidence excerpts;
- explicit rawTranscriptPublished=false/rawMediaPublished=false;
- stable canonical JSON hash;
- version fields;
- optional supersedes id.

Do not require action/target to be known.
Existing AI package files remain backward compatible.

New outputs:
- `ai-package/knowledge-package.json`
- `ai-package/procedure.json` when applicable.

## WP-03 — Durable knowledge outbox

Create:
- `src/transcript_pipeline/knowledge/outbox.py`
- `src/transcript_pipeline/knowledge/publisher.py`
- `src/transcript_pipeline/knowledge/ledger.py`

Data root:
`DATA_ROOT/knowledge-outbox`

States:
- pending;
- publishing;
- published;
- failed.

Rules:
- atomic write/replace;
- packageId idempotency;
- bounded attempt count;
- exponential/bounded backoff;
- no busy loop;
- publisher failure never corrupts documentation;
- terminal failures remain inspectable.

Transport interface only; no Supabase key.

Adapters:
- `FilePublisher` for deterministic/local test;
- `ZaviApiPublisher` behind explicit configuration.

## WP-04 — Hook documentation completion to outbox

At the point where AI package is successfully generated:
1. determine matched project + second_brain config;
2. if disabled -> no-op;
3. build package;
4. write package files;
5. enqueue outbox record atomically;
6. optionally wake publisher.

Do not:
- enqueue before documentation is valid;
- fail the media pipeline merely because remote publisher is unavailable;
- publish raw transcripts.

K'ab consolidated session path must call the same builder, not a second knowledge implementation.

## WP-05 — K'ab explicit project identity

Files likely:
- `src/transcript_pipeline/kab_ingest/server.py`
- `store.py`
- validation/models/settings modules;
- K'ab tests/docs.

Add backwards-compatible optional session metadata:
- `projectKey`;
- optional explicit artifact type if sender provides it.

Store it atomically in session metadata.

Add safe authenticated project catalog endpoint only if needed for Android sender:
- key;
- display name;
- scope default;
- artifact default.

No paths/prompts/secrets.

If old session has no projectKey:
- preserve processing;
- publishing uses existing deterministic routing only when a matching project can be proven;
- otherwise publishing disabled for that session rather than guessing.

## WP-06 — Zavi shared scope types

Repo: zavi.

Create module:
`src/features/knowledge/knowledgeScope.ts`

Define:
- `KnowledgeScope`;
- `KnowledgeActionability`;
- artifact types;
- parsers/guards;
- reserved global storage partition constant.

Do NOT modify or reuse:
`LearningScope`.

Update types:
- `src/features/knowledge/ragTypes.ts`;
- `src/features/knowledge/chunker.ts`;
- `src/features/knowledge/vectorStore.ts`;
- normalized Second Brain boundary types as required.

## WP-07 — Zavi additive DB migration

Create new migration after current latest timestamp.

Evidence plane:
add columns to documents/chunks:
- knowledge_scope;
- actionability;
- origin_project_id;
- knowledge_id;
- knowledge_version;
- package_id;
- artifact_type.

Defaults:
- existing documents/chunks -> PROJECT, preserving exact old retrieval behavior.

Indexes:
- owner + scope + project + status;
- package id unique/idempotency where appropriate;
- knowledge id/version.

Canonical plane:
add:
- knowledge_scope default GLOBAL;
- scope_project_id;
- actionability default REFERENCE;
- knowledge logical identity/version.

Extend knowledge entry enum only for types actually promoted in this feature:
- PROCEDURE;
- TUTORIAL;
- TROUBLESHOOTING;
- POLICY;
- REFERENCE
if migration compatibility permits. Otherwise keep producer artifact type separate in content metadata and defer enum extension; do not map all procedures to unrelated legacy types.

No destructive migration.

## WP-08 — Zavi import boundary

Create:
`src/app/api/knowledge/import/route.ts`

Create supporting:
- `src/features/knowledge/importSchema.ts`
- `src/features/knowledge/packageImporter.ts`

Behavior:
1. authenticate with server-side ingest credential;
2. strict Zod parse;
3. reject confidential GLOBAL;
4. resolve storage partition:
   - PROJECT -> active package project;
   - GLOBAL -> reserved global partition;
5. idempotency by packageId;
6. create/update knowledge document;
7. map derived text to existing chunk pipeline;
8. use existing embedding provider/index/update semantics;
9. return structured ACK:
   - IMPORTED;
   - ALREADY_IMPORTED;
   - UPDATED;
   - REJECTED;
   - RETRYABLE_FAILURE.

Never accept Supabase service-role credentials from client package.

## WP-09 — Scoped RAG retrieval

Modify:
- `src/features/knowledge/projectRetrieval.ts`;
- hybrid/vector helpers;
- migration RPC.

Lexical retrieval:
- fetch GLOBAL partition + active project partition;
- validate scope/project combination after row parse;
- exclude rejected/superseded.

Vector:
- add new RPC rather than silently breaking old function;
- query allowed scope union;
- owner isolation retained.

No active project:
- GLOBAL only.

Update rank model only if necessary; scope itself gives no relevance bonus.

## WP-10 — Normalized Second Brain scope

Modify:
- `src/features/secondBrain/knowledgeEntry.ts`;
- `src/features/secondBrain/secondBrainRetrieval.ts`;
- direct callers.

Add optional activeProject input to retrieval.

Filter:
- GLOBAL;
- PROJECT matching activeProject.

Fail closed:
- PROJECT row with no scope project is skipped;
- no active project excludes PROJECT rows.

Existing curated rows continue as GLOBAL.

Do not conflate with `learning_scope`.

## WP-11 — Promotion/version/supersede

Implement service-level functions:
- promoteProjectKnowledgeToGlobal;
- supersedeKnowledge;
- deprecateKnowledge.

Promotion:
- explicit owner/review action;
- sanitized replacement content supplied;
- new GLOBAL knowledge identity/version;
- original private evidence untouched;
- append provenance link.

Supersede:
- mark old status superseded/deprecated;
- vector retrieval excludes old;
- any derived skill candidate becomes SUPERSEDED/disabled.

No fuzzy automatic supersede.

## WP-12 — Procedure registry / skill candidate

Zavi side:
create a procedure/skill-candidate boundary model from package procedure.

A candidate may be generated only when:
- artifact type procedural;
- actionability EXECUTABLE;
- required procedure data valid.

Candidate does NOT imply validated.

It carries:
- knowledge ref/version/scope/project;
- evidence refs;
- required capability identifiers;
- parameters;
- proposed risk/approval.

If capability mapping is unknown:
- candidate remains CANDIDATE;
- procedure remains GUIDED.

## WP-13 — KAV knowledge-bound skill model

Repo: zavi-kab.

Modify:
`shared-core/src/commonMain/kotlin/com/zavikab/shared/skills/Skills.kt`

Prefer additive types to avoid breaking existing M13/M14 API:
- `KnowledgeRef`;
- `SkillValidationStatus`;
- `CapabilityRequirement`;
- `ApprovalPolicy`;
- `Precondition`;
- `Postcondition`;
- `RollbackPolicy`;
- `ExecutionReceipt`;
- knowledge-bound skill metadata.

Extend `SkillSource` with KNOWLEDGE if backward-compatible.

Only validated knowledge-bound skill gets a handler registration usable for execution.

## WP-14 — KAV execution guard

Before handler execution:
1. validate active scope/project;
2. validate skill status;
3. validate required capabilities;
4. validate required args;
5. validate runtime policy;
6. obtain required approval;
7. validate preconditions;
8. execute handler;
9. validate postconditions;
10. write receipt.

Structured failures:
- SCOPE_DENIED;
- SKILL_NOT_VALIDATED;
- CAPABILITY_MISSING;
- APPROVAL_REQUIRED;
- PRECONDITION_FAILED;
- EXECUTION_FAILED;
- POSTCONDITION_FAILED.

Raw knowledge text is never interpreted as a shell/browser command.

## WP-15 — Azure Data Factory proof without real cloud mutation

Use existing Azure Data Factory knowledge seed only as domain fixture/reference.

Deterministic test capability:
`fake.azure.datafactory.createPipeline`

Create a GLOBAL EXECUTABLE procedure and bind it to fake capability.

Acceptance:
- skill candidate initially cannot execute;
- validate/bind;
- execute with required params;
- fake tool records expected typed call;
- postcondition passes;
- receipt references knowledge/procedure versions.

Real Azure connector/API/MCP implementation is a separate adapter/US, because credentials, tenant/subscription and destructive policy require explicit environment configuration.

## WP-16 — Cross-repo contract fixtures

Commit the same JSON fixture version in a neutral contract test form (not copied production logic):
- valid P&G PROJECT package;
- valid Azure GLOBAL package;
- confidential GLOBAL invalid package;
- superseded procedure;
- validated skill fixture.

Each repo validates against its own parser but fixture semantics must match.

## WP-17 — Observability

Zo:
- pending/published/failed counts;
- last publisher result;
- package id.

Zavi:
- imports by status;
- duplicate idempotent imports;
- scope rejects;
- embedding failures.

KAV:
- skill selection result;
- denied reason;
- execution/verification receipt.

Never log:
- bearer/ingest tokens;
- cloud credentials;
- entire confidential transcript.

## WP-18 — Documentation

Zo:
- update project config docs;
- Knowledge Package schema;
- outbox/publisher operations.

Zavi:
- Second Brain scope semantics;
- distinction KnowledgeScope vs LearningScope;
- import/retrieval architecture.

KAV:
- knowledge-bound skill lifecycle;
- security/approval model.

Create ADR:
`Knowledge is not executable authority`.

## WP-19 — Final deterministic acceptance

Run each repo's normal unit/type/lint/security gates plus the cross-repo contract matrix.

No LLM watches test runs.

When complete:
- commit/push each implementation branch;
- generate compact summaries;
- STOP for heavy-model `/review`.

## Implementation model policy

Implementation MUST be launched directly from a normal shell through OpenCode/Z.ai GLM Coding Plan.

No Codex/GPT agent may supervise or orchestrate the implementation.

The implementation worker:
- reads frozen artifacts;
- codes;
- performs only bounded mechanical repairs;
- triggers deterministic tests;
- exits.

Any design ambiguity returns `REVIEW_REQUIRED` for owner + heavy model here.
