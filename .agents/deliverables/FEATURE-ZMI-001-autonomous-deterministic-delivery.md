# FEATURE-ZMI-001 — Autonomous Deterministic Delivery

## Outcome

Project-lead can execute a frozen US with minimal owner intervention, route work across configured model pools, and rely on deterministic tools for repeated validation.

## Required behavior

- Product/architecture/UX decisions originate from owner + external analysis and are frozen in Git.
- `STRONG_PLANNER`: planning/replanning only.
- `PRIMARY_CODER`: OpenCode Go.
- `FREE_WORKER`: Ollama local.
- `SECONDARY_CODER`: Ollama Pro / Ollama Cloud.
- Routine validation uses deterministic tools, not LLM judgment.
- Project-lead/worker runtime denies routine `question` / `doom_loop` owner prompts.
- Crash/session restart resumes from checkpoint + Git state.
- Jenkins handles local/long-running workflows; GitHub Actions handles public PR gates.
- SonarQube supplies static-quality evidence when configured.
