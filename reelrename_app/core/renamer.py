from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from reelrename_app.core.history import RenameOp


@dataclass(frozen=True)
class PlanItem:
    src: Path
    dst: Path
    reason: str = ""


def build_rename_plan_paths(src_paths: List[Path], dst_paths: List[Path]) -> Tuple[List[PlanItem], List[PlanItem]]:
    """
    Build a safe plan for rename/move:
      - do NOT overwrite existing files
      - detect duplicate targets in the same run
      - skip no-op
    Returns (ok_plan, skipped/conflicts)
    """
    if len(src_paths) != len(dst_paths):
        raise ValueError("src_paths and dst_paths length mismatch")

    ok: List[PlanItem] = []
    bad: List[PlanItem] = []
    seen_targets = set()

    for src, dst in zip(src_paths, dst_paths):
        src = src.resolve()
        dst = dst.resolve()

        if src == dst:
            bad.append(PlanItem(src=src, dst=dst, reason="No change"))
            continue

        # Don't overwrite
        if dst.exists():
            bad.append(PlanItem(src=src, dst=dst, reason="Target already exists"))
            continue

        # Duplicate targets in one run
        key = str(dst).lower()
        if key in seen_targets:
            bad.append(PlanItem(src=src, dst=dst, reason="Duplicate target in this run"))
            continue
        seen_targets.add(key)

        ok.append(PlanItem(src=src, dst=dst))

    return ok, bad


def execute_plan(plan: List[PlanItem]) -> List[RenameOp]:
    """
    Execute rename/move plan safely.
    Uses shutil.move to support cross-device moves.
    Returns ops for undo (src->dst).
    """
    ops: List[RenameOp] = []

    for item in plan:
        if not item.src.exists():
            continue

        item.dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(item.src), str(item.dst))
        ops.append(RenameOp(src=str(item.src), dst=str(item.dst)))

    return ops


def undo_ops(ops: List[RenameOp]) -> Tuple[int, List[str]]:
    """
    Undo ops in reverse order (dst -> src).
    Returns (count_undone, errors).
    """
    undone = 0
    errors: List[str] = []

    for op in reversed(ops):
        src = Path(op.src).resolve()
        dst = Path(op.dst).resolve()

        if not dst.exists():
            errors.append(f"Missing: {dst}")
            continue
        if src.exists():
            errors.append(f"Cannot undo (target exists): {src}")
            continue

        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            undone += 1
        except Exception as e:
            errors.append(f"Failed undo {dst} -> {src}: {e}")

    return undone, errors
