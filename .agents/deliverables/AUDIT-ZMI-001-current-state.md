# AUDIT-ZMI-001 — Current State and Completion Backlog

## Snapshot

Audit date: 2026-09-26

Product: **Zo Media Intelligence**

Public positioning: local-first multimodal media intelligence that turns screen recordings into evidence-grounded documentation and AI-ready knowledge.

Baseline branch: `main` at `f14ed96b76d2ea48b137eb1910ccc68f7d347ff5`.

This audit is the factual source for the final-completion epic. It separates release blockers from future work and avoids carrying unsafe history from abandoned branches.

## Repository topology

| Ref | Classification | Action |
|---|---|---|
| `main` | Product baseline | Keep protected; final completion merges here only after audit |
| `feat/project-lead-v4-autonomous-delivery` / PR #23 | Partial V4 experiment | Do **not** merge directly; port only reviewed/sanitized work to clean branch |
| `release/v1.1.0-community-launch` | Stale release branch | No unique product code required for final release; delete after final merge |
| `fix/security-fail-closed-git` | Stale fix branch | Underlying fail-closed security behavior already exists on main; delete after final merge |
| Dependabot branches/PRs | Dependency maintenance | Evaluate independently after release gates; do not mix blindly into final-completion diff |

### Why PR #23 is not the final integration branch

PR #23 demonstrated useful Project-lead V4 behavior and produced the first deterministic gate runner, but:
- it is incomplete (Jenkins/Sonar/provider/runtime enforcement unfinished);
- its pushed history contains an accidentally introduced private denylisted identifier;
- OpenCode workers repeatedly interrupted the owner through the native `question` tool;
- the Bun/OpenCode host crashed during a write and left partial files before recovery.

Therefore the final implementation is built from clean `main` and ports only sanitized, reviewed V4 changes.

## Product capabilities already present

- Local faster-whisper transcription.
- FFmpeg/ffprobe media processing and retry handling.
- Tesseract OCR / frame evidence.
- Real keyframe PTS mapping.
- Evidence-grounded Documentation Engine.
- `MANUAL.md` + `MANUAL.pdf`.
- AI-ready `knowledge.md`, `chunks.jsonl`, `steps.json`, `manifest.json`.
- Flask/Jinja/HTML/CSS/Vanilla JS dashboard.
- Eight-stage pipeline status.
- Frame thumbnails, timestamp seek and lightbox.
- Edit File with logical Project assignment.
- Generate/View Documentation separation.
- Project override persistence.
- File-table pagination/filter preservation.
- Localhost/token/filesystem security boundary.
- Privacy-gated optional external LLM.
- Unit/integration/security/Playwright coverage and synthetic marketing assets.

## Findings

### P0 — release blockers

#### BUG-ZMI-001 — Edit File is not atomic
The combined transcription + Project assignment endpoint can persist the transcription and return `ok: true` even when the Project override fails to persist.

Expected: all-or-nothing logical save with rollback and HTTP 5xx on persistence failure.

#### BUG-ZMI-002 — Project rename/delete is not atomic with overrides
`projects.json` can be committed while override migration/cleanup fails, leaving inconsistent state while the API still returns success.

Expected: transaction-like snapshot/write/rollback behavior.

#### BUG-ZMI-003 — public CI contract and repository reality disagree
README/SECURITY/CONTRIBUTING advertise CI/Gitleaks/GitHub Actions, branch protection expects named checks, but `.github/workflows/` is absent and LOCAL-OPS says Actions are disabled.

Expected: restore lightweight public PR CI or change all documentation/branch rules coherently. For an open-source community launch, this epic restores lightweight PR CI and keeps heavy/long-running validation local in Jenkins.

#### BUG-ZMI-004 — Project-lead V4 owner-interruption policy is not runtime-enforced
The policy says routine questions are forbidden, but autonomous workers can invoke OpenCode's native `question` tool and block the owner.

Expected: project-scoped OpenCode agent definitions deny routine `question` and `doom_loop` prompting for the orchestrator/workers; legitimate blockers terminate with typed V4 states.

### P1 — must close before community launch

#### GAP-ZMI-001 — V4 deterministic toolchain incomplete
Need clean implementation of:
- compact gate runner;
- Jenkins pipeline;
- SonarQube config;
- provider aliases;
- zero-LLM repeat proof;
- crash-resume rules;
- deterministic artifact policy.

#### GAP-ZMI-002 — restart/recovery acceptance is mostly simulated
Existing unit tests validate state reset and atomic file replacement but do not prove a real process stop/start lifecycle.

Need an isolated process-level recovery smoke that starts the dashboard on a free port, verifies state, terminates it, restarts it and confirms usable state/no stale running flag. A destructive mid-transcription kill remains a heavier soak/manual acceptance scenario.

#### GAP-ZMI-003 — community repository surface incomplete
Need:
- issue templates;
- PR template;
- Code of Conduct;
- truthful CI/community docs;
- contribution entry points suitable for first external contributors.

Repository rename/description/topics/Discussions/GitHub Release are repository-setting operations performed only after final code acceptance.

#### GAP-ZMI-004 — fresh-install/release proof
Need one documented clean-environment install/smoke path that validates `.[studio]`, dashboard boot, FFmpeg detection, optional Tesseract behavior and synthetic demo flow without relying on the maintainer's existing venv.

### P2 — post-release technical debt

#### TECHDEBT-ZMI-001 — experimental trees remain in the repository
`watcher/` and `deepseek/` are explicitly non-production but large. Keep excluded from product packaging/Sonar/release gates; evaluate extraction/archive in a later cleanup epic.

#### TECHDEBT-ZMI-002 — CPU-only default
Intentional and documented. GPU acceleration can be a future feature; not a release blocker.

#### TECHDEBT-ZMI-003 — single-process architecture
Intentional local-first design. Do not introduce Redis/Celery/Kubernetes merely for scale that the product does not claim.

### P3 — future commercial readiness

#### FEATURE-TRUST-001 — Enterprise Trust Readiness
Future, not required for v1.1.0:
- control matrix;
- SBOM provenance;
- change/access/incident/backup/vendor policy skeletons;
- evidence export suitable for later SOC 2 / ISO 27001 preparation.

Do not claim SOC 2 compliance without an independent attestation.

## Release target

The project is considered ready for the first community/LinkedIn launch when:
- P0/P1 findings above are closed with deterministic evidence;
- clean branch has no private denylist hits in tree/history;
- all release gates are green;
- README/security/contributor claims match reality;
- final owner local acceptance passes.

Repository metadata operations (rename to `zo-media-intelligence`, description, topics, Discussions, tag/release) occur after that final owner acceptance.
