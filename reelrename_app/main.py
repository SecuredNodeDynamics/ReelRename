import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from reelrename_app.ui.main_window import MainWindow
from reelrename_app.ui.theme import dark_palette


def user_env_path() -> Path:
    """
    Cross-platform per-user env file location.
    - Linux: ~/.config/ReelRename/.env
    - Windows: %APPDATA%\\ReelRename\\.env
    - Fallback: ~/.config/ReelRename/.env
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "ReelRename" / ".env"
    return Path.home() / ".config" / "ReelRename" / ".env"


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def main() -> int:
    # Load local .env (project folder / working dir) first
    load_dotenv()

    # Load per-user saved key second (overrides local)
    uenv = user_env_path()
    if uenv.exists():
        load_dotenv(dotenv_path=str(uenv), override=True)

    app = QApplication(sys.argv)
    app.setApplicationName("ReelRename")
    app.setPalette(dark_palette())

    # App icon (works dev + PyInstaller)
    icon_ico = resource_path("assets", "icon.ico")
    icon = None
    if icon_ico.exists():
        icon = QIcon(str(icon_ico))
        if not icon.isNull():
            app.setWindowIcon(icon)

    win = MainWindow()
    if icon and not icon.isNull():
        win.setWindowIcon(icon)

    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
