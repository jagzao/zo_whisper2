# DELTA-ZO-KNOWLEDGE-002 — Publisher wakeup + privacy hardening

## Status
FROZEN_FOR_IMPLEMENTATION

## Review findings

The producer implementation generates/enqueues Knowledge Package v2 correctly, but two gaps remain before real P&G use.

### F1 — enqueue does not automatically publish
`publish_knowledge_from_documentation()` only calls `enqueue_knowledge_package()`.
`run_publish_cycle()` exists but no production path wakes it.
Therefore processed documentation can remain forever in `knowledge-outbox/pending` even when Zavi is configured.

### F2 — forbidden raw-field scan is not recursive
`assert_no_forbidden_payload()` checks only top/source/knowledge keys.
Nested evidence must fail closed too.

## Required changes

1. Add a deterministic bounded publish wakeup after successful enqueue WHEN and only when a publisher is explicitly configured:
   - build publisher via `publisher_from_env`;
   - no configured publisher => enqueue-only, success with typed state;
   - configured publisher => run one bounded publish cycle;
   - network/publisher failure never fails documentation;
   - leave retryable packages pending according to existing outbox backoff;
   - maximum immediate cycle budget 15 seconds;
   - no background recursive loop;
   - no LLM.

2. The returned knowledge result must distinguish:
   - ENQUEUED
   - ACK/PUBLISHED
   - PENDING_RETRY
   - TERMINAL_FAILURE
   - SECOND_BRAIN_DISABLED

3. Apply the same behavior to standard documentation and K'ab consolidation through the shared hook only.

4. Make raw-payload detection recursive across dict/list values.
   Forbidden keys anywhere:
   rawTranscript, transcript, vtt, rawVtt, mediaBytes, mediaPath, media.
   Existing bounded `transcriptExcerpt` remains allowed.

5. Add tests:
   - configured fake publisher ACK moves package to published;
   - configured retryable publisher leaves pending/backoff;
   - unconfigured publisher remains enqueue-only;
   - nested rawTranscript/rawVtt/mediaPath rejected;
   - bounded transcriptExcerpt accepted;
   - publisher failure does not fail documentation.

6. Do NOT process real P&G media in this delta.
7. Do NOT add real P&G names/content/secrets to Git.

## Validation now
Targeted tests + Ruff + typecheck/compile only.
No full E2E/Docker.

## Terminal
Commit/push, READY_FOR_CHATGPT_REVIEW.
