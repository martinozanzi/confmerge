"""Punto di ingresso dell'applicazione grafica."""
from __future__ import annotations

import sys

from . import __version__, paths


def main() -> int:
    paths.setup_logging()
    paths.cleanup_stale()
    from PySide6.QtWidgets import QApplication
    from .ui.main_window import MainWindow

    if sys.platform == "win32":      # senza questo Windows raggruppa la finestra sotto l'icona di Python
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MartinoZanzi.ConfMerge")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    from .ui.brand import app_icon
    app.setWindowIcon(app_icon())
    app.setApplicationName("ConfMerge")
    app.setApplicationVersion(__version__)
    app.aboutToQuit.connect(paths.cleanup_temp)
    from .ui.state import AppState
    from .ui.theme import theme
    state = AppState()
    theme.apply(app)
    win = MainWindow(state)
    from .ui.theme import set_titlebar
    win.show()
    set_titlebar(win, theme.t.name == "dark")
    try:  # splash screen di PyInstaller (solo nel target onefile)
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except Exception:
        pass
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
