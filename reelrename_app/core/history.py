from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class RenameOp:
    src: str
    dst: str


def _app_data_dir() -> Path:
    """
    Cross-platform app data folder:
      - Linux: ~/.config/ReelRename
      - Windows: %APPDATA%\\ReelRename
      - macOS: ~/Library/Application Support/ReelRename (basic support)
    """
    home = Path.home()

    if os.name == "nt":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / "ReelRename"
        return home / "AppData" / "Roaming" / "ReelRename"

    # macOS
    if sys_platform().lower() == "darwin":
        return home / "Library" / "Application Support" / "ReelRename"

    # Linux/Unix
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "ReelRename"
    return home / ".config" / "ReelRename"


def sys_platform() -> str:
    # local helper to avoid importing platform everywhere
    import platform
    return platform.system()


def history_path() -> Path:
    d = _app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_rename.json"


def save_last_run(ops: List[RenameOp]) -> None:
    p = history_path()
    payload = {
        "version": 1,
        "ops": [asdict(op) for op in ops],
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_last_run() -> List[RenameOp]:
    p = history_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ops = data.get("ops", [])
        out: List[RenameOp] = []
        for o in ops:
            if isinstance(o, dict) and "src" in o and "dst" in o:
                out.append(RenameOp(src=str(o["src"]), dst=str(o["dst"])))
        return out
    except Exception:
        return []


def clear_last_run() -> None:
    p = history_path()
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass
