from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QLabel, QMessageBox, QAbstractItemView, QHeaderView, QStatusBar,
    QComboBox, QLineEdit, QMenu, QInputDialog,
    QDialog, QTextBrowser, QDialogButtonBox
)

from dotenv import load_dotenv

from reelrename_app.core.scanner import scan_paths, MediaItem
from reelrename_app.ui.theme import dark_palette, light_palette

from reelrename_app.core.parser import parse_filename
from reelrename_app.core.classifier import classify, MediaType
from reelrename_app.core.cache import YearCache
from reelrename_app.core.providers.tmdb import TmdbClient

from reelrename_app.core.templates import build_destination
from reelrename_app.core.renamer import build_rename_plan_paths, execute_plan, undo_ops
from reelrename_app.core.history import save_last_run, load_last_run, clear_last_run


APP_NAME = "ReelRename"
APP_VERSION = "1.1.2"


class DropHint(QLabel):
    def __init__(self) -> None:
        super().__init__("Drag & drop media files or folders here")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(80)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #4b5563; border-radius: 10px; padding: 14px; }"
        )


class MainWindow(QMainWindow):
    # Column indexes
    COL_TYPE = 0
    COL_NAME = 1
    COL_FOLDER = 2
    COL_PROPOSED_NAME = 3
    COL_DEST = 4

    # Windows filename constraints (safe cross-platform baseline)
    _INVALID_WIN_CHARS = '<>:"/\\|?*'
    _RESERVED_WIN_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        *{f"COM{i}" for i in range(1, 10)},
        *{f"LPT{i}" for i in range(1, 10)},
    }

    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self.is_dark = True

        self.setWindowTitle(APP_NAME)
        self.resize(1320, 760)

        self._items: List[MediaItem] = []
        self._dst_paths: List[Path] = []

        # Manual overrides & locking
        self._override_dst: Dict[str, Path] = {}
        self._locked: Set[str] = set()
        self._rendering = False

        # edit guard to avoid recursive cellChanged events
        self._editing = False

        # Preflight status
        self._row_issues: Dict[int, List[str]] = {}
        self._row_has_error: Set[int] = set()

        # Remember last render mode/root for helpers
        self._last_effective_move = False
        self._last_root: Optional[Path] = None

        # Year lookup helpers
        self.year_cache = YearCache()
        self.tmdb = TmdbClient()
        self._warned_tmdb_missing_key = False

        # ----- Menus -----
        # View menu
        view_menu = self.menuBar().addMenu("View")

        self.action_toggle_theme = QAction("Toggle Dark / Light", self)
        self.action_toggle_theme.triggered.connect(self.toggle_theme)
        view_menu.addAction(self.action_toggle_theme)

        self.action_toggle_folder = QAction("Show Current Folder", self)
        self.action_toggle_folder.setCheckable(True)
        self.action_toggle_folder.setChecked(True)
        self.action_toggle_folder.triggered.connect(self._toggle_current_folder)
        view_menu.addAction(self.action_toggle_folder)

        # Connect menu
        connect_menu = self.menuBar().addMenu("Connect")
        self.action_set_tmdb_key = QAction("Set TMDb API Key…", self)
        self.action_set_tmdb_key.triggered.connect(self._set_tmdb_api_key)
        connect_menu.addAction(self.action_set_tmdb_key)

        # Help menu
        help_menu = self.menuBar().addMenu("Help")

        self.action_user_guide = QAction("User Guide", self)
        self.action_user_guide.triggered.connect(self._show_user_guide)
        help_menu.addAction(self.action_user_guide)

        self.action_about = QAction("About ReelRename", self)
        self.action_about.triggered.connect(self._show_about)
        help_menu.addAction(self.action_about)

        # Central UI
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Top controls row 1
        top1 = QHBoxLayout()
        layout.addLayout(top1)

        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_clear = QPushButton("Clear List")
        self.btn_rename = QPushButton("Rename")
        self.btn_undo = QPushButton("Undo Last Rename")

        top1.addWidget(self.btn_add_files)
        top1.addWidget(self.btn_add_folder)
        top1.addWidget(self.btn_clear)
        top1.addSpacing(12)
        top1.addWidget(self.btn_rename)
        top1.addWidget(self.btn_undo)
        top1.addStretch(1)

        # Top controls row 2
        top2 = QHBoxLayout()
        layout.addLayout(top2)

        top2.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Rename in place", "Rename + Move (Library Root)"])
        top2.addWidget(self.mode_combo)

        top2.addSpacing(12)
        top2.addWidget(QLabel("Library Root:"))
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Select a library root folder (required for Move mode)")
        self.btn_browse_root = QPushButton("Browse…")

        top2.addWidget(self.root_edit, 1)
        top2.addWidget(self.btn_browse_root)

        # Drop hint
        self.drop_hint = DropHint()
        layout.addWidget(self.drop_hint)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Type",
            "File Name",
            "Current Folder",
            "Proposed Name",
            "Proposed Destination",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Allow click-to-edit + double-click (plays nicer with SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )

        self.table.horizontalHeader().setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_FOLDER, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_PROPOSED_NAME, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_DEST, QHeaderView.Stretch)

        self.table.setStyleSheet("""
QHeaderView::section {
    font-weight: 600;
    padding: 6px;
}

QTableWidget::item:hover {
    background-color: rgba(255, 255, 255, 0.06);
}
""")

        layout.addWidget(self.table)

        # Context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellChanged.connect(self._on_cell_changed)

        # Status bar
        self.setStatusBar(QStatusBar())
        self._update_status()

        # Enable drops
        self.setAcceptDrops(True)
        self.drop_hint.setAcceptDrops(False)

        # Signals
        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_rename.clicked.connect(self._rename_now)
        self.btn_undo.clicked.connect(self._undo_last)

        self.btn_browse_root.clicked.connect(self._pick_library_root)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.root_edit.textChanged.connect(lambda: self._render_table())

        self._on_mode_changed()
        self._toggle_current_folder()
        self._refresh_buttons()

    # ---------------------------
    # Help dialogs
    # ---------------------------
    def _show_user_guide(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{APP_NAME} — User Guide")
        dlg.resize(760, 560)

        layout = QVBoxLayout(dlg)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(self._user_guide_html())
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)

        dlg.exec()

    def _show_about(self) -> None:
        env_path = self._user_env_path()
        msg = (
            f"<b>{APP_NAME}</b> v{APP_VERSION}<br><br>"
            "Rename and organize Movies, TV Shows, and Anime safely.<br><br>"
            "<b>Key features</b><br>"
            "• Rename-in-place or Move to Library Root<br>"
            "• Proposed Name + Proposed Destination preview<br>"
            "• Manual edits + preflight conflict detection<br>"
            "• Undo last rename run<br>"
            "• TMDb year lookup for movies (optional)<br><br>"
            f"<b>TMDb key location</b><br>{env_path}"
        )
        QMessageBox.information(self, f"About {APP_NAME}", msg)

    def _user_guide_html(self) -> str:
        env_path = self._user_env_path()
        return f"""
        <h2>{APP_NAME} — User Guide</h2>

        <h3>1) Add media</h3>
        <ul>
          <li>Use <b>Add Files</b>, <b>Add Folder</b>, or drag &amp; drop into the drop zone.</li>
          <li>The table shows: <b>Type</b>, original name, and the proposed rename.</li>
        </ul>

        <h3>2) Understand the columns</h3>
        <ul>
          <li><b>Proposed Name</b> = the new filename only.</li>
          <li><b>Proposed Destination</b> = full final path.</li>
        </ul>

        <h3>3) Rename modes</h3>
        <ul>
          <li><b>Rename in place</b>: keeps files in the current folder, only changes the filename.</li>
          <li><b>Rename + Move (Library Root)</b>: moves files into organized folders under your chosen Library Root.</li>
        </ul>

        <h3>4) Manual edits, validation &amp; preflight</h3>
        <ul>
          <li>You can edit <b>Proposed Name</b> or <b>Proposed Destination</b> directly.</li>
          <li>ReelRename validates filenames (Windows-safe) and runs a preflight check for duplicates and conflicts.</li>
          <li>Rows will show:
            <ul>
              <li><b>❌</b> = must fix before renaming</li>
              <li><b>⚠️</b> = warning (you may still rename)</li>
            </ul>
          </li>
          <li>Right-click a row for options (Lock, Reset, Copy).</li>
        </ul>

        <h3>5) TMDb movie year lookup</h3>
        <ul>
          <li>Go to <b>Connect → Set TMDb API Key…</b></li>
          <li>Key is stored here:<br><code>{env_path}</code></li>
          <li>If a movie filename has no year, ReelRename can fetch and append it automatically.</li>
        </ul>

        <h3>6) Safety &amp; Undo</h3>
        <ul>
          <li>Click <b>Rename</b> to apply changes.</li>
          <li>Use <b>Undo Last Rename</b> to roll back the last run (best effort).</li>
        </ul>

        <h3>7) UI tips</h3>
        <ul>
          <li><b>View → Show Current Folder</b> can hide/show the folder column.</li>
          <li><b>View → Toggle Dark / Light</b> switches the theme.</li>
        </ul>
        """

    # ---------------------------
    # View toggles
    # ---------------------------
    def _toggle_current_folder(self) -> None:
        visible = self.action_toggle_folder.isChecked()
        self.table.setColumnHidden(self.COL_FOLDER, not visible)

    # ---------------------------
    # Per-user env location
    # ---------------------------
    def _user_env_path(self) -> Path:
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata:
                return Path(appdata) / "ReelRename" / ".env"
        return Path.home() / ".config" / "ReelRename" / ".env"

    def _write_tmdb_key_to_user_env(self, api_key: str) -> Path:
        env_path = self._user_env_path()
        env_path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        if env_path.exists():
            try:
                lines = env_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []

        new_lines = []
        replaced = False
        for line in lines:
            if line.strip().startswith("TMDB_API_KEY="):
                new_lines.append(f"TMDB_API_KEY={api_key}")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            new_lines.append(f"TMDB_API_KEY={api_key}")

        env_path.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")
        return env_path

    def _set_tmdb_api_key(self) -> None:
        current = os.environ.get("TMDB_API_KEY", "").strip()

        key, ok = QInputDialog.getText(
            self,
            "Set TMDb API Key",
            "Paste your TMDb API key:\n(It will be saved to your user config and used immediately.)",
            QLineEdit.Password,
            current,
        )
        if not ok:
            return

        key = (key or "").strip()
        if not key:
            QMessageBox.warning(self, "Invalid Key", "API key cannot be empty.")
            return

        try:
            env_path = self._write_tmdb_key_to_user_env(key)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save API key:\n{e}")
            return

        os.environ["TMDB_API_KEY"] = key
        load_dotenv(dotenv_path=str(env_path), override=True)

        self.tmdb = TmdbClient()
        self._warned_tmdb_missing_key = False

        self.statusBar().showMessage(f"TMDb API key saved to: {env_path}", 6000)

        if self._items:
            self._render_table()

    # ---------------------------
    # Theme toggle
    # ---------------------------
    def toggle_theme(self) -> None:
        if self.is_dark:
            self.app.setPalette(light_palette())
        else:
            self.app.setPalette(dark_palette())
        self.is_dark = not self.is_dark

    # ---------------------------
    # Mode / Root selection
    # ---------------------------
    def _on_mode_changed(self) -> None:
        move_mode = self._move_enabled()
        self.root_edit.setEnabled(move_mode)
        self.btn_browse_root.setEnabled(move_mode)
        self._render_table()

    def _move_enabled(self) -> bool:
        return self.mode_combo.currentIndex() == 1

    def _library_root(self) -> Optional[Path]:
        text = self.root_edit.text().strip()
        if not text:
            return None
        return Path(text).expanduser()

    def _pick_library_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Library Root", str(Path.home()))
        if folder:
            self.root_edit.setText(folder)

    # ---------------------------
    # File picking
    # ---------------------------
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

    # ---------------------------
    # Drag & drop
    # ---------------------------
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

    # ---------------------------
    # Validation & preflight
    # ---------------------------
    def _sanitize_filename(self, name: str, keep_ext: str | None = None) -> Tuple[str, List[str]]:
        """
        Returns (sanitized_name, notes). Notes contains changes/warnings.
        keep_ext: if provided and name has no suffix, ensure this extension.
        """
        notes: List[str] = []
        raw = (name or "")

        # Strip surrounding whitespace early
        cleaned = raw.strip()
        if cleaned != raw:
            notes.append("Trimmed leading/trailing whitespace.")

        if not cleaned:
            return "", ["Name cannot be empty."]

        # Replace invalid characters
        replaced = "".join("_" if ch in self._INVALID_WIN_CHARS else ch for ch in cleaned)
        if replaced != cleaned:
            notes.append(f"Replaced invalid characters: {self._INVALID_WIN_CHARS}")
        cleaned = replaced

        # Windows: trailing dot/space invalid
        trimmed = cleaned.rstrip(" .")
        if trimmed != cleaned:
            notes.append("Trimmed trailing dot/space (Windows compatibility).")
        cleaned = trimmed

        if not cleaned:
            return "", ["Name became empty after cleanup."]

        # Reserved names on Windows (CON, NUL, COM1, etc.)
        stem = Path(cleaned).stem
        if stem.upper() in self._RESERVED_WIN_NAMES:
            cleaned = f"_{cleaned}"
            notes.append("Prefixed reserved Windows filename.")

        # Add missing extension if requested
        if keep_ext and Path(cleaned).suffix == "":
            cleaned = Path(cleaned).with_suffix(keep_ext).name
            notes.append(f"Added missing extension: {keep_ext}")

        return cleaned, notes

    def _validate_destination_path(self, p: Path) -> List[str]:
        issues: List[str] = []

        fname = p.name
        sanitized, _notes = self._sanitize_filename(fname)
        if not sanitized:
            issues.append("Destination filename is empty/invalid.")
        elif sanitized != fname:
            issues.append("Destination filename contains invalid characters.")

        return issues

    def _apply_preflight_to_table(self) -> None:
        # Avoid recursive signals
        self._editing = True
        try:
            for row in range(self.table.rowCount()):
                type_item = self.table.item(row, self.COL_TYPE)
                if type_item is None:
                    continue

                base_text = type_item.text()
                # Remove any prior indicators
                base_text = base_text.replace(" ❌", "").replace(" ⚠️", "")

                issues = self._row_issues.get(row, [])
                if row in self._row_has_error:
                    type_item.setText(f"{base_text} ❌")
                    type_item.setToolTip("\n".join(issues))
                elif issues:
                    type_item.setText(f"{base_text} ⚠️")
                    type_item.setToolTip("\n".join(issues))
                else:
                    type_item.setText(base_text)
                    type_item.setToolTip("")
        finally:
            self._editing = False

    def _run_preflight(self) -> None:
        self._row_issues.clear()
        self._row_has_error.clear()

        if not self._dst_paths:
            self._apply_preflight_to_table()
            return

        # Duplicate destinations in-batch
        dst_to_rows: Dict[str, List[int]] = {}
        for i, dst in enumerate(self._dst_paths):
            dst_to_rows.setdefault(str(dst), []).append(i)

        for row, dst in enumerate(self._dst_paths):
            issues: List[str] = []

            # Validate name/path
            issues.extend(self._validate_destination_path(dst))

            # Duplicate within batch
            if len(dst_to_rows.get(str(dst), [])) > 1:
                issues.append("Duplicate destination within this batch.")

            # Exists on disk (warning, not always an error)
            try:
                if dst.exists():
                    issues.append("Destination already exists on disk.")
            except Exception:
                issues.append("Could not check destination existence (permission/path issue).")

            if issues:
                self._row_issues[row] = issues

                # Classify hard errors
                hard = False
                if any("invalid" in x.lower() or "empty" in x.lower() for x in issues):
                    hard = True
                if any("Duplicate destination" in x for x in issues):
                    hard = True

                if hard:
                    self._row_has_error.add(row)

        self._apply_preflight_to_table()

    # ---------------------------
    # Data handling
    # ---------------------------
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

    def _try_fill_movie_year(self, title: str) -> int | None:
        cached = self.year_cache.get_movie_year(title)
        if cached:
            return cached

        if not self.tmdb.is_configured():
            if not self._warned_tmdb_missing_key:
                self.statusBar().showMessage("TMDB_API_KEY not set — movie years won't auto-fill.", 8000)
                self._warned_tmdb_missing_key = True
            return None

        try:
            res = self.tmdb.search_movie(title)
            if res and res.year:
                self.year_cache.set_movie_year(title, res.year)
                return res.year
        except Exception:
            return None

        return None

    def _item_key(self, item: MediaItem) -> str:
        return str(item.path)

    def _move_enabled(self) -> bool:
        return self.mode_combo.currentIndex() == 1

    def _compute_auto_destination_for_item(self, item: MediaItem) -> Path:
        """Recompute the auto destination for an item under current mode/root settings."""
        stem = item.path.stem
        parsed = parse_filename(stem)
        mtype = classify(parsed)

        if mtype == MediaType.MOVIE and parsed.year is None and parsed.title:
            year = self._try_fill_movie_year(parsed.title)
            if year:
                parsed = replace(parsed, year=year)

        auto_dst = build_destination(
            src=item.path,
            parsed=parsed,
            media_type=mtype,
            library_root=self._last_root if self._last_effective_move else None,
            move_enabled=self._last_effective_move,
        )
        return Path(auto_dst)

    def _render_table(self) -> None:
        self._rendering = True
        try:
            self.table.setRowCount(0)
            self._dst_paths = []

            if not self._items:
                self._row_issues.clear()
                self._row_has_error.clear()
                self._update_status()
                self._refresh_buttons()
                return

            move_mode = self._move_enabled()
            root = self._library_root() if move_mode else None
            effective_move = move_mode and root is not None and root.exists()

            self._last_root = root
            self._last_effective_move = effective_move

            if move_mode and (root is None or not root.exists()):
                self.statusBar().showMessage(
                    "Move mode enabled: select a valid Library Root to preview destinations.", 8000
                )

            for item in self._items:
                r = self.table.rowCount()
                self.table.insertRow(r)

                key = self._item_key(item)

                auto_dst = self._compute_auto_destination_for_item(item)

                if key in self._override_dst:
                    dst_path = Path(self._override_dst[key])
                else:
                    dst_path = auto_dst

                if key in self._locked and key not in self._override_dst:
                    self._override_dst[key] = auto_dst
                    dst_path = auto_dst

                self._dst_paths.append(dst_path)

                # Type column
                stem = item.path.stem
                parsed = parse_filename(stem)
                mtype = classify(parsed)

                type_text = str(mtype.value)
                if key in self._locked:
                    type_text += " 🔒"

                self.table.setItem(r, self.COL_TYPE, QTableWidgetItem(type_text))
                self.table.setItem(r, self.COL_NAME, QTableWidgetItem(item.name))
                self.table.setItem(r, self.COL_FOLDER, QTableWidgetItem(str(item.parent)))

                # Proposed Name (editable)
                proposed_name_item = QTableWidgetItem(dst_path.name)
                proposed_name_item.setFlags(proposed_name_item.flags() | Qt.ItemIsEditable)
                self.table.setItem(r, self.COL_PROPOSED_NAME, proposed_name_item)

                # Proposed Destination (editable)
                dest_item = QTableWidgetItem(str(dst_path))
                dest_item.setFlags(dest_item.flags() | Qt.ItemIsEditable)
                self.table.setItem(r, self.COL_DEST, dest_item)

            self._run_preflight()
            self._update_status()
            self._refresh_buttons()
        finally:
            self._rendering = False

    def _clear(self) -> None:
        self._items.clear()
        self._dst_paths.clear()
        self._override_dst.clear()
        self._locked.clear()
        self._row_issues.clear()
        self._row_has_error.clear()
        self.table.setRowCount(0)
        self._update_status()
        self._refresh_buttons()

    def _update_status(self) -> None:
        msg = f"Items loaded: {len(self._items)}"
        if self._row_has_error:
            msg += f" — Fix ❌ rows: {len(self._row_has_error)}"
        self.statusBar().showMessage(msg)

    def _refresh_buttons(self) -> None:
        can_rename = len(self._items) > 0

        if self._move_enabled():
            root = self._library_root()
            can_rename = can_rename and root is not None and root.exists()

        # Safety gate: block rename if any hard preflight errors
        if self._row_has_error:
            can_rename = False

        self.btn_rename.setEnabled(can_rename)
        self.btn_undo.setEnabled(len(load_last_run()) > 0)

    def _library_root(self) -> Optional[Path]:
        text = self.root_edit.text().strip()
        if not text:
            return None
        return Path(text).expanduser()

    def _on_cell_changed(self, row: int, col: int) -> None:
        # Ignore table rebuilds and internal sync edits
        if self._rendering or self._editing:
            return

        if row < 0 or row >= len(self._items):
            return

        key = self._item_key(self._items[row])

        def _set_cell(r: int, c: int, text: str) -> None:
            """Update a cell without causing recursive cellChanged loops."""
            self._editing = True
            try:
                it = self.table.item(r, c)
                if it is not None:
                    it.setText(text)
            finally:
                self._editing = False

        # ---- Case 1: Proposed Destination edited directly ----
        if col == self.COL_DEST:
            text = (self.table.item(row, col).text() or "").strip()
            if not text:
                return

            new_dst = Path(text).expanduser()

            # sanitize filename portion
            fname = new_dst.name
            sanitized, notes = self._sanitize_filename(fname)
            if not sanitized:
                self.statusBar().showMessage("Invalid destination filename. Fix the name.", 6000)
                self._dst_paths[row] = new_dst
                self._override_dst[key] = new_dst
                self._run_preflight()
                self._update_status()
                self._refresh_buttons()
                return

            if sanitized != fname:
                new_dst = new_dst.with_name(sanitized)
                _set_cell(row, self.COL_DEST, str(new_dst))
                if notes:
                    self.statusBar().showMessage("Destination adjusted: " + " ".join(notes), 6500)

            self._override_dst[key] = new_dst
            self._dst_paths[row] = new_dst

            # Keep Proposed Name synced
            _set_cell(row, self.COL_PROPOSED_NAME, new_dst.name)

            self._run_preflight()
            self._update_status()
            self._refresh_buttons()
            return

        # ---- Case 2: Proposed Name edited ----
        if col == self.COL_PROPOSED_NAME:
            text = (self.table.item(row, col).text() or "")
            if not text.strip():
                self.statusBar().showMessage("Name cannot be empty.", 5000)
                return

            current_dst = Path(self._dst_paths[row]).expanduser()
            keep_ext = current_dst.suffix if current_dst.suffix else None

            sanitized, notes = self._sanitize_filename(text, keep_ext=keep_ext)
            if not sanitized:
                self.statusBar().showMessage("Invalid name. Fix the filename.", 6000)
                self._run_preflight()
                self._update_status()
                self._refresh_buttons()
                return

            if sanitized != text.strip():
                _set_cell(row, self.COL_PROPOSED_NAME, sanitized)
                if notes:
                    self.statusBar().showMessage("Name adjusted: " + " ".join(notes), 6500)

            new_dst = current_dst.with_name(sanitized)

            self._override_dst[key] = new_dst
            self._dst_paths[row] = new_dst

            # Keep Proposed Destination synced
            _set_cell(row, self.COL_DEST, str(new_dst))

            self._run_preflight()
            self._update_status()
            self._refresh_buttons()
            return

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        if row < 0 or row >= len(self._items):
            return

        item = self._items[row]
        key = self._item_key(item)

        menu = QMenu(self)
        act_lock = QAction("Lock Row" if key not in self._locked else "Unlock Row", self)

        act_reset_name = QAction("Reset Name Only", self)
        act_reset_dest = QAction("Reset Destination Only", self)
        act_reset_all = QAction("Reset to Auto", self)

        act_copy_dest = QAction("Copy Destination", self)
        act_copy_name = QAction("Copy Proposed Name", self)

        menu.addAction(act_lock)
        menu.addSeparator()
        menu.addAction(act_reset_name)
        menu.addAction(act_reset_dest)
        menu.addAction(act_reset_all)
        menu.addSeparator()
        menu.addAction(act_copy_name)
        menu.addAction(act_copy_dest)

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if chosen == act_lock:
            if key in self._locked:
                self._locked.remove(key)
                self.statusBar().showMessage(f"Unlocked: {item.name}", 3000)
            else:
                self._locked.add(key)
                self.statusBar().showMessage(f"Locked: {item.name}", 3000)
            self._render_table()
            return

        if chosen in (act_reset_name, act_reset_dest, act_reset_all):
            auto_dst = self._compute_auto_destination_for_item(item)
            current_dst = Path(self._dst_paths[row])

            if chosen == act_reset_all:
                self._override_dst.pop(key, None)
                self.statusBar().showMessage(f"Reset to auto: {item.name}", 3000)
                self._render_table()
                return

            if chosen == act_reset_dest:
                self._override_dst[key] = auto_dst
                self._dst_paths[row] = auto_dst
                self._editing = True
                try:
                    self.table.item(row, self.COL_PROPOSED_NAME).setText(auto_dst.name)
                    self.table.item(row, self.COL_DEST).setText(str(auto_dst))
                finally:
                    self._editing = False
                self.statusBar().showMessage(f"Reset destination: {item.name}", 3000)
                self._run_preflight()
                self._update_status()
                self._refresh_buttons()
                return

            if chosen == act_reset_name:
                # Keep current folder, restore auto filename
                new_dst = current_dst.with_name(auto_dst.name)
                self._override_dst[key] = new_dst
                self._dst_paths[row] = new_dst
                self._editing = True
                try:
                    self.table.item(row, self.COL_PROPOSED_NAME).setText(new_dst.name)
                    self.table.item(row, self.COL_DEST).setText(str(new_dst))
                finally:
                    self._editing = False
                self.statusBar().showMessage(f"Reset name: {item.name}", 3000)
                self._run_preflight()
                self._update_status()
                self._refresh_buttons()
                return

        if chosen == act_copy_dest:
            dest_text = self.table.item(row, self.COL_DEST).text()
            if dest_text:
                self.app.clipboard().setText(dest_text)
                self.statusBar().showMessage("Destination copied to clipboard", 2500)
            return

        if chosen == act_copy_name:
            name_text = self.table.item(row, self.COL_PROPOSED_NAME).text()
            if name_text:
                self.app.clipboard().setText(name_text)
                self.statusBar().showMessage("Proposed name copied to clipboard", 2500)
            return

    def _rename_now(self) -> None:
        if not self._items:
            return

        if self._row_has_error:
            QMessageBox.warning(
                self,
                "Fix Errors First",
                "One or more rows are marked ❌.\n\nFix those rows before renaming."
            )
            return

        if self._move_enabled():
            root = self._library_root()
            if root is None or not root.exists():
                QMessageBox.warning(self, "Library Root Required", "Please select a valid Library Root folder.")
                return

        src_paths = [i.path for i in self._items]
        ok_plan, bad_plan = build_rename_plan_paths(src_paths, self._dst_paths)

        ok_count = len(ok_plan)
        bad_count = len(bad_plan)

        details = []
        if bad_count:
            preview = "\n".join([f"- {p.src.name} → {p.dst.name} ({p.reason})" for p in bad_plan[:10]])
            details.append(f"Skipped/Conflicts: {bad_count}\n{preview}")
            if bad_count > 10:
                details.append("...")

        msg = f"Ready to apply {ok_count} change(s).\nSkipped/Conflicts: {bad_count}\n\nProceed?"
        if details:
            msg += "\n\n" + "\n".join(details)

        res = QMessageBox.question(self, "Confirm Rename/Move", msg, QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes:
            return

        ops = execute_plan(ok_plan)
        save_last_run(ops)

        dst_map = {op.src: op.dst for op in ops}

        new_items: List[MediaItem] = []
        new_override: Dict[str, Path] = {}
        new_locked: Set[str] = set()

        for item in self._items:
            old_key = self._item_key(item)
            new_path = Path(dst_map.get(str(item.path), str(item.path)))
            new_item = MediaItem(new_path)
            new_items.append(new_item)
            new_key = str(new_item.path)

            if old_key in self._override_dst:
                # preserve overrides where possible
                new_override[new_key] = self._override_dst[old_key]
            if old_key in self._locked:
                new_locked.add(new_key)

        self._items = new_items
        self._override_dst = new_override
        self._locked = new_locked

        self._render_table()
        QMessageBox.information(self, "Complete", f"Applied: {len(ops)}\nSkipped/Conflicts: {bad_count}")

    def _undo_last(self) -> None:
        ops = load_last_run()
        if not ops:
            QMessageBox.information(self, "Undo", "No previous rename/move run found.")
            self._refresh_buttons()
            return

        res = QMessageBox.question(
            self,
            "Undo Last Run",
            f"Undo last run? ({len(ops)} operation(s))",
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        undone, errors = undo_ops(ops)
        clear_last_run()
        self._clear()

        if errors:
            preview = "\n".join(errors[:12])
            QMessageBox.warning(self, "Undo Completed (with issues)", f"Undone: {undone}\n\nIssues:\n{preview}")
        else:
            QMessageBox.information(self, "Undo Completed", f"Undone: {undone}")

        self._refresh_buttons()
