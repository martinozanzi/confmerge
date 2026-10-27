"""Autotest dell'applicazione impacchettata: `ConfMerge.exe --selftest` (esce con 0 se tutto è in ordine).

Controlla risorse (font Inter, icone Lucide), moduli Qt (SVG, PDF, multimedia), ffmpeg/ffprobe e che la finestra
si costruisca in entrambe le modalità. Il risultato è anche in <dati>/selftest.txt (utile perché l'exe non ha console)."""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

from . import paths


def run() -> int:
    lines: list[str] = []
    failed = 0

    def check(name: str, fn) -> None:
        nonlocal failed
        try:
            detail = fn()
            lines.append(f"OK    {name}" + (f" — {detail}" if isinstance(detail, str) and detail else ""))
        except Exception as e:  # noqa: BLE001
            failed += 1
            lines.append(f"ERRORE {name} — {e!r}\n{traceback.format_exc(limit=3)}")

    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from .ui import theme as th

    def fonts():
        th.theme.load_fonts()
        fams = QFontDatabase.families()
        assert "Inter" in fams, "font Inter non caricato"
        for fam in ("Poppins", "Bebas Neue", "Anton"):
            assert fam in fams, f"font {fam} non caricato (servono ai modelli dei titoli)"
        return f"{sum(1 for f in (th.RESOURCES / 'fonts').glob('Inter-*.ttf'))} file"

    def icons():
        n = 0
        for f in (th.RESOURCES / "icons").glob("*.svg"):
            assert not th.icon(f.stem, "#ffffff").isNull(), f.name
            n += 1
        assert n >= 60, f"solo {n} icone"
        return f"{n} icone"

    def brand():
        from .ui.brand import app_icon
        assert not app_icon().isNull()

    def qt_modules():
        from PySide6 import QtMultimedia, QtPdf, QtSvg  # noqa: F401
        from PySide6.QtPdf import QPdfDocument
        QPdfDocument()

    def ffmpeg():
        import subprocess

        from .ffmpeg_wrapper import _CREATIONFLAGS, ffmpeg_path, ffprobe_path
        out = []
        for exe in (ffmpeg_path(), ffprobe_path()):
            r = subprocess.run([exe, "-version"], capture_output=True, text=True, creationflags=_CREATIONFLAGS)
            assert r.returncode == 0, exe
            out.append(r.stdout.splitlines()[0][:40])
        return "; ".join(out)

    def notices():
        root = paths.app_root()
        found = [n for n in ("THIRD-PARTY-NOTICES.txt", "LICENSE") if (root / n).exists() or (Path.cwd() / n).exists()]
        assert len(found) == 2, f"mancano file legali: {found}"

    def windows():
        from .settings import Settings
        from .ui.main_window import MainWindow
        from .ui.state import AppState
        th.theme.reduce_motion = True
        st = AppState(Settings(Path(tempfile.mkdtemp())))
        th.theme.apply(QApplication.instance())
        w = MainWindow(st)
        w.show()
        for mode in ("simple", "advanced"):
            w.set_mode(mode, animate=False)
            QApplication.processEvents()
            img = w.grab()
            assert not img.isNull() and img.width() > 400, mode
        w.close()

    check("font Inter", fonts)
    check("icone Lucide", icons)
    check("logo e icona", brand)
    check("moduli Qt (SVG, PDF, multimedia)", qt_modules)
    check("ffmpeg e ffprobe", ffmpeg)
    check("licenze e crediti", notices)
    check("finestra in modalità Semplice e Avanzata", windows)
    text = "\n".join(lines) + f"\n\n{'TUTTO OK' if not failed else str(failed) + ' controlli falliti'}\n"
    try:
        (paths.data_dir() / "selftest.txt").write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text)
    return 1 if failed else 0
