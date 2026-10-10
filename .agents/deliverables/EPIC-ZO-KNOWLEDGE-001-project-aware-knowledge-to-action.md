# EPIC-ZO-KNOWLEDGE-001 — Project-aware Knowledge-to-Action

## Goal

Turn Zo Media Intelligence output into durable, scoped, provenance-rich Second Brain knowledge and allow KAV to execute validated procedures derived from that knowledge.

## Repositories

- Producer: `jagzao/zo_whisper2`
- Knowledge consumer/storage: `jagzao/zavi`
- Execution consumer: `jagzao/zavi-kab`

## Product outcomes

### Outcome A — Project-private knowledge
A P&G tutorial/KT capture is published to Second Brain with:

```
scope = PROJECT
projectId = p-g
```

It can be retrieved by Zavi/KAV only while `p-g` is active.

### Outcome B — Global technical knowledge
A generic tutorial, e.g. Azure Data Factory, may be explicitly published with:

```
scope = GLOBAL
```

It becomes available to all projects.

### Outcome C — Procedure knowledge
A tutorial may generate an evidence-grounded procedure with stable step provenance.

### Outcome D — Executable skills
A procedure marked EXECUTABLE may become a KAV skill only after capability binding + validation + policy checks.

## Architecture

```
Media / K'ab session
      |
      v
Zo Media Intelligence
  transcription / OCR / frames
      |
      v
Documentation Engine
  manual + AI package
      |
      v
Knowledge Package v2
  scope / project / provenance / procedure
      |
      v
Durable Outbox
      |
      v
Knowledge Publisher Adapter
      |
      v
Zavi import boundary
      |
      +-----------------------+
      |                       |
      v                       v
Evidence Plane           Canonical Plane
docs/chunks              knowledge entries
RAG + embeddings         curated/verified
      |
      v
Procedure Registry
      |
      v
Skill Candidate
      |
      v
KAV Capability Binding
      |
      v
Policy / Approval
      |
      v
Execution + Verification Receipt
```

## Features

### FEATURE-KNOW-001 — Scoped knowledge contract
- `KnowledgeScope = PROJECT | GLOBAL`
- project/domain mapping;
- data-classification compatibility;
- artifact type/actionability;
- package schema v2.

### FEATURE-KNOW-002 — Durable knowledge publishing
- outbox;
- idempotency;
- local ledger;
- transport adapters;
- retries without blocking documentation generation.

### FEATURE-KNOW-003 — Scoped Second Brain ingestion/retrieval
- evidence-plane import;
- GLOBAL + active PROJECT retrieval;
- vector RPC support;
- normalized Second Brain scope support;
- provenance/version/supersede.

### FEATURE-KNOW-004 — Procedural knowledge
- evidence-grounded procedure contract;
- bounded transcript/OCR refs;
- deterministic stable ids/versioning;
- no automatic executable authority.

### FEATURE-KNOW-005 — KAV knowledge-bound skills
- skill candidate;
- knowledge provenance;
- capability requirements;
- validation status;
- project scope enforcement;
- approvals/pre/postconditions.

### FEATURE-KNOW-006 — Execution receipts
- structured outcome evidence;
- no automatic truth promotion;
- future confidence/learning input.

## Delivery phases

### Phase 1 — Knowledge publishing + retrieval
Vertical slice:
- P&G project-only tutorial;
- generic Azure tutorial global;
- both ingested into Zavi;
- isolation proven.

### Phase 2 — Procedure + skill candidate
- procedure contract;
- skill candidate generation;
- no real external mutation.

### Phase 3 — KAV validated execution
- fake deterministic capability first;
- then one real low-risk tool binding;
- Azure Data Factory real binding is a separate controlled adapter if credentials/tools exist.

## Non-goals for first implementation

- autonomous PROJECT -> GLOBAL promotion;
- raw transcript/VTT ingestion;
- raw media upload;
- arbitrary browser-coordinate replay from video;
- automatic credential acquisition;
- automatic execution of unreviewed procedures;
- multi-user tenancy redesign;
- replacing existing Zavi RAG or Second Brain;
- using an LLM to decide privacy scope.
