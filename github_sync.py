#!/usr/bin/env python3
"""
github_sync.py
Auto-sync a local git repo (ReelRename) to GitHub.

Typical use:
  python github_sync.py
  python github_sync.py --path "C:/Users/artyo/PycharmProjects/ReelRename" --message "Quick fixes"
  python github_sync.py --no-pull
  python github_sync.py --no-stash
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

SCRIPT_NAME = "github_sync.py"


def run_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    p = subprocess.run(["git"] + args, cwd=str(cwd), text=True, capture_output=True)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def fail(msg: str, code: int = 1) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def is_git_repo(cwd: Path) -> bool:
    rc, out, _ = run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    return rc == 0 and out.lower() == "true"


def current_branch(cwd: Path) -> Optional[str]:
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return out if rc == 0 else None


def has_remote(cwd: Path, remote: str) -> bool:
    rc, out, _ = run_git(["remote"], cwd)
    return rc == 0 and remote in {r.strip() for r in out.splitlines() if r.strip()}


def status_porcelain(cwd: Path) -> str:
    rc, out, err = run_git(["status", "--porcelain"], cwd)
    if rc != 0:
        fail(f"Failed to read status. Git said: {err}")
    return out.strip()


def ensure_script_ignored(repo_path: Path) -> None:
    gitignore = repo_path / ".gitignore"
    lines: List[str] = []
    if gitignore.exists():
        lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()

    if SCRIPT_NAME not in lines:
        info(f"Adding {SCRIPT_NAME} to .gitignore...")
        with gitignore.open("a", encoding="utf-8") as f:
            if lines and lines[-1].strip():
                f.write("\n")
            f.write(f"{SCRIPT_NAME}\n")
        ok(f"Added {SCRIPT_NAME} to .gitignore.")
    else:
        ok(f"{SCRIPT_NAME} already in .gitignore.")

    # If tracked, untrack it (keep local file)
    rc, _, _ = run_git(["ls-files", "--error-unmatch", SCRIPT_NAME], repo_path)
    if rc == 0:
        info(f"{SCRIPT_NAME} is tracked. Untracking it (keeping local file)...")
        rc2, out2, err2 = run_git(["rm", "--cached", "--quiet", SCRIPT_NAME], repo_path)
        if rc2 != 0:
            fail(f"Failed to untrack {SCRIPT_NAME}. Git said: {err2 or out2}")
        ok(f"Untracked {SCRIPT_NAME}.")
    else:
        ok(f"{SCRIPT_NAME} is not tracked (good).")


def stash_push_if_needed(repo_path: Path) -> bool:
    if not status_porcelain(repo_path):
        return False
    msg = f"github_sync auto-stash {datetime.now():%Y-%m-%d %H:%M:%S}"
    info("Local changes detected. Stashing them so pull/rebase can run...")
    rc, out, err = run_git(["stash", "push", "-u", "-m", msg], repo_path)
    if rc != 0:
        fail(f"Failed to stash changes. Git said: {err or out}")
    ok("Stashed.")
    return True


def stash_pop(repo_path: Path) -> None:
    info("Restoring stashed changes (stash pop)...")
    rc, out, err = run_git(["stash", "pop"], repo_path)
    if rc != 0:
        fail(f"Stash pop failed (conflicts). Git said:\n{err or out}")
    ok("Stash restored.")


def ensure_upstream(repo_path: Path, remote: str, branch: str) -> None:
    rc, _, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo_path)
    if rc == 0:
        return
    info(f"Setting upstream to {remote}/{branch}...")
    rc, out, err = run_git(["push", "-u", remote, branch], repo_path)
    if rc != 0:
        fail(f"Failed to set upstream. Git said:\n{err or out}")
    ok("Upstream set.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto-sync repo to GitHub (stash/pull/add/commit/push).")
    ap.add_argument("--path", default=".", help="Repo path (default: current directory).")
    ap.add_argument("--remote", default="origin", help="Remote (default: origin).")
    ap.add_argument("--branch", default="main", help="Branch (default: main).")
    ap.add_argument("--message", default=None, help="Commit message.")
    ap.add_argument("--no-pull", action="store_true", help="Skip pull/rebase.")
    ap.add_argument("--no-commit", action="store_true", help="Skip commit.")
    ap.add_argument("--no-stash", action="store_true", help="Disable auto-stash.")
    args = ap.parse_args()

    repo = Path(args.path).expanduser().resolve()
    if not repo.exists():
        fail(f"Path does not exist: {repo}")
    if not is_git_repo(repo):
        fail(f"Not a git repository: {repo}")

    ok(f"Git repo detected: {repo}")

    ensure_script_ignored(repo)

    branch = args.branch or current_branch(repo)
    if not branch or branch == "HEAD":
        fail("Could not determine current branch.")
    info(f"Branch: {branch}")

    if not has_remote(repo, args.remote):
        rc, out, err = run_git(["remote", "-v"], repo)
        fail(f"Remote '{args.remote}' not found.\n{out or err}")
    ok(f"Remote: {args.remote}")

    did_stash = False
    if not args.no_stash:
        did_stash = stash_push_if_needed(repo)
    else:
        info("Auto-stash disabled (--no-stash).")

    if not args.no_pull:
        info("Pulling latest changes (rebase)...")
        rc, out, err = run_git(["pull", "--rebase", args.remote, branch], repo)
        if rc != 0:
            fail(f"Pull/rebase failed. Git said:\n{err or out}")
        ok("Pull/rebase complete.")
    else:
        info("Skipping pull/rebase (--no-pull).")

    if did_stash:
        stash_pop(repo)

    info("Staging changes (git add -A)...")
    rc, _, err = run_git(["add", "-A"], repo)
    if rc != 0:
        fail(f"Failed to stage changes. Git said: {err}")
    ok("Staged.")

    if not args.no_commit:
        if status_porcelain(repo):
            msg = args.message or f"Auto-sync: {datetime.now():%Y-%m-%d %H:%M:%S}"
            info(f"Committing: {msg}")
            rc, out, err = run_git(["commit", "-m", msg], repo)
            if rc != 0:
                combined = (err or "") + ("\n" + out if out else "")
                if "nothing to commit" not in combined.lower():
                    fail(f"Commit failed. Git said:\n{combined.strip()}")
            ok("Commit created.")
        else:
            ok("No changes to commit.")
    else:
        info("Skipping commit (--no-commit).")

    ensure_upstream(repo, args.remote, branch)

    info("Pushing to GitHub...")
    rc, out, err = run_git(["push", args.remote, branch], repo)
    if rc != 0:
        fail(f"Push failed. Git said:\n{err or out}")
    ok("Push complete. GitHub is updated.")

    rc, log_out, _ = run_git(["log", "-1", "--oneline"], repo)
    if rc == 0 and log_out:
        info(f"Latest commit: {log_out}")


if __name__ == "__main__":
    main()
