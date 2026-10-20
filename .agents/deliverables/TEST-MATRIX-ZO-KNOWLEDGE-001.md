# TEST-MATRIX-ZO-KNOWLEDGE-001 — Knowledge-to-Action Acceptance

## Principle

No implementation worker may weaken these checks.
A failing gate is evidence for heavy-model review, not permission to redefine behavior.

## Zo Media Intelligence

| ID | Test | Expected |
|---|---|---|
| ZK-01 | legacy project without second_brain | publishing disabled; existing behavior unchanged |
| ZK-02 | PROJECT config with project id/domain | valid |
| ZK-03 | PROJECT config missing project id | rejected |
| ZK-04 | GLOBAL public tutorial config | valid |
| ZK-05 | confidential + GLOBAL | rejected |
| ZK-06 | unknown scope/actionability/type | rejected |
| ZK-07 | package v2 deterministic same input | identical canonical packageId |
| ZK-08 | reprocess unchanged source | outbox logical no-op/idempotent |
| ZK-09 | changed derived package same knowledgeId | version increments |
| ZK-10 | new recording | does not auto-supersede |
| ZK-11 | package contains no raw media bytes/path export | PASS |
| ZK-12 | package contains no whole raw transcript/VTT | PASS |
| ZK-13 | bounded transcript/OCR evidence retained | PASS |
| ZK-14 | procedure preserves timestamps/confidence/review/evidence | PASS |
| ZK-15 | procedural semantic action may be null | valid |
| ZK-16 | documentation succeeds while publisher unavailable | PASS + pending/failed outbox |
| ZK-17 | outbox crash between write/move | no partial published state |
| ZK-18 | bounded retry | no infinite loop |
| ZK-19 | K'ab explicit projectKey persists | PASS |
| ZK-20 | old K'ab session without projectKey | processing works; no unsafe guessed publishing |

## Zavi import/storage

| ID | Test | Expected |
|---|---|---|
| ZV-01 | valid P&G PROJECT package | imported |
| ZV-02 | same package twice | second = ALREADY_IMPORTED; no duplicate chunks |
| ZV-03 | valid GLOBAL package | imported into global partition |
| ZV-04 | confidential GLOBAL | rejected |
| ZV-05 | malformed enum/schema | rejected |
| ZV-06 | raw transcript/media forbidden field | rejected/fail closed |
| ZV-07 | embedding failure during replacement | last-good source preserved |
| ZV-08 | version update | changed chunks replace atomically |
| ZV-09 | explicit supersede | old excluded from active retrieval |
| ZV-10 | existing pre-migration docs | remain PROJECT and behave as before |

## Retrieval isolation

| ID | Active project | Available data | Expected |
|---|---|---|---|
| RT-01 | p-g | GLOBAL + P&G + Gravity | GLOBAL + P&G only |
| RT-02 | gravity | GLOBAL + P&G + Gravity | GLOBAL + Gravity only |
| RT-03 | none | GLOBAL + P&G | GLOBAL only |
| RT-04 | p-g | superseded P&G v1 + active v2 | v2 only |
| RT-05 | p-g | normalized global + normalized P&G | both |
| RT-06 | gravity | normalized P&G | no P&G hit |
| RT-07 | any | malformed PROJECT without project id | skipped/fail closed |

Run RT-01..07 for both lexical and vector paths where applicable.

## Promotion

| ID | Test | Expected |
|---|---|---|
| PR-01 | automatic PROJECT->GLOBAL request | denied |
| PR-02 | owner promotion with sanitized content | new GLOBAL artifact |
| PR-03 | original PROJECT after promotion | remains intact/private |
| PR-04 | confidential source without reclassification | promotion denied |
| PR-05 | promoted artifact provenance | links source without exposing private body |

## Procedure/actionability

| ID | Test | Expected |
|---|---|---|
| PC-01 | REFERENCE | retrievable, no skill candidate |
| PC-02 | GUIDED | retrievable/guidable, no executable skill |
| PC-03 | EXECUTABLE unbound | candidate only |
| PC-04 | unknown semanticAction | remains candidate/guided |
| PC-05 | procedure evidence | exact knowledge/version/source refs |
| PC-06 | superseded procedure | no new execution |

## KAV skills

| ID | Test | Expected |
|---|---|---|
| KV-01 | CANDIDATE invoked | SKILL_NOT_VALIDATED |
| KV-02 | VALIDATED but missing capability | CAPABILITY_MISSING |
| KV-03 | PROJECT p-g skill under gravity | SCOPE_DENIED |
| KV-04 | PROJECT p-g skill under p-g | may continue |
| KV-05 | GLOBAL skill under any project | may continue |
| KV-06 | required param missing | structured failure, no handler call |
| KV-07 | approval required but absent | APPROVAL_REQUIRED |
| KV-08 | failed precondition | no handler call |
| KV-09 | fake ADF capability success | handler receives typed expected params |
| KV-10 | failed postcondition | POSTCONDITION_FAILED + receipt |
| KV-11 | success | SUCCESS receipt with knowledge+skill versions |
| KV-12 | credential material in knowledge spec | parser/review rejects or no credential field exists |
| KV-13 | raw prose cannot invoke shell/browser directly | PASS |

## Cross-repo vertical E2E

### E2E-KNOW-01 — P&G privacy
1. build P&G tutorial package;
2. scope PROJECT/project=p-g;
3. publish/import;
4. retrieve under p-g -> found;
5. retrieve under gravity -> not found;
6. retrieve no project -> not found.

### E2E-KNOW-02 — Global Azure tutorial
1. build generic Azure Data Factory tutorial package;
2. scope GLOBAL;
3. publish/import once;
4. retrieve under p-g -> found;
5. retrieve under gravity -> found;
6. duplicate publish -> no duplicate.

### E2E-KNOW-03 — Knowledge to action
1. GLOBAL Azure procedure actionability EXECUTABLE;
2. create skill candidate;
3. invocation before validation -> denied;
4. bind deterministic fake ADF capability;
5. mark validated;
6. require BEFORE_WRITE approval;
7. approve;
8. execute fake capability;
9. verify postcondition;
10. receipt references exact knowledge/procedure/skill versions.

### E2E-KNOW-04 — Private executable isolation
1. PROJECT p-g procedure;
2. validated fake skill;
3. active gravity -> denied before tool call;
4. active p-g -> allowed after policy/approval.

### E2E-KNOW-05 — Source update
1. import knowledge v1;
2. import unchanged v1 -> no-op;
3. import same knowledge id changed v2;
4. active retrieval returns v2;
5. v1 stays historical/superseded;
6. skill derived from v1 cannot be selected.

## Security negative tests

- no PROJECT cross-project leak through lexical query;
- no PROJECT cross-project leak through vector RPC;
- no normalized Second Brain cross-project leak;
- no prompt-based scope enforcement dependency;
- no GLOBAL confidential import;
- no service-role key in Zo client/config;
- no execution from unvalidated knowledge;
- no shell=True/raw command from tutorial text;
- no automatic owner approval;
- no remote LLM requirement for confidential package generation;
- no raw P&G transcript/VTT ingestion.

## Performance/operability

- import idempotent retry does not re-embed unchanged chunks;
- retrieval global+project remains bounded to current top-K/candidate limits;
- publisher restart resumes outbox;
- one failed package does not block later packages;
- package/import failures have compact typed status.

## Required final evidence

Per repo:
- unit;
- integration;
- typecheck;
- lint;
- security;
- targeted E2E;
- compact SUMMARY.

Cross-repo:
- E2E-KNOW-01..05 results;
- exact branch SHAs;
- migration not applied to production without owner approval;
- no real Azure mutation performed.
