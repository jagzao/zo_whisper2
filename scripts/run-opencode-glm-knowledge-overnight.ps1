param(
    [string]$Model = "zai-coding-plan/glm-5.2",
    [string]$DevRoot = "C:\Dev\Zo"
)

$ErrorActionPreference = "Stop"
$RunId = Get-Date -Format "yyyyMMdd-HHmmss"
$RunRoot = Join-Path $DevRoot ".knowledge-overnight\$RunId"
$WorktreeRoot = Join-Path $DevRoot ".worktrees"
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WorktreeRoot | Out-Null

function Write-RunNote {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$stamp] $Message" | Tee-Object -FilePath (Join-Path $RunRoot "master.log") -Append | Out-Host
}

function Test-RepoRemote {
    param([string]$Path, [string]$ExpectedRepo)
    if (-not (Test-Path $Path)) { return $false }
    try {
        $inside = (& git -C $Path rev-parse --is-inside-work-tree 2>$null | Out-String).Trim()
        if ($inside -ne "true") { return $false }
        $remote = (& git -C $Path remote get-url origin 2>$null | Out-String).Trim()
        if (-not $remote) { return $false }
        $needle = [regex]::Escape($ExpectedRepo)
        return $remote -match "$needle(?:\.git)?$"
    } catch {
        return $false
    }
}

function Resolve-RepoRoot {
    param(
        [string]$Preferred,
        [string]$ExpectedRepo
    )

    if (Test-RepoRemote -Path $Preferred -ExpectedRepo $ExpectedRepo) {
        return (Resolve-Path $Preferred).Path
    }

    $candidates = @()
    foreach ($base in @($DevRoot, "C:\Dev")) {
        if (Test-Path $base) {
            $candidates += Get-ChildItem -Path $base -Directory -ErrorAction SilentlyContinue
            foreach ($child in (Get-ChildItem -Path $base -Directory -ErrorAction SilentlyContinue)) {
                $candidates += Get-ChildItem -Path $child.FullName -Directory -ErrorAction SilentlyContinue
            }
        }
    }

    foreach ($candidate in ($candidates | Select-Object -ExpandProperty FullName -Unique)) {
        if (Test-RepoRemote -Path $candidate -ExpectedRepo $ExpectedRepo) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

function Get-ExistingBranchWorktree {
    param([string]$RepoRoot, [string]$Branch)

    $lines = & git -C $RepoRoot worktree list --porcelain 2>$null
    $currentPath = $null
    foreach ($line in $lines) {
        if ($line -like "worktree *") {
            $currentPath = $line.Substring(9)
            continue
        }
        if ($line -eq "branch refs/heads/$Branch" -and $currentPath) {
            return $currentPath
        }
    }
    return $null
}

function Prepare-Worktree {
    param(
        [string]$Name,
        [string]$RepoRoot,
        [string]$Branch
    )

    Write-RunNote "$Name: fetching origin"
    & git -C $RepoRoot fetch origin 2>&1 | Add-Content (Join-Path $RunRoot "$Name-git.log")
    if ($LASTEXITCODE -ne 0) { throw "$Name: git fetch failed" }

    & git -C $RepoRoot show-ref --verify --quiet "refs/remotes/origin/$Branch"
    if ($LASTEXITCODE -ne 0) { throw "$Name: remote branch origin/$Branch not found" }

    $existing = Get-ExistingBranchWorktree -RepoRoot $RepoRoot -Branch $Branch
    if ($existing) {
        Write-RunNote "$Name: using existing worktree $existing"
        return $existing
    }

    & git -C $RepoRoot show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -ne 0) {
        & git -C $RepoRoot branch --track $Branch "origin/$Branch" 2>&1 | Add-Content (Join-Path $RunRoot "$Name-git.log")
        if ($LASTEXITCODE -ne 0) { throw "$Name: could not create local tracking branch" }
    }

    $target = Join-Path $WorktreeRoot "knowledge-$RunId-$Name"
    & git -C $RepoRoot worktree add $target $Branch 2>&1 | Add-Content (Join-Path $RunRoot "$Name-git.log")
    if ($LASTEXITCODE -ne 0) { throw "$Name: git worktree add failed" }

    Write-RunNote "$Name: created isolated worktree $target"
    return $target
}

function New-GlmRuntimeConfig {
    param([string]$SelectedModel)

    return @{
        model = $SelectedModel
        small_model = $SelectedModel
        default_agent = "implementation-worker"
        subagent_depth = 0
        enabled_providers = @("zai-coding-plan")
        permission = @{
            task = "deny"
            webfetch = "deny"
            websearch = "deny"
            question = "deny"
            doom_loop = "deny"
        }
        experimental = @{
            policies = @(
                @{ action = "provider.use"; resource = "*"; effect = "deny" },
                @{ action = "provider.use"; resource = "zai-coding-plan"; effect = "allow" }
            )
        }
    } | ConvertTo-Json -Depth 8 -Compress
}

function Invoke-ImplementationRun {
    param(
        [string]$Name,
        [string]$Worktree,
        [string]$Branch,
        [string]$ContractPath,
        [string]$ReadyStatus
    )

    $log = Join-Path $RunRoot "$Name-opencode.log"
    $prompt = @"
IMPLEMENTATION ONLY. UNATTENDED RUN.

Read and execute the complete frozen contract:
$ContractPath

Also read every frozen SPEC / TEST-MATRIX file referenced by that contract.

The owner + heavy reasoning model already completed product analysis, architecture, security decisions, acceptance criteria and implementation planning.

You are ONLY the implementation worker.

Rules:
- do not analyze or redesign;
- do not re-plan;
- do not change acceptance criteria;
- do not weaken tests;
- do not use web research;
- do not invoke subagents;
- do not ask the owner questions;
- do not change provider/model;
- do not merge or deploy;
- continue all independent implementation and deterministic gates even if another gate fails;
- for the same directly-caused mechanical failure, maximum two repair attempts;
- for product/architecture ambiguity, write REVIEW_REQUIRED evidence and continue independent work;
- for external blockers, record BLOCKED_EXTERNAL and continue independent local work;
- always write artifacts/knowledge-to-action/SUMMARY.json and SUMMARY.md;
- commit and push the implementation branch;
- stop only after all independent work in the contract is exhausted.

Expected branch:
$Branch

Finish with the exact compact terminal output required by the contract.
"@

    Write-RunNote "$Name: starting OpenCode GLM implementation in $Worktree"

    Push-Location $Worktree
    try {
        & git fetch origin *> (Join-Path $RunRoot "$Name-preflight-git.log")
        & git pull --ff-only origin $Branch *>> (Join-Path $RunRoot "$Name-preflight-git.log")
        if ($LASTEXITCODE -ne 0) {
            Write-RunNote "$Name: fast-forward pull could not complete; implementation worker will inspect/preserve repository state"
        }

        & opencode --pure run --dir $Worktree --model $Model --agent implementation-worker --auto $prompt *> $log
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    $summaryPath = Join-Path $Worktree "artifacts\knowledge-to-action\SUMMARY.json"
    $status = $null
    $summaryError = $null
    if (Test-Path $summaryPath) {
        try {
            $summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
            $status = [string]$summary.status
        } catch {
            $summaryError = "INVALID_SUMMARY_JSON"
        }
    } else {
        $summaryError = "MISSING_SUMMARY"
    }

    $head = (& git -C $Worktree rev-parse HEAD 2>$null | Out-String).Trim()
    $remoteHead = (& git -C $Worktree rev-parse "origin/$Branch" 2>$null | Out-String).Trim()

    Write-RunNote "$Name: OpenCode exit=$exitCode status=$status head=$head remote=$remoteHead"

    return [pscustomobject]@{
        name = $Name
        branch = $Branch
        worktree = $Worktree
        opencodeExit = $exitCode
        status = $(if ($status) { $status } else { $summaryError })
        expectedReadyStatus = $ReadyStatus
        head = $head
        remoteHead = $remoteHead
        summaryPath = $summaryPath
        logPath = $log
    }
}

if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) {
    throw "OpenCode CLI no esta disponible en PATH."
}

$modelList = (& opencode models zai-coding-plan 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $modelList -notmatch [regex]::Escape($Model)) {
    throw "FAIL_CLOSED: $Model no esta disponible en zai-coding-plan. No se inicia ningun otro proveedor/modelo."
}

$env:OPENCODE_CONFIG_CONTENT = New-GlmRuntimeConfig -SelectedModel $Model
$env:OPENCODE_AUTO_SHARE = "false"

Write-RunNote "Provider lock: zai-coding-plan only"
Write-RunNote "Main model: $Model"
Write-RunNote "Small model: $Model"
Write-RunNote "Subagent depth: 0"
Write-RunNote "OpenCode mode: non-interactive --pure --auto"
Write-RunNote "Codex/OpenAI is not part of this launcher"

$definitions = @(
    @{
        Name = "zo-media"
        ExpectedRepo = "jagzao/zo_whisper2"
        Preferred = "C:\Dev\Zo\whisper"
        Branch = "feat/zmi-knowledge-to-action-v1"
        Contract = ".agents/deliverables/LOCAL-CODER-ZO-KNOWLEDGE-001.md"
        Ready = "ZO_PRODUCER_READY_FOR_REVIEW"
    },
    @{
        Name = "zavi"
        ExpectedRepo = "jagzao/zavi"
        Preferred = "C:\Dev\Zo\zavi"
        Branch = "feat/knowledge-scope-publishing-v1"
        Contract = ".agents/delivery/LOCAL-CODER-ZO-KNOWLEDGE-002.md"
        Ready = "ZAVI_KNOWLEDGE_READY_FOR_REVIEW"
    },
    @{
        Name = "zavi-kab"
        ExpectedRepo = "jagzao/zavi-kab"
        Preferred = "C:\Dev\Zo\zavi-kab"
        Branch = "feat/knowledge-bound-skills-v1"
        Contract = ".agents/memory/tasks/LOCAL-CODER-ZO-KNOWLEDGE-003.md"
        Ready = "KAV_SKILLS_READY_FOR_REVIEW"
    }
)

$results = @()

foreach ($d in $definitions) {
    try {
        $root = Resolve-RepoRoot -Preferred $d.Preferred -ExpectedRepo $d.ExpectedRepo
        if (-not $root) {
            throw "repository not found locally"
        }
        $worktree = Prepare-Worktree -Name $d.Name -RepoRoot $root -Branch $d.Branch
        $results += Invoke-ImplementationRun -Name $d.Name -Worktree $worktree -Branch $d.Branch -ContractPath $d.Contract -ReadyStatus $d.Ready
    } catch {
        Write-RunNote "$($d.Name): BLOCKED_LOCAL_PRECONDITION: $($_.Exception.Message)"
        $results += [pscustomobject]@{
            name = $d.Name
            branch = $d.Branch
            worktree = $null
            opencodeExit = -1
            status = "BLOCKED_LOCAL_PRECONDITION"
            expectedReadyStatus = $d.Ready
            head = $null
            remoteHead = $null
            summaryPath = $null
            logPath = $null
            blocker = $_.Exception.Message
        }
    }
}

# Zero-LLM cross-repo fixture sanity.
$fixtureChecks = @()
function Add-FixtureCheck {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    $script:fixtureChecks += [pscustomobject]@{ name=$Name; ok=$Ok; detail=$Detail }
}

$zo = $results | Where-Object name -eq "zo-media"
$zv = $results | Where-Object name -eq "zavi"
$kv = $results | Where-Object name -eq "zavi-kab"

if ($zo.worktree) {
    $p = Join-Path $zo.worktree "contracts\knowledge-to-action\v1\p-g-project-package.json"
    if (Test-Path $p) {
        try {
            $j = Get-Content $p -Raw | ConvertFrom-Json
            Add-FixtureCheck "zo-pg-scope" ($j.scope -eq "PROJECT" -and $j.projectId -eq "p-g") "PROJECT/p-g"
        } catch { Add-FixtureCheck "zo-pg-scope" $false "invalid json" }
    } else { Add-FixtureCheck "zo-pg-scope" $false "missing fixture" }

    $p = Join-Path $zo.worktree "contracts\knowledge-to-action\v1\azure-global-package.json"
    if (Test-Path $p) {
        try {
            $j = Get-Content $p -Raw | ConvertFrom-Json
            Add-FixtureCheck "zo-azure-scope" ($j.scope -eq "GLOBAL") "GLOBAL"
        } catch { Add-FixtureCheck "zo-azure-scope" $false "invalid json" }
    } else { Add-FixtureCheck "zo-azure-scope" $false "missing fixture" }
}

if ($zv.worktree) {
    foreach ($f in @("p-g-project-package.json","azure-global-package.json","confidential-global-invalid-package.json")) {
        $p = Join-Path $zv.worktree "contracts\knowledge-to-action\v1\$f"
        if (Test-Path $p) {
            try { $null = Get-Content $p -Raw | ConvertFrom-Json; Add-FixtureCheck "zavi-$f" $true "json parse ok" }
            catch { Add-FixtureCheck "zavi-$f" $false "invalid json" }
        } else { Add-FixtureCheck "zavi-$f" $false "missing fixture" }
    }
}

if ($kv.worktree) {
    foreach ($f in @("azure-global-package.json","validated-global-skill.json","p-g-project-skill.json","superseded-skill.json")) {
        $p = Join-Path $kv.worktree "contracts\knowledge-to-action\v1\$f"
        if (Test-Path $p) {
            try { $null = Get-Content $p -Raw | ConvertFrom-Json; Add-FixtureCheck "kav-$f" $true "json parse ok" }
            catch { Add-FixtureCheck "kav-$f" $false "invalid json" }
        } else { Add-FixtureCheck "kav-$f" $false "missing fixture" }
    }
}

$allReady = $true
foreach ($r in $results) {
    if ($r.status -ne $r.expectedReadyStatus) { $allReady = $false }
}
if ($fixtureChecks | Where-Object { -not $_.ok }) { $allReady = $false }

$overall = if ($allReady) { "READY_FOR_OWNER_REVIEW" } else { "REVIEW_REQUIRED" }

$master = [pscustomobject]@{
    runId = $RunId
    model = $Model
    provider = "zai-coding-plan"
    codexUsedByLauncher = $false
    overall = $overall
    repositories = $results
    fixtureChecks = $fixtureChecks
    completedAt = (Get-Date).ToString("o")
}

$masterJson = Join-Path $RunRoot "MASTER-SUMMARY.json"
$masterMd = Join-Path $RunRoot "MASTER-SUMMARY.md"
$master | ConvertTo-Json -Depth 10 | Set-Content -Path $masterJson -Encoding UTF8

$lines = @(
    "# Knowledge-to-Action Overnight Summary",
    "",
    "- Run: $RunId",
    "- Provider: zai-coding-plan",
    "- Model: $Model",
    "- Codex used by launcher: NO",
    "- Overall: $overall",
    ""
)
foreach ($r in $results) {
    $lines += "## $($r.name)"
    $lines += "- Branch: $($r.branch)"
    $lines += "- Status: $($r.status)"
    $lines += "- HEAD: $($r.head)"
    $lines += "- Remote HEAD: $($r.remoteHead)"
    $lines += "- Summary: $($r.summaryPath)"
    $lines += ""
}
$lines += "## Fixture sanity"
foreach ($f in $fixtureChecks) {
    $lines += "- $($f.name): $(if ($f.ok) {'PASS'} else {'FAIL'}) — $($f.detail)"
}
$lines | Set-Content -Path $masterMd -Encoding UTF8

Remove-Item Env:OPENCODE_CONFIG_CONTENT -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================"
Write-Host "KNOWLEDGE OVERNIGHT COMPLETE"
Write-Host "OVERALL=$overall"
Write-Host "MASTER_SUMMARY=$masterJson"
Write-Host "MASTER_SUMMARY_MD=$masterMd"
Write-Host "============================================"
exit 0
