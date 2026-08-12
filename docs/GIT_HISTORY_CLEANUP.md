# Git History Cleanup

**Status: audit complete, no destructive action taken.** This document
records what a full history scan found and the exact commands to fix it —
running them is a deliberate, manual decision for the repo owner, not
something this pass executed.

## What was audited

Full history (`git log --all -p`, 7 commits total) was scanned for:
client/project names, personal file-path fragments, real email addresses,
and credential-shaped strings (OpenAI/GitHub/AWS key patterns).

## What was found

### 1. Client name "Valeris" — present in history, already removed from HEAD

The client name "Valeris" (and its handler `ValerisHandler`/`valeris_handler.py`,
routing prefix `valeris_`, `VALERIS_PATH`) appears in the diffs of:

- `041f5f4` — Initial commit (introduces it)
- `d6718db` — Fix leaked client names in dashboard.html and smoke test, retake screenshots with mock data
- `bbc4250` — Translate codebase to English, remove Valeris references
- `37eae5d` — Anonymize local paths and client names for public repo

The **current working tree is clean** (verified via `git grep -i valeris` —
zero hits as of this pass, after redacting the remaining occurrences found
in `.agents/` — see below). The name is only reachable by checking out or
diffing an older commit.

### 2. Personal local paths (`C:\Jagzao\whisper\...`) — present in history, removed from HEAD in this pass

Stale file-header comments of the form `# C:\Jagzao\whisper\...` were found
in 5 files under `watcher/` and `deepseek/` (leftover editor-generated path
comments, no functional purpose). Removed from the working tree in this
pass. They remain visible in the history of:

- `041f5f4` — Initial commit
- `37eae5d` — Anonymize local paths and client names for public repo

Note: `LICENSE`'s `Copyright (c) 2026 Jagzao` is the repo owner's own name
as copyright holder — intentional, not a leak, not in scope for redaction.

### 3. Project/task codename ("Apoc", `validacionesFaltantesRoles`) — present in history only

A debug/test script once contained hardcoded paths:
`C:/Jagzao/whisper/Videos/Apoc/validacionesFaltantesRoles.webm` (and the
matching `.wav`). This does not exist in the current working tree
(`git grep -i apoc` — zero hits) but is visible in the diffs of `041f5f4`
and `37eae5d`. "Apoc" and the Spanish task name
(`validacionesFaltantesRoles` = "missing-roles validations") read as a
real project/feature reference rather than a synthetic placeholder.

### 4. Secrets / credentials — none found

No OpenAI/GitHub/AWS-shaped key patterns, and no real email addresses, were
found anywhere in history — only placeholder values
(`your_api_key_here`, `destinatario@gmail.com`, etc.). **No rotation is
needed based on this audit.** If you know of a real credential that was
ever pasted into this repo outside of what this scan's patterns cover,
rotate it regardless of whether it shows up here — this audit is
pattern-based, not exhaustive.

## Recommended cleanup command (not executed)

Given the repo is small (7 commits) and the leaks are text substitutions
(not whole files to delete), `git filter-repo --replace-text` is the
right tool — it rewrites blob content across all history in one pass.

**1. Back up first — this rewrites every commit hash.**
```sh
git clone --mirror . ../whisper-backup-before-history-rewrite.git
```

**2. Install git-filter-repo** (not bundled with git):
```sh
pip install git-filter-repo
```

**3. Create a replacements file** (`replacements.txt`, project root — delete after use, don't commit it):
```
Valeris==>Northwind
ValerisHandler==>ClientMeetingHandler
valeris_handler==>client_meeting_handler
valeris==>northwind
VALERIS_PATH==>NORTHWIND_PATH
C:\Jagzao\whisper==>REDACTED_LOCAL_PATH
C:/Jagzao/whisper==>REDACTED_LOCAL_PATH
Apoc==>REDACTED_PROJECT
validacionesFaltantesRoles==>redacted_task_name
```

**4. Run it:**
```sh
git filter-repo --replace-text replacements.txt --force
```
(`--force` is required by git-filter-repo when running against a repo
that wasn't freshly cloned for this purpose — it's filter-repo's own
safety flag, unrelated to `git push --force`.)

**5. Verify:**
```sh
git log --all -p | grep -i "valeris\|jagzao\|apoc" || echo "clean"
git log --oneline | head -20    # confirm history still makes sense
```

**6. Force-push — manual, deliberate, owner-only step:**
```sh
git push --force-with-lease origin main
```
`git filter-repo` rewrites every commit hash after the earliest affected
commit (in this repo, that's effectively all of them). This is why it's
listed here as a documented procedure rather than something run
automatically.

## Risks and consequences of rewriting history

- **All commit hashes change.** Anyone with an existing clone or fork must
  re-clone, or hard-reset their local branch to the new history — a normal
  `git pull` will conflict/diverge.
- **Open PRs against the old history will need to be re-based or recreated.**
- **GitHub may still show the old commits** in cached views (PR diffs,
  notifications, forks) for a period after the rewrite, even though they're
  no longer reachable from `main`.
- **If anyone already cloned/forked the repo**, the leaked strings remain in
  *their* copy regardless of what you do here — history rewriting protects
  future clones, not past ones. This is exactly why credential rotation
  (not applicable here, per the audit above) always takes priority over
  history cleanup when a real secret is involved.
- Given the low sensitivity of what was actually found (a client name
  already anonymized going forward, stale path comments, a project
  codename with no accompanying secret), rewriting history is a
  **nice-to-have for a cleaner public portfolio piece**, not an urgent
  security fix — there's no live credential to invalidate. Weigh the
  one-time disruption (re-clones, PR rebases) against that.
