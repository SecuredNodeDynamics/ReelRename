#!/usr/bin/env python3
"""
github_sync.py
Auto-sync a local git repo (e.g., ReelRename) to GitHub.

Typical use:
  python github_sync.py
  python github_sync.py --path "C:\Projects\ReelRename" --message "Quick fixes"
  python github_sync.py --no-pull
  python github_sync.py --remote origin --branch main

Notes:
- Requires Git installed and available on PATH.
- Assumes the repo already has a remote (default: origin).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


def run_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    cmd = ["git"] + args
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        shell=False,
    )
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def fail(msg: str, code: int = 1) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def is_git_repo(cwd: Path) -> bool:
    rc, out, _ = run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    return rc == 0 and out.lower() == "true"


def current_branch(cwd: Path) -> Optional[str]:
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if rc != 0:
        return None
    return out


def has_remote(cwd: Path, remote: str) -> bool:
    rc, out, _ = run_git(["remote"], cwd=cwd)
    if rc != 0:
        return False
    remotes = {r.strip() for r in out.splitlines() if r.strip()}
    return remote in remotes


def working_tree_dirty(cwd: Path) -> bool:
    rc, out, _ = run_git(["status", "--porcelain"], cwd=cwd)
    if rc != 0:
        return False
    return len(out.strip()) > 0


def ensure_upstream(cwd: Path, remote: str, branch: str) -> None:
    """
    Ensure branch has an upstream.
    If not, set it to remote/branch.
    """
    rc, _, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=cwd)
    if rc == 0:
        return

    info(f"No upstream set for '{branch}'. Setting upstream to '{remote}/{branch}'...")
    rc, _, err = run_git(["push", "-u", remote, branch], cwd=cwd)
    if rc != 0:
        fail(
            "Failed to set upstream. This usually means:\n"
            "- remote/branch doesn't exist yet, OR\n"
            "- authentication failed, OR\n"
            "- remote name is wrong.\n\n"
            f"Git said: {err}"
        )
    ok("Upstream set.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-sync a repo to GitHub via git add/commit/push.")
    parser.add_argument(
        "--path",
        default=".",
        help="Path to the repo root (default: current directory).",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="Remote name to push to (default: origin).",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch to push (default: current branch).",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="Commit message (default: timestamped 'Auto-sync').",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="Skip pulling/rebasing before pushing.",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Stage changes and push without committing (not typical).",
    )
    args = parser.parse_args()

    repo_path = Path(args.path).expanduser().resolve()
    if not repo_path.exists():
        fail(f"Path does not exist: {repo_path}")

    if not is_git_repo(repo_path):
        fail(
            f"Not a git repository: {repo_path}\n"
            "Fix: run `git init` and add a remote, or point --path at the repo root."
        )
    ok(f"Git repo detected: {repo_path}")

    # Determine branch
    branch = args.branch or current_branch(repo_path)
    if not branch or branch == "HEAD":
        fail("Could not determine current branch. Are you in a detached HEAD state?")
    info(f"Branch: {branch}")

    # Remote sanity check
    remote = args.remote
    if not has_remote(repo_path, remote):
        rc, _, err = run_git(["remote", "-v"], cwd=repo_path)
        details = err if err else "(no remotes listed)"
        fail(
            f"Remote '{remote}' not found.\n"
            "Fix: set your GitHub remote, e.g.:\n"
            "  git remote add origin <YOUR_GITHUB_REPO_URL>\n\n"
            f"Current remotes:\n{details}"
        )
    ok(f"Remote: {remote}")

    # Pull/rebase first (best practice)
    if not args.no_pull:
        info("Pulling latest changes (rebase)...")
        rc, out, err = run_git(["pull", "--rebase", remote, branch], cwd=repo_path)
        if rc != 0:
            fail(
                "Pull/rebase failed. You likely have conflicts or auth issues.\n"
                "Resolve conflicts, then re-run.\n\n"
                f"Git said: {err or out}"
            )
        ok("Pull/rebase complete.")
    else:
        info("Skipping pull/rebase (--no-pull).")

    # Stage everything
    info("Staging changes (git add -A)...")
    rc, _, err = run_git(["add", "-A"], cwd=repo_path)
    if rc != 0:
        fail(f"Failed to stage changes. Git said: {err}")
    ok("Staged.")

    # Commit if needed
    if args.no_commit:
        info("Skipping commit (--no-commit).")
    else:
        if working_tree_dirty(repo_path):
            # still dirty after add? (usually means untracked ignored etc., but status will show)
            pass

        rc, status_out, status_err = run_git(["status", "--porcelain"], cwd=repo_path)
        if rc != 0:
            fail(f"Failed to read status. Git said: {status_err}")

        if not status_out.strip():
            ok("No changes to commit. Repo already up to date locally.")
        else:
            commit_msg = args.message or f"Auto-sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            info(f"Committing: {commit_msg}")
            rc, out, err = run_git(["commit", "-m", commit_msg], cwd=repo_path)
            if rc != 0:
                # Common case: "nothing to commit" can happen depending on state.
                combined = (err or "") + ("\n" + out if out else "")
                if "nothing to commit" in combined.lower():
                    ok("Nothing to commit.")
                else:
                    fail(f"Commit failed. Git said:\n{combined.strip()}")
            else:
                ok("Commit created.")

    # Ensure upstream & push
    ensure_upstream(repo_path, remote, branch)

    info("Pushing to GitHub...")
    rc, out, err = run_git(["push", remote, branch], cwd=repo_path)
    if rc != 0:
        fail(
            "Push failed. This is usually authentication, permissions, or a non-fast-forward issue.\n\n"
            f"Git said: {err or out}"
        )
    ok("Push complete. GitHub is updated.")

    # Friendly summary
    rc, log_out, _ = run_git(["log", "-1", "--oneline"], cwd=repo_path)
    if rc == 0 and log_out:
        info(f"Latest commit: {log_out}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        fail("Cancelled.", code=130)
