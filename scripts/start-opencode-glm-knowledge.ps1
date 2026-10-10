param(
    [string]$Model = "zai-coding-plan/glm-5.2"
)

$ErrorActionPreference = "Stop"

$ExpectedBranch = "feat/zmi-knowledge-to-action-v1"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Set-Location $Repo

if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) {
    throw "OpenCode CLI no esta disponible en PATH."
}

git fetch origin | Out-Host

$current = (git branch --show-current).Trim()
if ($current -ne $ExpectedBranch) {
    git switch $ExpectedBranch | Out-Host
}

git pull --ff-only origin $ExpectedBranch | Out-Host

$current = (git branch --show-current).Trim()
if ($current -ne $ExpectedBranch) {
    throw "FAIL_CLOSED: rama incorrecta: $current"
}

$modelList = (opencode models zai-coding-plan 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "FAIL_CLOSED: no se pudo consultar zai-coding-plan."
}
if ($modelList -notmatch [regex]::Escape($Model)) {
    throw "FAIL_CLOSED: el modelo requerido $Model no esta disponible en zai-coding-plan."
}

# Highest normal runtime override. This prevents a global/project default from
# silently selecting Codex/OpenAI for the main or small-model path.
$runtimeConfig = @{
    model = $Model
    small_model = $Model
    default_agent = "implementation-worker"
    subagent_depth = 0
    permission = @{
        task = "deny"
        webfetch = "deny"
        websearch = "deny"
        question = "deny"
        doom_loop = "deny"
        external_directory = "deny"
    }
} | ConvertTo-Json -Depth 5 -Compress

$env:OPENCODE_CONFIG_CONTENT = $runtimeConfig
$env:OPENCODE_AUTO_SHARE = "false"

Write-Host ""
Write-Host "OPENCode implementation runtime:"
Write-Host "  branch: $ExpectedBranch"
Write-Host "  provider/model: $Model"
Write-Host "  agent: implementation-worker"
Write-Host "  subagents: disabled"
Write-Host "  external plugins: disabled (--pure)"
Write-Host "  external directories: denied"
Write-Host ""
Write-Host "In OpenCode paste:"
Write-Host "Implementa completamente LOCAL-CODER-ZO-KNOWLEDGE-001. No analices ni replantees. Trabaja hasta el estado terminal definido, commit, push y termina."
Write-Host ""

# IMPORTANT: this starts OpenCode itself. It does not start Codex and does not
# wrap OpenCode inside another LLM agent.
& opencode --pure . --model $Model --agent implementation-worker

$exitCode = $LASTEXITCODE
Remove-Item Env:OPENCODE_CONFIG_CONTENT -ErrorAction SilentlyContinue
exit $exitCode
