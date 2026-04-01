#!/usr/bin/env python3
"""
gen.backup.py  –  ReelRename full project backup generator

Creates a timestamped, compressed zip archive of all project source files
(including gitignored build scripts and assets) while skipping virtual
environments, build artefacts, release binaries, and sensitive data.

Usage:
    python gen.backup.py
    python gen.backup.py --output-dir "D:/MyBackups"
    python gen.backup.py --dry-run

Output:
    backups/ReelRename-backup-v1.2.10-20260211-143022.zip
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root (directory that contains this script)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

# Any folder with one of these names (anywhere in the tree) is skipped entirely
EXCLUDE_DIRS: set[str] = {
    ".git",
    ".venv",
    "venv",
    ".idea",
    ".vs",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "release",
    "backups",      # never include previous backup archives
    "node_modules",
}

# Filenames / glob patterns that are always excluded
EXCLUDE_FILE_PATTERNS: list[str] = [
    ".env",
    ".env.*",       # .env.local, .env.production, etc.
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.manifest",
    "Thumbs.db",
    "Desktop.ini",
    ".DS_Store",
]

# File extensions that are always excluded
EXCLUDE_EXTENSIONS: set[str] = {
    ".exe",
    ".zip",
    ".gz",
    ".tar",
    ".AppImage",
    ".iso",
    ".dmg",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_exclude(path: Path) -> bool:
    """Return True if *path* should be left out of the backup."""
    rel = path.relative_to(PROJECT_ROOT)

    # Check every ancestor folder
    for part in rel.parts[:-1]:
        if part in EXCLUDE_DIRS:
            return True

    # Check the file itself for dir-exclusion names (handles top-level dirs)
    if path.is_dir() and path.name in EXCLUDE_DIRS:
        return True

    fname = path.name

    # Glob-pattern exclusions (matched against filename only)
    for pat in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(fname, pat):
            return True

    # Extension exclusions
    if path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True

    return False


def _read_version() -> str:
    """Read APP_VERSION from main_window.py."""
    mw = PROJECT_ROOT / "reelrename_app" / "ui" / "main_window.py"
    if mw.exists():
        text = mw.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    return "unknown"


def _collect_files() -> list[Path]:
    """Walk PROJECT_ROOT and return every file that should be backed up."""
    files: list[Path] = []
    for p in sorted(PROJECT_ROOT.rglob("*")):
        if p.is_file() and not _should_exclude(p):
            files.append(p)
    return files


# ---------------------------------------------------------------------------
# Main backup routine
# ---------------------------------------------------------------------------

def create_backup(output_dir: Path, dry_run: bool = False) -> Path:
    version   = _read_version()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name      = f"ReelRename-backup-v{version}-{timestamp}.zip"

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / name

    files = _collect_files()

    # ---- Report header ----
    print("=" * 60)
    print("  ReelRename – Project Backup Generator")
    print("=" * 60)
    print(f"  Version    : {version}")
    print(f"  Timestamp  : {timestamp}")
    print(f"  Project    : {PROJECT_ROOT}")
    print(f"  Archive    : {archive_path}")
    print(f"  Mode       : {'DRY RUN (no file written)' if dry_run else 'WRITE'}")
    print(f"  Files      : {len(files)}")
    print("=" * 60)

    if not files:
        print("\n  [WARNING] No files found to back up.")
        return archive_path

    # ---- Write archive ----
    if not dry_run:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for fp in files:
                arcname = fp.relative_to(PROJECT_ROOT)
                zf.write(fp, arcname=arcname)
                print(f"  + {arcname}")
    else:
        for fp in files:
            print(f"  + {fp.relative_to(PROJECT_ROOT)}")

    # ---- Summary ----
    print()
    if not dry_run:
        size_kb = archive_path.stat().st_size / 1024
        print(f"  Files archived : {len(files)}")
        print(f"  Archive size   : {size_kb:.1f} KB")
        print(f"  Saved to       : {archive_path}")
    else:
        print(f"  Files that would be archived : {len(files)}")
        print("  (Dry run — no archive written)")

    print("=" * 60)
    return archive_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gen.backup.py",
        description="Create a full source backup of the ReelRename project.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "backups",
        metavar="DIR",
        help="Folder to write the zip archive into (default: ./backups)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be included without writing the archive",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        out = create_backup(output_dir=args.output_dir, dry_run=args.dry_run)
        if not args.dry_run:
            print(f"\n  Backup complete.")
    except KeyboardInterrupt:
        print("\n  Aborted.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
