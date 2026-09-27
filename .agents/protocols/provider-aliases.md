# Provider Aliases — Project-lead V4

## Purpose

Keep orchestration semantics stable while provider/model availability changes. This repository commits role names and routing policy, never credentials.

## Runtime roles

| Alias | Intended pool | Responsibility |
|---|---|---|
| `STRONG_PLANNER` | owner-authorized high-capability planner | Initial implementation plan and bounded architectural re-plan only |
| `PRIMARY_CODER` | OpenCode Go | Normal production implementation |
| `FREE_WORKER` | Ollama local | Search, mechanical edits, deterministic lint/type/test repairs, docs |
| `SECONDARY_CODER` | Ollama Pro / Ollama Cloud | Overflow, difficult bug, alternative coding attempt |
| `REVIEWER` | configured review model | Independent review of diff/evidence; no product-scope invention |

Provider credentials, account tokens, base URLs and concrete private model IDs belong in the user's OpenCode/Ollama configuration, not in Git.

## Resolution

Project-lead resolves aliases from the locally configured agents/pools. If one pool is unavailable, it automatically routes to the next permitted tier from `model-routing.md`.

A pool failure is not an owner blocker unless every permitted implementation route is unavailable and the remaining dependency genuinely requires owner/account action.

## Owner-analysis boundary

Product/architecture/UX analysis is performed by the owner with ChatGPT/Claude outside the autonomous implementation loop and committed as frozen EPIC/FEATURE/US/ADR artifacts.

Autonomous `STRONG_PLANNER` consumes that frozen scope. It may plan implementation but cannot redefine product decisions.

## Interaction enforcement

Project-level `opencode.json` denies OpenCode's native `question` and `doom_loop` prompts. Legitimate V4 blockers are reported as typed terminal states in normal text rather than interactive owner prompts.

This is intentionally project-wide so child workers cannot reintroduce routine owner interruptions through permissive defaults.
