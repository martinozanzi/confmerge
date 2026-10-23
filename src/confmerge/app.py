"""Punto di ingresso dell'applicazione grafica."""
from __future__ import annotations

import sys

from . import __version__, paths


def main() -> int:
    paths.setup_logging()
    paths.cleanup_stale()
    from PySide6.QtWidgets import QApplication
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("ConfMerge")
    app.setApplicationVersion(__version__)
    app.aboutToQuit.connect(paths.cleanup_temp)
    win = MainWindow()
    win.show()
    try:  # splash screen di PyInstaller (solo nel target onefile)
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except Exception:
        pass
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
