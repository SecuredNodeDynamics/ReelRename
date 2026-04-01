#!/usr/bin/env python3
"""
app.build.py  –  ReelRename build & release pipeline

Bumps the app version, rebuilds the .exe via PyInstaller, then compiles a
ready-to-distribute installer with Inno Setup.

Usage:
    python app.build.py                        # patch bump  (1.2.10 → 1.2.11)
    python app.build.py --bump minor           # minor bump  (1.2.10 → 1.3.0)
    python app.build.py --bump major           # major bump  (1.2.10 → 2.0.0)
    python app.build.py --version 2.0.0        # exact version
    python app.build.py --dry-run              # preview steps, write nothing
    python app.build.py --skip-backup          # skip the pre-build source backup
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (all relative to this script's directory)
# ---------------------------------------------------------------------------
ROOT          = Path(__file__).resolve().parent
MAIN_WIN      = ROOT / "reelrename_app" / "ui" / "main_window.py"
SPEC_FILE     = ROOT / "reelrename.spec"
INSTALLER_ISS = ROOT / "installer.iss"
VENV_PYTHON   = ROOT / ".venv" / "Scripts" / "python.exe"
INNO_SETUP    = Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe")
BACKUP_SCRIPT = ROOT / "gen.backup.py"

# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def read_version() -> str:
    """Read APP_VERSION from main_window.py."""
    text = MAIN_WIN.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise RuntimeError("APP_VERSION not found in main_window.py")
    return m.group(1)


def bump_version(version: str, part: str) -> str:
    """Return a new version string with the requested part incremented."""
    try:
        major, minor, patch = (int(x) for x in version.split("."))
    except ValueError:
        raise ValueError(f"Cannot parse version '{version}' – expected X.Y.Z")

    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    # default: patch
    return f"{major}.{minor}.{patch + 1}"


def validate_version(v: str) -> str:
    """Raise if *v* is not in X.Y.Z format."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise ValueError(f"Version must be X.Y.Z (got '{v}')")
    return v


# ---------------------------------------------------------------------------
# File-update helpers
# ---------------------------------------------------------------------------

def write_version_to_main(new_ver: str, dry_run: bool) -> None:
    text = MAIN_WIN.read_text(encoding="utf-8")
    updated = re.sub(
        r'(APP_VERSION\s*=\s*)["\'][^"\']+["\']',
        rf'\g<1>"{new_ver}"',
        text,
    )
    if text == updated:
        raise RuntimeError("APP_VERSION replacement had no effect – pattern mismatch?")
    if not dry_run:
        MAIN_WIN.write_text(updated, encoding="utf-8")


def write_version_to_iss(new_ver: str, dry_run: bool) -> None:
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    updated = re.sub(
        r'(#define MyAppVersion\s*")[^"]+(")',
        rf'\g<1>{new_ver}\g<2>',
        text,
    )
    if text == updated:
        raise RuntimeError("#define MyAppVersion replacement had no effect – pattern mismatch?")
    if not dry_run:
        INSTALLER_ISS.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], label: str) -> None:
    """Run a subprocess and raise a clean error on failure."""
    print(f"\n  Running: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def check_prerequisites() -> list[str]:
    """Return a list of missing prerequisite descriptions."""
    issues: list[str] = []
    if not VENV_PYTHON.exists():
        issues.append(f"Python venv not found: {VENV_PYTHON}")
    if not SPEC_FILE.exists():
        issues.append(f"PyInstaller spec not found: {SPEC_FILE}")
    if not INSTALLER_ISS.exists():
        issues.append(f"Inno Setup script not found: {INSTALLER_ISS}")
    if not INNO_SETUP.exists():
        issues.append(f"Inno Setup compiler not found: {INNO_SETUP}")
    return issues


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

def build(new_ver: str, old_ver: str, dry_run: bool, skip_backup: bool) -> None:
    sep = "=" * 60

    print(sep)
    print("  ReelRename – Build & Release Pipeline")
    print(sep)
    print(f"  Version    : {old_ver}  →  {new_ver}")
    print(f"  Mode       : {'DRY RUN (no changes written)' if dry_run else 'RELEASE BUILD'}")
    print(sep)

    # ── Step 1: Pre-build source backup ─────────────────────────────────────
    step = 1
    print(f"\n[{step}] Pre-build source backup")
    if skip_backup:
        print("      Skipped (--skip-backup)")
    elif not BACKUP_SCRIPT.exists():
        print("      Skipped (gen.backup.py not found)")
    else:
        if not dry_run:
            run([str(VENV_PYTHON), str(BACKUP_SCRIPT)], "Source backup")
        else:
            print("      (dry-run) would run gen.backup.py")

    # ── Step 2: Bump version in source files ────────────────────────────────
    step += 1
    print(f"\n[{step}] Update version: {old_ver} → {new_ver}")
    print(f"      {MAIN_WIN.relative_to(ROOT)}")
    write_version_to_main(new_ver, dry_run)
    print(f"      {INSTALLER_ISS.relative_to(ROOT)}")
    write_version_to_iss(new_ver, dry_run)
    if dry_run:
        print("      (dry-run) files not written")

    # ── Step 3: PyInstaller ─────────────────────────────────────────────────
    step += 1
    print(f"\n[{step}] PyInstaller  →  dist/ReelRename.exe")
    if dry_run:
        print(f"      (dry-run) would run: pyinstaller {SPEC_FILE.name} --clean")
    else:
        run(
            [str(VENV_PYTHON), "-m", "PyInstaller", str(SPEC_FILE), "--clean"],
            "PyInstaller",
        )

    # ── Step 4: Inno Setup ──────────────────────────────────────────────────
    step += 1
    installer_out = ROOT / "release" / f"ReelRename-Setup-{new_ver}.exe"
    print(f"\n[{step}] Inno Setup   →  {installer_out.relative_to(ROOT)}")
    if dry_run:
        print(f"      (dry-run) would run: ISCC.exe {INSTALLER_ISS.name}")
    else:
        run([str(INNO_SETUP), str(INSTALLER_ISS)], "Inno Setup")

    # ── Done ────────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    if dry_run:
        print("  DRY RUN complete – no files were modified or built.")
    else:
        print(f"  Build complete!")
        print(f"  Installer : {installer_out}")
    print(sep)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="app.build.py",
        description="Bump version, build exe, and compile installer for ReelRename.",
    )

    ver_group = parser.add_mutually_exclusive_group()
    ver_group.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        default="patch",
        help="Which version component to increment (default: patch)",
    )
    ver_group.add_argument(
        "--version",
        metavar="X.Y.Z",
        help="Set an explicit version instead of auto-bumping",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all steps without writing any files or running builds",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip the pre-build source backup step",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Validate prerequisites
    issues = check_prerequisites()
    if issues:
        print("ERROR – missing prerequisites:")
        for issue in issues:
            print(f"  • {issue}")
        sys.exit(1)

    # Determine versions
    old_ver = read_version()
    if args.version:
        new_ver = validate_version(args.version)
    else:
        new_ver = bump_version(old_ver, args.bump)

    if old_ver == new_ver and not args.dry_run:
        print(f"WARNING: new version ({new_ver}) is the same as the current version.")
        answer = input("Continue anyway? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    try:
        build(new_ver=new_ver, old_ver=old_ver, dry_run=args.dry_run, skip_backup=args.skip_backup)
    except KeyboardInterrupt:
        print("\n\n  Aborted by user.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
