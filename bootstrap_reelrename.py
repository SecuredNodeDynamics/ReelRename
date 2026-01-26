from __future__ import annotations

from pathlib import Path


FILES: dict[str, str] = {
    "reelrename_app/__init__.py": "",
    "reelrename_app/main.py": """\
import sys
from PySide6.QtWidgets import QApplication
from reelrename_app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ReelRename")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
""",
    "reelrename_app/core/__init__.py": "",
    "reelrename_app/core/scanner.py": """\
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set


MEDIA_EXTS: Set[str] = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm"
}


@dataclass(frozen=True)
class MediaItem:
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()

    @property
    def parent(self) -> str:
        return str(self.path.parent)


def is_media_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in MEDIA_EXTS


def scan_paths(paths: Iterable[str]) -> List[MediaItem]:
    \"""
    Accepts file/folder paths.
    - Files: include if media
    - Folders: recursively add media files
    De-dupes by resolved absolute path.
    \"""
    found: List[MediaItem] = []
    seen: Set[Path] = set()

    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            continue

        if p.is_file():
            if is_media_file(p):
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    found.append(MediaItem(rp))
            continue

        if p.is_dir():
            for f in p.rglob("*"):
                if is_media_file(f):
                    rp = f.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        found.append(MediaItem(rp))

    found.sort(key=lambda x: (x.parent.lower(), x.name.lower()))
    return found
""",
    "reelrename_app/ui/__init__.py": "",
    "reelrename_app/ui/main_window.py": """\
from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QLabel, QMessageBox, QAbstractItemView, QHeaderView, QStatusBar
)

from reelrename_app.core.scanner import scan_paths, MediaItem


class DropHint(QLabel):
    def __init__(self) -> None:
        super().__init__("Drag & drop media files or folders here")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(80)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #4b5563; border-radius: 10px; padding: 14px; }"
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ReelRename")
        self.resize(1050, 650)

        self._items: List[MediaItem] = []

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        layout.addLayout(top)

        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_clear = QPushButton("Clear List")

        top.addWidget(self.btn_add_files)
        top.addWidget(self.btn_add_folder)
        top.addWidget(self.btn_clear)
        top.addStretch(1)

        self.drop_hint = DropHint()
        layout.addWidget(self.drop_hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder", "Proposed Name (v1 placeholder)"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.setStatusBar(QStatusBar())
        self._update_status()

        self.setAcceptDrops(True)
        self.drop_hint.setAcceptDrops(False)

        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_clear.clicked.connect(self._clear)

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select media files",
            str(Path.home()),
            "Media Files (*.mkv *.mp4 *.avi *.mov *.m4v *.wmv *.flv *.webm);;All Files (*)"
        )
        if files:
            self._add_paths(files)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder", str(Path.home()))
        if folder:
            self._add_paths([folder])

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self._add_paths(paths)
        event.acceptProposedAction()

    def _add_paths(self, paths: List[str]) -> None:
        new_items = scan_paths(paths)
        if not new_items:
            QMessageBox.information(self, "Nothing Found", "No supported media files were found.")
            return

        existing = {str(i.path) for i in self._items}
        added = 0
        for item in new_items:
            if str(item.path) not in existing:
                self._items.append(item)
                existing.add(str(item.path))
                added += 1

        if added:
            self._render_table()
        else:
            QMessageBox.information(self, "No New Files", "Those files are already in the list.")

    def _render_table(self) -> None:
        self.table.setRowCount(0)
        for item in self._items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(r, 0, QTableWidgetItem(item.name))
            self.table.setItem(r, 1, QTableWidgetItem(item.parent))

            proposed = item.name  # later replaced by naming engine
            self.table.setItem(r, 2, QTableWidgetItem(proposed))

        self._update_status()

    def _clear(self) -> None:
        self._items.clear()
        self.table.setRowCount(0)
        self._update_status()

    def _update_status(self) -> None:
        self.statusBar().showMessage(f"Items loaded: {len(self._items)}")
""",
}


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Don’t overwrite existing work.
        print(f"SKIP (exists): {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"CREATE: {path}")


def main() -> None:
    root = Path(__file__).resolve().parent
    for rel, content in FILES.items():
        write_file(root / rel, content)

    print("\nDone.")
    print("Next:")
    print("  1) pip install PySide6")
    print("  2) Run: python -m reelrename_app.main")


if __name__ == "__main__":
    main()
