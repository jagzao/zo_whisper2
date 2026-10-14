# RECOVERY-ZMI-DOCS-V2-POWER-LOSS-20261014

## Status
FROZEN_RECOVERY

## Remote fact
At recovery start, remote branch:
`feat/zmi-documentation-synthesis-v2`
HEAD:
`7636f850abcd19079bae18e325f5c66a717057d5`

No Documentation Synthesis V2 implementation commit is visible remotely after the frozen analysis/product commits.

Therefore local work MUST be inspected/recovered before assuming it was lost.

## Primary goal
Resume and finish Documentation Synthesis V2 without repeating analysis and without another hours-long all-or-nothing run.

## Recovery rules
- owner worktree is read-only if dirty;
- never reset/stash/clean/switch it automatically;
- inspect local worktrees first;
- preserve coherent local implementation;
- commit/push recovered slices immediately;
- no real confidential media;
- no heavy validation until ChatGPT review.

## Recovery algorithm

### R1 — discover local state
Run from normal shell, not from an LLM loop:

```powershell
git -C C:\Dev\Zo\whisper worktree list --porcelain
git -C C:\Dev\Zo\whisper status --porcelain=v1 -b
git -C C:\Dev\Zo\whisper branch --all --contains 7636f850abcd19079bae18e325f5c66a717057d5
```

For each worktree related to Documentation V2:
- record path;
- branch;
- HEAD;
- status;
- changed files;
- staged files.

Do not mutate yet.

### R2 — inspect recovery evidence
In candidate worktree:
- `.agents/session/delivery-checkpoint.json` if present;
- `git status`;
- `git diff --stat`;
- `git diff --cached --stat`;
- `git log --oneline --decorate -20`;
- `git reflog --date=iso -30`;
- untracked files under documentation/tests only.

If a local commit exists and is a descendant of frozen remote head, preserve it.
If uncommitted coherent files exist, preserve them in the isolated worktree.

### R3 — establish safe isolated worktree
If no safe candidate exists, create a new isolated worktree from:
`origin/feat/zmi-documentation-synthesis-v2`.

If coherent local changes exist in another safe isolated worktree, continue there.
Do not copy from dirty owner worktree until exact changed files are reviewed.

### R4 — checkpoint immediately
Before further coding, install/port the validated PLV5 checkpoint tooling from:
`feat/project-lead-v4-autonomous-delivery@46ea1432a048ebb3c65d549272e75993d487f69b`

Required recovery tooling:
- scripts/delivery_checkpoint.py
- scripts/ram_gate.py
- scripts/heavy_validation_runner.py
- scripts/implementation_summary.py
- scripts/model_router.py
- PLV5 gate categorization in scripts/gate_runner.py
- corresponding tests/protocols when needed

Do not blindly overwrite the current Jenkinsfile. CI fast-lane behavior is defined separately.

### R5 — convert WP-01..WP-20 into vertical delivery slices
Do not wait for all 20 WPs before first commit/push.

Slice A — Evidence foundation
- WP-01 config/enums
- WP-02 evidence model
- WP-03 evidence timeline
- WP-04 mode resolver
- WP-05 compaction

Slice B — Grounded synthesis
- WP-06 synthesis domain
- WP-07 synthesis service
- WP-08 grounding validator

Slice C — Human documentation quality
- WP-09 screenshots
- WP-10 semantic Markdown
- WP-11 semantic PDF

Slice D — Knowledge/RAG bridge
- WP-12 AI package V2
- WP-13 Knowledge Package v2 bridge
- WP-14 orchestration

Slice E — Recovery/product integration
- WP-15 regeneration
- WP-16 review compatibility
- WP-17 dashboard surfacing
- WP-18 fixtures
- WP-19 docs
- WP-20 light validation

Each slice:
1. code;
2. run only slice-targeted tests;
3. Ruff changed surface;
4. compile/typecheck changed surface;
5. commit;
6. push immediately;
7. checkpoint;
8. continue.

A power outage after any slice must leave a remote recoverable commit.

## Fast feedback objective
Target normal slice feedback in minutes, not hours.

No Whisper model loading.
No real media.
No Docker.
No Playwright.
No full pytest.
No security/smoke/full CI before review.

## Terminal state
After Slice E:
- all frozen DV2 behavior implemented;
- light gates green;
- remote HEAD verified;
- READY_FOR_CHATGPT_REVIEW.
