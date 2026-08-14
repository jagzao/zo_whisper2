# Git History Cleanup

**Status: audit complete, the rewrite command below has been test-run
against an isolated local clone (not this repo, not pushed anywhere) to
confirm it actually works — no destructive action has been taken against
the real repository or its remote.** Running it for real is a deliberate,
manual decision for the repo owner.

This document intentionally uses **placeholders** instead of the real
values found during the audit. Spelling out the actual client name, path,
or codename in a public doc would defeat the point of cleaning them up —
so below, `CLIENT_NAME_A`, `CLIENT_HANDLER_A`, `OLD_CLIENT_PREFIX`,
`REDACTED_LOCAL_PATH`, `REDACTED_PROJECT`, and `REDACTED_TASK` each stand
in for one real string the owner already knows. A regression check
(`scripts/security.py::check_no_denylisted_identifiers`) fails the build if
the real values it protects against ever reappear in a tracked file — the
actual denylist is never tracked in this repo (owner-local
`.sensitive-identifiers`, gitignored, or a private `SENSITIVE_IDENTIFIERS`
CI secret; see the docstring above `_load_private_denylist` in that
script). Neither is required for public clones/forks — the check simply
reports `SKIPPED: no private denylist configured` and the rest of the
security harness still runs.

## What was audited

Full history (`git log --all -p`) was scanned for: client/project names,
personal file-path fragments, real email addresses, and credential-shaped
strings (OpenAI/GitHub/AWS key patterns).

## What was found

### 1. A real client name — present in history, already removed from HEAD

A real client name (call it `CLIENT_NAME_A`) — along with its handler
class (`CLIENT_HANDLER_A`), a routing prefix derived from it
(`OLD_CLIENT_PREFIX`), and an env-var-shaped constant built from it —
appears in the diffs of several early commits (the initial commit and the
subsequent anonymization/translation passes that removed it from HEAD).

The **current working tree is clean** (verified via
`scripts/security.py::check_no_denylisted_identifiers`, which runs in CI
on every push/PR). The name is only reachable by checking out or diffing
an older commit.

### 2. Personal local paths — present in history, removed from HEAD

Stale file-header comments of the form `# <REDACTED_LOCAL_PATH>\...` (an
absolute path under the original author's local username) were found in a
handful of files under non-production directories (leftover
editor-generated path comments, no functional purpose). Removed from the
working tree in an earlier pass; still visible in the diffs of the commits
that introduced/removed them.

Note: `LICENSE`'s copyright line uses the repo owner's own name as
copyright holder — intentional, not a leak, not in scope for redaction,
and explicitly allowlisted in the denylist check below.

### 3. A project/task codename — present in history only

A debug/test script once contained a hardcoded path referencing an
internal project codename and a Spanish-language task name (referred to
here as `REDACTED_PROJECT`/`REDACTED_TASK`). This does not exist in the
current working tree (confirmed by the denylist check) but is visible in
the diffs of the same early commits noted above. It reads as a real
project/feature reference rather than a synthetic placeholder.

### 4. Secrets / credentials — none found

No OpenAI/GitHub/AWS-shaped key patterns, and no real email addresses, were
found anywhere in history — only placeholder values
(`your_api_key_here`, `destinatario@gmail.com`, etc.). **No rotation is
needed based on this audit.** If you know of a real credential that was
ever pasted into this repo outside of what this scan's patterns cover,
rotate it regardless of whether it shows up here — this audit is
pattern-based, not exhaustive.

## Recommended cleanup command (tested locally, not executed against the real repo)

Given the leaks are text substitutions (not whole files to delete),
`git filter-repo --replace-text` (blob/file content) plus `--replace-message`
(commit messages — a **separate** flag; `--replace-text` alone does not
touch commit messages, confirmed by testing) is the right combination.

**1. Back up first — this rewrites every commit hash.**
```sh
git clone --mirror . ../whisper-backup-before-history-rewrite.git
```

**2. Install git-filter-repo** (not bundled with git):
```sh
pip install git-filter-repo
```

**3. Find the exact strings and SHAs to replace, locally** (do not hardcode
real values in this doc — find them fresh, since they may drift as history
grows):
```sh
git log --all -p | grep -in "client_name_a\|old_client_prefix\|redacted_local_path\|redacted_project" 
```
Use the real strings you find (the client name, its handler class name,
its routing prefix, the local path fragment, the project codename) to
build the replacements file below — substitute your own values for every
placeholder shown.

**4. Create a replacements file** (`replacements.txt`, project root — delete after use, don't commit it):
```
CLIENT_NAME_A==>REPLACEMENT_NAME
ClientNameA==>ReplacementName
client_name_a==>replacement_name
ClientHandlerA==>NewHandlerName
client_handler_a==>new_handler_name
OLD_CLIENT_PREFIX_PATH==>NEW_PREFIX_PATH
REDACTED_LOCAL_PATH==>SANITIZED_PATH
REDACTED_PROJECT==>SANITIZED_PROJECT
REDACTED_TASK==>sanitized_task_name
```
(Include an **all-caps** variant of the client name specifically — a
`[CLIENT_NAME_A]`-style log-tag string in early commits would only be
caught by that exact casing, not by the lowercase/mixed-case rules alone;
confirmed by actually running this against a test clone and checking the
output.)

**5. Run it — both flags, same file:**
```sh
git filter-repo --replace-text replacements.txt --replace-message replacements.txt --force
```
(`--force` is required by git-filter-repo when running against a repo
that wasn't freshly cloned for this purpose — it's filter-repo's own
safety flag, unrelated to `git push --force`.)

**6. Verify:**
```sh
python scripts/security.py   # re-runs check_no_denylisted_identifiers among other gates
git log --oneline | head -20 # confirm history still makes sense
```

**Known cosmetic side effect, confirmed in testing:** if the replacement
value for a renamed handler is the pipeline's *current* real name, a
commit message that narrates the actual historical rename (e.g. "renamed
X to Y") can come out slightly redundant-looking after substitution (both
the "from" and "to" names collapse toward the same text). No information
is lost or leaked by this — it just reads a bit oddly. Not worth
hand-fixing for a handful of commit messages; mentioned here so it isn't
mistaken for the rewrite going wrong.

**7. Force-push — manual, deliberate, owner-only step:**
```sh
git push --force-with-lease origin main
```
`git filter-repo` rewrites every commit hash after the earliest affected
commit (in this repo, that's effectively all of them). This is why it's
listed here as a documented procedure rather than something run
automatically.

## Checklist before running this for real

- [ ] Backed up via `git clone --mirror` (step 1).
- [ ] Confirmed no open PRs would be orphaned by a full history rewrite
      (or accepted they'll need to be re-based/recreated).
- [ ] Notified anyone else with a clone/fork that they'll need to re-clone.
- [ ] Ran the replacement locally and verified with
      `python scripts/security.py` before force-pushing.
- [ ] Understand that a force-push cannot undo exposure for anyone who
      already cloned/forked before the rewrite — see below.

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
