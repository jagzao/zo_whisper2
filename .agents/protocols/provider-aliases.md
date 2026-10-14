# Provider Alias Mapping

Project-lead roles are runtime aliases. Configure them in the local provider
orchestrator; do not commit credentials, private endpoints, or machine-specific
configuration.

| Alias | Default role target | Configuration |
|---|---|---|
| `STRONG_PLANNER` | Owner-authorized strong planning model | Set in local orchestrator config; planning only. |
| `PRIMARY_CODER` | OpenCode Go | Set the OpenCode model/provider locally. |
| `FREE_WORKER` | Ollama local | Set the installed local Ollama model locally. |
| `SECONDARY_CODER` | Ollama Pro / Ollama Cloud | Set the available secondary model locally. |

The repository does not assume that these providers are installed or authorized
in every runtime. Use the configured role pool and follow
`.agents/protocols/model-routing.md` when a pool is unavailable.
