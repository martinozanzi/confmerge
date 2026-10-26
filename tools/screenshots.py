"""Screenshot di ogni schermata + controllo geometrie (widget sovrapposti o tagliati).

Uso:  QT_SCALE_FACTOR=1.5 python tools/screenshots.py OUTDIR [--min] [--theme dark|light] [--font-scale 1.25]
Stampa un JSON con i problemi trovati (lista vuota = ok).
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QApplication, QLabel, QScrollBar, QSplitter,
                               QStackedWidget, QTabBar, QWidget)


def make_media(d: pathlib.Path) -> None:
    from scipy.io import wavfile
    from conftest import make_world
    SR = 16000
    if (d / "rec.wav").exists():
        return
    world = make_world(60, seed=8, fs=SR)
    world[:15 * SR] *= 0.02
    world[50 * SR:] *= 0.02
    for i in range(2):
        wavfile.write(str(d / f"c{i}.wav"), SR, (world[i * 30 * SR:(i + 1) * 30 * SR] * 32767).astype("<i2"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=30",
                        "-i", str(d / f"c{i}.wav"), "-t", "30", "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-metadata", f"creation_time=2026-05-01T10:00:{i * 30:02d}Z",
                        str(d / f"v{i}.mp4")], check=True)
        (d / f"c{i}.wav").unlink()
    wavfile.write(str(d / "rec.wav"), SR, (world[int(1.5 * SR):] * 32767).astype("<i2"))


def find_problems(root: QWidget, tag: str) -> list[dict]:
    out = []
    skip_parent = (QSplitter, QStackedWidget, QTabBar, QAbstractScrollArea, QScrollBar)
    for w in root.findChildren(QWidget):
        if not w.isVisible() or w.property("overlay"):
            continue
        name = f"{type(w).__name__}:{w.objectName() or (w.text()[:20] if hasattr(w, 'text') and callable(w.text) else '')}"
        # scorrimento orizzontale = contenuto più largo dello spazio disponibile (cose tagliate)
        if isinstance(w, QAbstractScrollArea) and w.horizontalScrollBar().isVisible() and w.horizontalScrollBar().maximum() > 0:
            inner = w.widget() if hasattr(w, "widget") else None
            out.append({"tag": tag, "kind": "scorrimento-orizzontale", "widget": name,
                        "eccesso": w.horizontalScrollBar().maximum(),
                        "contenuto": type(inner).__name__ if inner else "", "visibile": w.viewport().width(),
                        "minimo-contenuto": inner.minimumSizeHint().width() if inner else 0})
        # testo tagliato
        if isinstance(w, (QLabel, QAbstractButton)) and w.width() > 0:
            hint = w.minimumSizeHint()
            if isinstance(w, QLabel) and w.wordWrap():
                if w.heightForWidth(w.width()) > w.height() + 2:
                    out.append({"tag": tag, "kind": "tagliato", "widget": name, "size": [w.width(), w.height()],
                                "need_h": w.heightForWidth(w.width())})
            elif hint.width() > w.width() + 2 or hint.height() > w.height() + 2:
                out.append({"tag": tag, "kind": "tagliato", "widget": name, "size": [w.width(), w.height()],
                            "hint": [hint.width(), hint.height()]})
        # sovrapposizioni fra fratelli
        p = w.parentWidget()
        if p is None or isinstance(p, skip_parent) or p.layout() is None:
            continue
        for o in p.children():
            if o is w or not isinstance(o, QWidget) or not o.isVisible() or o.isWindow() or o.property("overlay"):
                continue
            if id(o) < id(w):
                continue
            inter = w.geometry().intersected(o.geometry())
            if inter.width() > 2 and inter.height() > 2:
                on = f"{type(o).__name__}:{o.objectName()}"
                out.append({"tag": tag, "kind": "sovrapposto", "widget": name, "con": on,
                            "area": [inter.width(), inter.height()]})
    return out


def pump(app, n=15, dt=0.03):
    for _ in range(n):
        app.processEvents()
        time.sleep(dt)


def main():
    args = sys.argv[1:]
    outdir = pathlib.Path(args[0])
    outdir.mkdir(parents=True, exist_ok=True)
    use_min = "--min" in args
    theme_name = args[args.index("--theme") + 1] if "--theme" in args else "dark"
    fscale = float(args[args.index("--font-scale") + 1]) if "--font-scale" in args else 1.0
    app = QApplication([])
    from confmerge.settings import Settings
    from confmerge.ui.main_window import MainWindow
    from confmerge.ui.state import AppState
    from confmerge.ui.theme import theme
    st = AppState(Settings(pathlib.Path(tempfile.mkdtemp())))
    theme.reduce_motion = True
    theme.font_scale = fscale
    theme.mode = theme_name
    theme.apply(app)
    media = pathlib.Path(tempfile.gettempdir()) / "confmerge-shots-media"
    media.mkdir(exist_ok=True)
    make_media(media)
    w = MainWindow(st)
    w.resize(*((1100, 700) if use_min else (1360, 860)))
    w.show()
    problems: list[dict] = []
    shots = []

    def snap(name):
        pump(app)
        w.grab().save(str(outdir / f"{name}.png"))
        problems.extend(find_problems(w, name))
        shots.append(name)

    snap("01-selezione-vuota")
    w.select.load_folder(media)
    snap("02-selezione")
    w.go_next()
    t = time.time()
    while w.stack.currentIndex() != 2 and time.time() - t < 120:
        pump(app, 1, 0.05)
    w.review.apply_suggestion()
    pump(app, 20)
    snap("03-revisione")
    from confmerge.ui.graphics_page import new_element
    from confmerge.render.model import LowerThird
    el = new_element("text")
    el.text, el.x, el.y = "Evento 2026", 0.8, 0.08
    st.spec.graphics.elements.append(el)
    st.spec.graphics.lower_thirds.append(LowerThird("Mario Rossi", "Relatore", start=0, duration=20))
    st.touch()
    w.go_next()
    pump(app, 10)
    for i in range(w.graphics.tabs.count()):
        w.graphics.tabs.setCurrentIndex(i)
        if i == 1:
            w.graphics.ov_main.list.setCurrentRow(0)
        snap(f"04-grafica-{i + 1}-{w.graphics.tabs.tabText(i).split(',')[0].replace(' ', '-').lower()}")
    w.go_next()
    t = time.time()
    while w.export.est is None and time.time() - t < 120:
        pump(app, 1, 0.05)
    snap("05-export")
    print(json.dumps({"shots": shots, "problems": problems}, ensure_ascii=False))
    w.close()
    os._exit(0)


if __name__ == "__main__":
    main()
