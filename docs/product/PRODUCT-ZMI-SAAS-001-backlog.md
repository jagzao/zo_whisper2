# PRODUCT-ZMI-SAAS-001 — SaaS market, pricing, abuse control and security analysis

## Status
BACKLOG / PAUSED

## Decision
Do NOT start SaaS implementation yet.

Current priority is Documentation Synthesis V2 and reaching a documentation experience competitive with products such as Scribe/Guidde.

The SaaS analysis is preserved here for later product work.

## Product positioning

Zo Media Intelligence should not compete as "another transcription tool".

Target positioning:

> Turn recordings, screen captures, meetings and tutorials into structured, evidence-backed, reusable knowledge.

Potential evolution:

```
Capture
  -> Understand
  -> Document
  -> Remember
  -> Act
```

Product layers:

```
Zo Media Intelligence
  transcription + screen evidence + OCR + semantic documentation

Zavi
  project/global knowledge + retrieval + Second Brain

KAV
  validated procedural knowledge -> capabilities -> execution
```

## Competitive frame

Primary direct/adjacent competitors identified:
- Microsoft Teams / Intelligent Recap
- Otter
- Fireflies
- Fathom
- tl;dv
- Loom AI
- Scribe
- Guidde

Most important direct benchmark for the current product phase:
- Scribe
- Guidde
- Loom AI

Zo should differentiate through:
- media beyond a single meeting platform;
- screen evidence + OCR;
- evidence-grounded semantic documentation;
- project-scoped knowledge;
- local/private processing option;
- Knowledge Library / RAG;
- future Knowledge-to-Action with KAV.

## Commercial model hypothesis

Preferred direction:
SaaS or hybrid SaaS, not only a standalone local license.

Potential architecture:

```
SaaS control plane
  |
  +-- cloud worker
  +-- private worker
  +-- local worker
```

This preserves local/private processing as an enterprise differentiator.

## Pricing hypothesis — NOT FINAL

Goal: affordable for micro/small businesses while keeping healthy gross margin.

Possible future tiers to validate, not publish yet:
- Trial: limited lifetime minutes
- Starter: low monthly price, small media-hour allowance
- Pro: larger allowance + Knowledge Library
- Team: shared projects/roles
- Business: private worker / retention / enterprise controls

Pricing should be based on measured COGS per media hour before final numbers are chosen.

Target business rule:
- normal-use gross margin >= 70–80%.

## Usage / financial firewall

Do NOT allow uncontrolled post-paid overage.

Use:
- prepaid credits / included processing allowance;
- hard quota;
- reservation before job start;
- settlement after actual usage.

Flow:

```
upload
 -> ffprobe/duration estimate
 -> estimate cost
 -> reserve credits
 -> queue
 -> process
 -> settle actual usage
 -> refund unused reservation
```

If user has insufficient balance:
- reject/pause before processing;
- offer credit purchase/upgrade.

Never allow a low-price account to create unlimited provider/cloud spend.

## Usage ledger

Future SaaS should maintain its own internal authoritative ledger, not rely only on billing-provider asynchronous metering.

Candidate entities:
- organizations
- subscriptions
- plans
- usage_wallets
- usage_reservations
- usage_transactions
- jobs
- job_costs
- provider_usage
- storage_usage

Per-job metrics:
- media minutes
- CPU seconds
- OCR frames
- LLM input/output tokens
- storage
- bandwidth
- reserved credits
- actual credits
- infrastructure/provider cost

## Abuse controls

Per-plan hard limits:
- max media duration/job
- max upload size
- monthly processing quota
- concurrent jobs
- daily jobs
- storage quota
- retention
- LLM token cap/job
- retry cap/job

Recommended principle:
- max 2 retries for expensive external work;
- no recursive autonomous processing loops.

Financial circuit breakers:
- tenant quota checks before queue
- provider daily spend warning threshold
- provider hard-stop threshold
- disable optional expensive AI before exceeding budget

## Security / tenancy

Recommended SaaS direction:
- Supabase Auth
- organizations / organization_members
- tenant_id on tenant-owned tables
- RLS on exposed tables
- service-role server-side only
- private object storage
- short-lived signed URLs
- no permanent public media URLs

Protect:
- media
- transcripts
- screenshots
- manuals
- knowledge documents
- embeddings/metadata

Workers should use short-lived job-scoped credentials/tokens, never global service-role/payment/admin secrets.

## Piracy / licensing

Current repository/code already published under MIT cannot later be made unavailable retroactively.

Recommended future commercial model:
open-core SaaS.

Possible open/core:
- local transcription
- FFmpeg/OCR
- evidence capture
- basic local pipeline

Possible private/hosted commercial value:
- SaaS control plane
- multi-tenancy
- billing
- Knowledge Library
- advanced semantic synthesis/templates
- managed knowledge publishing
- analytics
- hosted RAG
- enterprise controls
- KAV cloud/enterprise integrations

Competitive moat should come from product quality, workflow, hosting, knowledge and integrations rather than DRM alone.

## Product rollout recommendation

Do not build full SaaS first.

Preferred sequence:
1. Finish Documentation Synthesis V2.
2. Reach Scribe/Guidde-level human-document quality.
3. Validate with real already-processed recordings via regeneration.
4. Sell 2–3 managed pilots before full SaaS.
5. Benchmark true cost per processed media hour.
6. Finalize pricing/credits.
7. Implement SaaS control plane based on observed customer usage.
8. Add Knowledge Library / Ask Zo.
9. Add KAV Knowledge-to-Action later as premium capability.

## Explicit current priority

PAUSE:
- SaaS control plane implementation
- billing implementation
- final pricing
- marketing plan commitment

P0 NOW:
> Make Zo Media Intelligence generate genuinely useful, concise, professional documentation comparable to Scribe/Guidde, while preserving stronger evidence/provenance.

The current Documentation Synthesis V2 branch is the active product priority.

## Resume trigger

Return to this analysis after Documentation Synthesis V2 passes:
- code review;
- heavy validation;
- human quality gate on real regenerated media;
- acceptable manual quality versus Scribe/Guidde benchmark.

Then create:
`EPIC-ZMI-SAAS-001 — SaaS Control Plane`
and a measured COGS benchmark before implementing pricing/billing.
