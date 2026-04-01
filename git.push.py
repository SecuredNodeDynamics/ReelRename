#!/usr/bin/env python3
"""
git.push.py  –  ReelRename release sync & GitHub publisher

Performs the full release handshake in one command:
  1. Read current APP_VERSION from main_window.py
  2. Patch README.md so every version reference matches the current version
  3. Stage all tracked changes + any new root-level .py tools
  4. Commit (if anything changed) and push to origin/main
  5. Create and push the vX.Y.Z git tag (if not already tagged)
  6. Create a GitHub Release (if not already published) with:
       - Auto-generated notes from git log since the previous release tag
       - The compiled installer .exe attached (if present in release/)

Usage:
    python git.push.py                            # full release flow
    python git.push.py --dry-run                  # preview every step, write nothing
    python git.push.py --skip-release             # push code + tag only, skip GitHub Release
    python git.push.py --message "Custom commit"  # override the auto commit message
    python git.push.py --notes "Custom notes"     # override auto-generated release notes
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT      = Path(__file__).resolve().parent
MAIN_WIN  = ROOT / "reelrename_app" / "ui" / "main_window.py"
README    = ROOT / "README.md"
RELEASE_DIR = ROOT / "release"

# New tool scripts at project root that should always be committed if untracked
ROOT_TOOLS = {"gen.backup.py", "app.build.py", "git.push.py"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=capture,
        text=True,
        check=check,
    )


def _run_out(cmd: list[str]) -> str:
    """Run a command and return stdout stripped."""
    result = _run(cmd, capture=True, check=False)
    return result.stdout.strip()


def _gh_available() -> bool:
    result = subprocess.run(["gh", "--version"], capture_output=True)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Step 1 – Read version
# ---------------------------------------------------------------------------

def read_version() -> str:
    text = MAIN_WIN.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise RuntimeError("APP_VERSION not found in main_window.py")
    return m.group(1)


# ---------------------------------------------------------------------------
# Step 2 – Sync README version references
# ---------------------------------------------------------------------------

def sync_readme(version: str, dry_run: bool) -> bool:
    """Replace any vX.Y.Z pattern in README that differs from *version*.
    Skips versions that are part of file paths (preceded by a dot).
    Returns True if changes were made (or would be made in dry-run)."""
    text = README.read_text(encoding="utf-8")

    # Negative lookbehind for '.' and word chars so filenames like
    # 'ReelRename.v1.2.1.png' are not touched
    pattern = re.compile(r'(?<![.\w])v(\d+\.\d+\.\d+)')
    stale   = {m.group(0) for m in pattern.finditer(text) if m.group(1) != version}

    if not stale:
        return False

    updated = pattern.sub(lambda m: f"v{version}" if m.group(1) != version else m.group(0), text)

    print(f"      Replacing {stale} → v{version}")
    if not dry_run:
        README.write_text(updated, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Step 3 – Stage changes
# ---------------------------------------------------------------------------

def stage_changes(dry_run: bool) -> bool:
    """Stage all tracked modifications and any untracked root tool scripts.
    Returns True if anything was staged."""

    # Use _run directly so leading spaces in porcelain output are preserved
    result = _run(["git", "status", "--porcelain"], capture=True, check=False)
    raw    = result.stdout  # do NOT strip — leading spaces are significant
    if not raw.strip():
        return False

    lines  = raw.splitlines()
    to_add = []

    for line in lines:
        if len(line) < 4:
            continue
        xy   = line[0:2]
        path = line[3:]          # preserve leading dots / slashes exactly

        # Strip surrounding quotes git uses for paths with spaces
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]

        # xy[0] = index status, xy[1] = worktree status
        # Only 'git add' files that have UN-staged worktree changes.
        # Files already staged (xy[0] in M/D via git rm --cached etc.) are
        # committed as-is and must NOT be passed to git add again.
        if xy[1] in ("M", "D"):
            to_add.append(path)
        elif xy == "??":
            fname = Path(path).name
            if fname in ROOT_TOOLS:
                to_add.append(path)

    if not to_add:
        return False

    print("      Files to stage:")
    for f in to_add:
        print(f"        + {f}")

    if not dry_run:
        _run(["git", "add", "--"] + to_add)
    return True


# ---------------------------------------------------------------------------
# Step 4 – Commit
# ---------------------------------------------------------------------------

def commit_changes(version: str, message: str | None, dry_run: bool) -> bool:
    """Commit staged changes. Returns True if a commit was made."""
    # Check if anything is actually staged
    staged = _run_out(["git", "diff", "--cached", "--name-only"])
    if not staged:
        return False

    msg = message or f"Release v{version}"
    print(f"      Message : {msg}")
    if not dry_run:
        _run(["git", "commit", "-m", msg])
    return True


# ---------------------------------------------------------------------------
# Step 5 – Push main
# ---------------------------------------------------------------------------

def push_main(dry_run: bool) -> None:
    if dry_run:
        print("      (dry-run) would run: git push origin main")
        return
    _run(["git", "push", "origin", "main"])


# ---------------------------------------------------------------------------
# Step 6 – Tag
# ---------------------------------------------------------------------------

def tag_exists_locally(version: str) -> bool:
    tags = _run_out(["git", "tag", "-l", f"v{version}"])
    return bool(tags)


def tag_exists_remotely(version: str) -> bool:
    result = _run_out(["git", "ls-remote", "--tags", "origin", f"refs/tags/v{version}"])
    return bool(result)


def ensure_tag(version: str, dry_run: bool) -> bool:
    """Create local + remote tag if missing. Returns True if tag was created."""
    tag = f"v{version}"

    if tag_exists_locally(version):
        print(f"      Tag {tag} already exists locally")
        if not tag_exists_remotely(version):
            print(f"      Pushing tag {tag} to origin")
            if not dry_run:
                _run(["git", "push", "origin", tag])
        else:
            print(f"      Tag {tag} already on origin")
        return False

    print(f"      Creating tag {tag}")
    if not dry_run:
        _run(["git", "tag", tag])
        _run(["git", "push", "origin", tag])
    return True


# ---------------------------------------------------------------------------
# Step 7 – GitHub Release
# ---------------------------------------------------------------------------

def release_exists(version: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", f"v{version}"],
        cwd=ROOT, capture_output=True,
    )
    return result.returncode == 0


def _previous_tag(version: str) -> str | None:
    """Return the tag immediately before vX.Y.Z."""
    all_tags = _run_out(["git", "tag", "-l", "--sort=-version:refname"]).splitlines()
    current  = f"v{version}"
    for i, tag in enumerate(all_tags):
        if tag == current and i + 1 < len(all_tags):
            return all_tags[i + 1]
    return None


def _categorise(commits: list[str]) -> str:
    """Sort commit messages into rough markdown sections."""
    features, fixes, tooling, other = [], [], [], []
    feat_kw    = ("add", "new", "feat", "implement", "support", "introduc")
    fix_kw     = ("fix", "bug", "patch", "correct", "resolv", "repair")
    tool_kw    = ("build", "release", "deploy", "ci", "script", "backup", "push", "sync", "gitignore")

    for msg in commits:
        low = msg.lower()
        if any(k in low for k in feat_kw):
            features.append(msg)
        elif any(k in low for k in fix_kw):
            fixes.append(msg)
        elif any(k in low for k in tool_kw):
            tooling.append(msg)
        else:
            other.append(msg)

    sections = []
    if features:
        sections.append("### ✨ New Features\n" + "\n".join(f"- {c}" for c in features))
    if fixes:
        sections.append("### 🐛 Fixes\n" + "\n".join(f"- {c}" for c in fixes))
    if tooling:
        sections.append("### 🔧 Tooling\n" + "\n".join(f"- {c}" for c in tooling))
    if other:
        sections.append("### 🔄 Changes\n" + "\n".join(f"- {c}" for c in other))
    return "\n\n".join(sections)


def generate_release_notes(version: str) -> str:
    prev = _previous_tag(version)
    ref  = f"{prev}..HEAD" if prev else "HEAD"
    log  = _run_out(["git", "log", ref, "--pretty=format:%s", "--no-merges"])

    commits = [l.strip() for l in log.splitlines() if l.strip()]
    if not commits:
        return f"Release v{version}"

    header = f"## ReelRename v{version}\n"
    if prev:
        header += f"_Changes since {prev}_\n"
    return header + "\n" + _categorise(commits)


def find_installer(version: str) -> Path | None:
    candidate = RELEASE_DIR / f"ReelRename-Setup-{version}.exe"
    return candidate if candidate.exists() else None


def ensure_github_release(version: str, notes: str | None, dry_run: bool) -> None:
    tag = f"v{version}"

    if release_exists(version):
        print(f"      GitHub Release {tag} already exists — skipping")
        return

    auto_notes = notes or generate_release_notes(version)
    installer  = find_installer(version)

    print(f"      Creating GitHub Release {tag}")
    print()
    # Print notes indented for readability
    for line in auto_notes.splitlines():
        print(f"        {line}")
    print()

    if installer:
        print(f"      Attaching : {installer.relative_to(ROOT)}")
    else:
        print(f"      WARNING   : No installer found at release/ReelRename-Setup-{version}.exe")

    if dry_run:
        print(f"      (dry-run) would run: gh release create {tag}")
        return

    cmd = [
        "gh", "release", "create", tag,
        "--title", f"ReelRename {tag}",
        "--notes", auto_notes,
    ]
    if installer:
        cmd.append(str(installer))

    _run(cmd)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    dry_run: bool,
    skip_release: bool,
    message: str | None,
    notes: str | None,
) -> None:
    sep = "=" * 62

    version = read_version()

    print(sep)
    print("  ReelRename – Git Sync & GitHub Release Publisher")
    print(sep)
    print(f"  Version : v{version}")
    print(f"  Mode    : {'DRY RUN (nothing written or pushed)' if dry_run else 'LIVE'}")
    print(sep)

    # ── Step 1: README sync ─────────────────────────────────────────────────
    print(f"\n[1] Sync README.md version references → v{version}")
    changed = sync_readme(version, dry_run)
    if not changed:
        print("      Already up to date")

    # ── Step 2: Stage ───────────────────────────────────────────────────────
    print("\n[2] Stage changes")
    staged = stage_changes(dry_run)
    if not staged:
        print("      Nothing to stage")

    # ── Step 3: Commit ──────────────────────────────────────────────────────
    print("\n[3] Commit")
    committed = commit_changes(version, message, dry_run)
    if not committed:
        print("      Nothing to commit")

    # ── Step 4: Push main ───────────────────────────────────────────────────
    print("\n[4] Push → origin/main")
    push_main(dry_run)
    if not dry_run:
        print("      Done")

    # ── Step 5: Tag ─────────────────────────────────────────────────────────
    print(f"\n[5] Tag v{version}")
    ensure_tag(version, dry_run)

    # ── Step 6: GitHub Release ──────────────────────────────────────────────
    if skip_release:
        print("\n[6] GitHub Release  — skipped (--skip-release)")
    elif not _gh_available():
        print("\n[6] GitHub Release  — skipped (gh CLI not found)")
    else:
        print(f"\n[6] GitHub Release v{version}")
        ensure_github_release(version, notes, dry_run)

    # ── Done ────────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    if dry_run:
        print("  DRY RUN complete – no changes were made.")
    else:
        print(f"  All done!  v{version} is live on GitHub.")
        print(f"  https://github.com/SecuredNodeDynamics/ReelRename/releases/tag/v{version}")
    print(sep)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="git.push.py",
        description="Sync README, commit, push, tag, and publish a GitHub Release.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview every step without writing or pushing anything",
    )
    parser.add_argument(
        "--skip-release", action="store_true",
        help="Push code and tag only; do not create a GitHub Release",
    )
    parser.add_argument(
        "--message", metavar="MSG",
        help='Override the auto-generated commit message (default: "Release vX.Y.Z")',
    )
    parser.add_argument(
        "--notes", metavar="TEXT",
        help="Override the auto-generated GitHub Release notes",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run_pipeline(
            dry_run=args.dry_run,
            skip_release=args.skip_release,
            message=args.message,
            notes=args.notes,
        )
    except KeyboardInterrupt:
        print("\n\n  Aborted.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"\n  ERROR: command failed → {' '.join(exc.cmd)}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
