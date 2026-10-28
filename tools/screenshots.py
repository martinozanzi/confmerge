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
os.environ.setdefault("CONFMERGE_NO_CONFIRM", "1")
os.environ.setdefault("CONFMERGE_NO_RECOVERY", "1")
os.environ.setdefault("CONFMERGE_NO_UPDATE_CHECK", "1")
os.environ.setdefault("CONFMERGE_NO_PLAYER", "1")
os.environ.setdefault("CONFMERGE_APP", "merge")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QApplication, QLabel, QListWidget, QScrollBar, QSplitter,
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
    vertical = tag[:1] in ("s", "o", "h")         # Semplice, Social, scelta iniziale; l'Avanzata ha molte opzioni e può scorrere
    skip_parent = (QSplitter, QStackedWidget, QTabBar, QAbstractScrollArea, QScrollBar)
    for w in root.findChildren(QWidget):
        if not w.isVisible() or w.property("overlay"):
            continue
        name = f"{type(w).__name__}:{w.objectName() or (w.text()[:20] if hasattr(w, 'text') and callable(w.text) else '')}"
        # scorrimento orizzontale = contenuto più largo dello spazio disponibile (cose tagliate)
        if isinstance(w, QListWidget) and w.flow() == QListWidget.LeftToRight and not w.isWrapping():
            pass          # striscia di miniature: scorre di proposito
        elif isinstance(w, QAbstractScrollArea) and w.horizontalScrollBar().isVisible() and w.horizontalScrollBar().maximum() > 0:
            inner = w.widget() if hasattr(w, "widget") else None
            out.append({"tag": tag, "kind": "scorrimento-orizzontale", "widget": name,
                        "eccesso": w.horizontalScrollBar().maximum(),
                        "contenuto": type(inner).__name__ if inner else "", "visibile": w.viewport().width(),
                        "minimo-contenuto": inner.minimumSizeHint().width() if inner else 0})
        # scorrimento verticale: nelle schermate guidate (Semplice, Social) niente deve scorrere su un portatile 1366×768
        if (vertical and type(w).__name__ in ("QScrollArea", "_Scroll") and w.verticalScrollBar().isVisible()
                and w.verticalScrollBar().maximum() > 4):
            out.append({"tag": tag, "kind": "scorrimento-verticale", "widget": name, "eccesso": w.verticalScrollBar().maximum(),
                        "visibile": w.viewport().height()})
        # testo tagliato
        if isinstance(w, QLabel) and w.hasScaledContents():
            continue      # immagine che si adatta al riquadro: non si taglia
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
    import faulthandler
    faulthandler.dump_traceback_later(240, exit=True)       # se qualcosa si blocca, si esce con la traccia invece di restare fermi
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
    sst = AppState(st.settings, kind="social")
    w = MainWindow(st, sst)
    w.resize(*((1100, 700) if use_min else (1280, 700)))                 # portatile 1366×768: finestra utile ≈ 1280×700
    w.show()
    problems: list[dict] = []
    shots: list[str] = []

    def snap(name):
        pump(app)
        w.grab().save(str(outdir / f"{name}.png"))
        problems.extend(find_problems(w, name))
        shots.append(name)

    def wait(cond, secs=120):
        t = time.time()
        while not cond() and time.time() - t < secs:
            pump(app, 1, 0.05)

    # ---------------- modalità SEMPLICE
    w.set_mode("simple", animate=False)
    snap("s01-cartella")
    w.simple.start.use_folder(media)
    pump(app, 4)
    snap("s02-analisi")
    wait(lambda: st.project is not None)
    pump(app, 20)
    snap("s03-controlla")
    st.review.apply_suggestion()
    st.spec.variables.update({"titolo": "Convegno sul futuro della città", "relatore": "Mario Rossi", "ruolo": "Sindaco"})
    st.touch()
    pump(app, 10)
    snap("s04-controlla-confermato")
    w.simple.show_step(2, animate=False)
    wait(lambda: st.export.est is not None)
    snap("s05-esporta")
    w.simple.export.stack.setCurrentIndex(1)
    w.simple.export.ring.setValue(0.42)
    snap("s06-in-corso")
    w.simple.export.done_title.setText("Il video è pronto!")
    w.simple.export.done_info.setText("/home/utente/Video/conferenza.mp4\nCi sono voluti 9:12 e il file pesa 2412 MB.")
    w.simple.export.stack.setCurrentIndex(2)
    snap("s07-pronto")
    w.simple.export.stack.setCurrentIndex(0)

    # ---------------- modalità AVANZATA
    w.set_mode("advanced", animate=False)
    from confmerge.ui.graphics_page import new_element
    el = new_element("text")
    el.text, el.x, el.y = "Evento 2026", 0.8, 0.08
    st.spec.graphics.elements.append(el)
    st.spec.graphics.elements.append(new_element("bar"))
    st.touch()
    adv = w.adv
    adv.goto(0, animate=False)
    snap("a0-sorgenti")
    adv.goto(1, animate=False)
    pump(app, 20)
    snap("a1-sincronia")
    adv.goto(2, animate=False)
    snap("a2-immagine")
    adv.goto(3, animate=False)
    for i in range(adv.titles.tabs.count()):
        adv.titles.tabs.setCurrentIndex(i)
        snap(f"a3-titoli-{i + 1}-{adv.titles.tabs.tabText(i).replace(' ', '-').lower()}")
    adv.goto(4, animate=False)
    adv.graphics.ov_main.list.setCurrentRow(0)
    snap("a4-decorazioni")
    adv.goto(5, animate=False)
    snap("a5-slide")
    adv.goto(6, animate=False)
    snap("a6-audio")
    adv.goto(7, animate=False)
    wait(lambda: st.export.est is not None)
    snap("a7-export")

    # ---------------- STUDIO SOCIAL
    w.set_app("home", animate=False)
    snap("h0-scelta")
    w.set_app("social", animate=False)
    snap("o0-video")
    w.social.start.start([media / "v0.mp4", media / "v1.mp4"])
    wait(lambda: sst.project is not None and w.social.step == 1)
    pump(app, 30)
    snap("o1-taglia")
    sst.social.remove_silences()
    sst.social.remove(2.0, 4.0)
    w.social.cut.wave.sel = (6.0, 9.0)
    w.social.cut._sel_changed((6.0, 9.0))
    pump(app, 10)
    snap("o1-taglia-tagliato")
    sst.spec.social.platforms = ["shorts", "reels", "youtube"]
    sst.spec.subtitles.enabled = True
    from confmerge.ui.social_style import new_text
    sst.spec.graphics.elements.append(new_text(sst, "tc"))
    sst.spec.graphics.elements[-1].text = "Assemblea cittadina"
    sst.spec.split.path = str(media / "v1.mp4")
    sst.touch()
    for step, name in ((2, "o2-formato"), (3, "o2-due-video"), (4, "o2-grafica"), (5, "o2-sottotitoli"), (6, "o2-audio")):
        w.social.show_step(step, animate=False)
        w.social.look.sync()
        if step == 2:
            w.social.look.safe.setChecked(True)
        if step == 3:
            sst.spec.split.enabled = True               # il pannello si vede anche con il secondo video acceso (è il più alto)
            sst.touch()
            sst.profile_changed.emit()
        pump(app, 25)
        snap(name)
    sst.spec.split.enabled = False
    w.social.show_step(7, animate=False)
    pump(app, 10)
    snap("o3-esporta")

    # ---------------- MARCHIO E MINIATURE
    from PySide6.QtGui import QColor, QImage, QPainter
    from confmerge import brand
    from confmerge.ui.brand_dialog import BrandDialog
    from confmerge.ui.thumbnail_dialog import ThumbnailDialog
    k = sst.kits.new("Associazione Prova")
    k.slogan, k.social = "Insieme per la città", "@associazioneprova"
    sst.kits.save(k)
    for name, col, w_, h_ in (("Logo", "#FFFFFF", 400, 160), ("Simbolo", "#EF4444", 300, 300)):
        im = QImage(w_, h_, QImage.Format_ARGB32)
        im.fill(QColor(0, 0, 0, 0))
        q = QPainter(im)
        q.setBrush(QColor(col))
        q.setPen(QColor(0, 0, 0, 0))
        q.drawEllipse(8, 8, w_ - 16, h_ - 16)
        q.end()
        f = media / f"{name}.png"
        im.save(str(f))
        sst.kits.add_logo(k, f, name, "main" if name == "Logo" else "symbol")
    brand.apply_kit(sst.spec, sst.kits.get(k.id), sst.kits)
    sst.touch()
    w.social.show_step(4, animate=False)
    w.social.look.sync()
    pump(app, 20)
    snap("o2-grafica-marchio")

    def snap_dialog(dlg, name):
        dlg.show()
        pump(app, 40)
        dlg.grab().save(str(outdir / f"{name}.png"))
        problems.extend(find_problems(dlg, name))
        shots.append(name)
        dlg.close()

    snap_dialog(BrandDialog(sst, w), "b0-marchio")
    snap_dialog(ThumbnailDialog(sst, outdir, "x", lambda: 2.0, w), "m0-miniatura")
    print(json.dumps({"shots": shots, "problems": problems}, ensure_ascii=False), flush=True)
    os._exit(0)          # senza chiudere la finestra: la chiusura dei lettori multimediali può bloccarsi in modo casuale


if __name__ == "__main__":
    main()
