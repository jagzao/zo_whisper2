# EPIC-PLV4 — Autonomous Delivery with Minimal Owner Intervention

## Decision

Evolve project-lead to V4 around four principles:

1. Product/architecture/UX reasoning is performed by the owner with ChatGPT/Claude and persisted in Git before autonomous implementation.
2. Expensive models plan; coding models implement; local/cheap workers handle mechanical work.
3. Repeated validation is deterministic and consumes zero LLM tokens.
4. Normal owner intervention budget is two touchpoints: initial specification and final acceptance.

## Model topology

- STRONG_PLANNER — configurable strong model; plan/re-plan only; no production code.
- PRIMARY_CODER — OpenCode Go.
- FREE_WORKER — Ollama local.
- SECONDARY_CODER — Ollama Pro / Ollama Cloud.

## Validation topology

Existing deterministic tools remain authoritative:
- pytest
- Ruff
- Pyright
- security.py / pip-audit / Gitleaks
- FFmpeg/ffprobe
- Playwright

Target integrations:
- Jenkins for local/long-running/nightly orchestration.
- SonarQube for deterministic static-quality findings.
- GitHub Actions/public PR checks where enabled.

Electron is used only by Electron products; Zo Media Intelligence remains Playwright Chromium.

## Owner experience

Normal workflow:

```
OWNER + ASSISTANT ANALYSIS
 -> frozen EPIC/FEATURE/US/ADR in Git
 -> one start prompt
 -> autonomous project-lead execution
 -> READY_FOR_OWNER_AUDIT
 -> external audit
 -> owner final product test
```

No routine "continue?", "which model?", "which test?", or "should I retry?" owner questions.

## Runtime resilience

Checkpoint state under `.agents/session/` and `.agents/memory/` stays local and gitignored. Forced session boundaries resume from checkpoint rather than restart planning.

## Follow-up implementation

The protocol files in this EPIC define the V4 behavior immediately. Repository-level Jenkins/Sonar/compact-gate tooling should be delivered under a separate frozen implementation US so V4 itself is the orchestrator that implements and validates its deterministic toolchain.
