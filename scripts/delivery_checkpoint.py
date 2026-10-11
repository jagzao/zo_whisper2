"""PLV5 delivery checkpoint / resume.

Atomically maintains a gitignored checkpoint at
``.agents/session/delivery-checkpoint.json`` so a power loss can be resumed
mechanically without local re-planning.

Checkpoint fields (frozen):
repo, branch, remote, start_sha, current_sha, frozen_contract,
work_packages (list of {id, status}), gates (list of {gate, result}),
last_commit, last_push, terminal_state, next_action.

Resume contract:

    LOAD_CHECKPOINT -> VERIFY_REPO_AND_REMOTE -> RESUME_FIRST_INCOMPLETE

Verification fails closed (non-zero exit + JSON evidence) on branch mismatch,
remote SHA divergence, or a missing frozen contract.

Exit codes: 0 ok, 5 verification failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = ROOT / ".agents" / "session" / "delivery-checkpoint.json"

WP_STATUS_VALUES = ("pending", "in_progress", "done")


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def load(path: Path | None = None) -> dict:
    target = path or CHECKPOINT_PATH
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A previous interrupted temp write never corrupts the last good state:
        # os.replace guarantees the checkpoint file is always complete JSON.
        return {}
    return data if isinstance(data, dict) else {}


def update(path: Path | None = None, **fields) -> dict:
    target = path or CHECKPOINT_PATH
    payload = load(target)
    payload.update(fields)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _atomic_write(target, payload)
    return payload


def record_gate(gate: str, result: str, path: Path | None = None) -> dict:
    payload = load(path)
    gates = [g for g in payload.get("gates", []) if g.get("gate") != gate]
    gates.append({"gate": gate, "result": result})
    return update(path, gates=gates)


def set_work_package(wp_id: str, status: str, path: Path | None = None) -> dict:
    if status not in WP_STATUS_VALUES:
        raise ValueError(f"invalid work package status: {status}")
    payload = load(path)
    wps = [wp for wp in payload.get("work_packages", []) if wp.get("id") != wp_id]
    wps.append({"id": wp_id, "status": status})
    return update(path, work_packages=wps)


def first_incomplete_step(checkpoint: dict) -> dict | None:
    """First pending/in-progress work package, in recorded order."""
    for wp in checkpoint.get("work_packages", []):
        if wp.get("status") in ("pending", "in_progress"):
            return wp
    return None


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def verify(
    expected_branch: str,
    remote_name: str = "origin",
    frozen_contract: str | None = None,
    allow_dirty: bool = True,
) -> tuple[bool, dict]:
    evidence: dict = {"expected_branch": expected_branch, "remote": remote_name}
    ok = True

    branch = _git(["branch", "--show-current"])
    evidence["current_branch"] = branch or "(detached)"
    if branch != expected_branch:
        ok = False
        evidence["branch_mismatch"] = True

    try:
        remote_head = _git(["rev-parse", f"{remote_name}/{expected_branch}"])
        local_head = _git(["rev-parse", "HEAD"])
        evidence["remote_head"] = remote_head
        evidence["local_head"] = local_head
        merge_base = _git(["merge-base", "HEAD", f"{remote_name}/{expected_branch}"])
        if merge_base not in (remote_head, local_head):
            evidence["sha_relation"] = "DIVERGED"
            ok = False
        else:
            evidence["sha_relation"] = "FAST_FORWARDABLE" if local_head == merge_base else "AHEAD"
    except RuntimeError as exc:
        evidence["git_error"] = str(exc)
        ok = False

    status = _git(["status", "--porcelain"])
    evidence["dirty"] = bool(status)
    if status and not allow_dirty:
        evidence["dirty_when_clean_required"] = True
        ok = False

    contract = frozen_contract or load().get("frozen_contract")
    if contract:
        evidence["frozen_contract"] = contract
        if not (ROOT / contract).exists():
            evidence["frozen_contract_missing"] = True
            ok = False

    evidence["verified"] = ok
    return ok, evidence


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="PLV5 delivery checkpoint / resume")
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="print current checkpoint JSON")
    p_show.add_argument("--path", type=Path, default=None)

    p_verify = sub.add_parser("verify", help="verify repo state against checkpoint (fails closed)")
    p_verify.add_argument("--branch", required=True)
    p_verify.add_argument("--remote", default="origin")
    p_verify.add_argument("--contract", default=None)

    p_next = sub.add_parser("next-step", help="print first incomplete mechanical step")
    p_next.add_argument("--path", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.command == "show":
        print(json.dumps(load(args.path), ensure_ascii=False, indent=2))
        return 0
    if args.command == "next-step":
        step = first_incomplete_step(load(args.path))
        print(json.dumps(step, ensure_ascii=False))
        return 0 if step else 1

    ok, evidence = verify(args.branch, args.remote, args.contract)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
