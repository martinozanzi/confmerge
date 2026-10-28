"""Tela di anteprima WYSIWYG: video + ritaglio/zoom + slide/PiP + grafica, con lo stesso codice dell'export."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .. import slides as sl, subtitles
from ..brand import brand_elements
from . import placement
from ..render import anchors
from ..render import compositor
from ..render.model import Element, Scene, lower_third_elements, substitute
from ..render.text_renderer import element_bbox, new_image
from ..spec import RenderSpec, output_size, split_heights
from ..templates import preview_variables
from ..view import source_to_frame
from .theme import theme

PREVIEW_W = 960


class Canvas(QWidget):
    """mode: 'video' (frame del player + grafica principale) | 'scene' (sfondo scena) | 'crop' (ritaglio a mano)."""
    elementMoved = Signal(int, float, float)
    elementPicked = Signal(int)
    cropChanged = Signal(float, float, float, float)
    itemSelected = Signal(str, int)        # Studio Social: tipo («el», «logo», «sub») e indice dell'elemento scelto; ('', -1) = nessuno
    itemsChanged = Signal()                # un elemento è stato spostato (a fine trascinamento)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setMinimumSize(320, 180)
        self.setMouseTracking(True)
        self.frame: QImage | None = None
        self.mode = "video"
        self.scene: Scene | None = None
        self.scene_target = "main"
        self.elements_override: list[Element] | None = None
        self.fixed_size: tuple[int, int] | None = None   # es. miniatura 1280×720
        self.social_edit = False                         # Studio Social: testi, loghi e sottotitoli si trascinano con aggancio
        self.sel_item: tuple[str, int] | None = None
        self._item_drag: tuple[str, int, QPointF, float, float] | None = None
        self.safe_zones: list[dict] = []                 # Studio Social: [{name, color, safe=(sopra, sotto, sinistra, destra)}]
        self.safe_common = (0.0, 0.0, 0.0, 0.0)          # area sicura per tutte le piattaforme mostrate
        self.out_t = 0.0                 # tempo di uscita
        self.seg_dur = 1e9
        self.selected = -1
        self.show_guides = True
        self._slides: list[QImage] = []
        self._slides_key: tuple = ()
        self._layer_cache: dict = {}
        self._guides: list[tuple[str, float]] = []
        self._drag_idx = -1
        self._drag_off = QPointF()
        self._crop_drag: QPointF | None = None
        self._crop_rect: QRectF | None = None
        self._second_cache: dict = {}
        state.spec_changed.connect(self.update)           # testi, immagini, sottotitoli: l'anteprima segue subito ogni modifica
        state.profile_changed.connect(self.update)

    # --- dati
    def set_frame(self, img: QImage | None) -> None:
        self.frame = img
        self.update()

    def set_time(self, out_t: float) -> None:
        self.out_t = out_t
        self.update()

    def _slides_images(self) -> list[QImage]:
        s = self.state.spec.slides
        key = tuple(s.files)
        if key != self._slides_key:
            try:
                self._slides = sl.load_slides(list(s.files), 1280) if s.files else []
            except Exception:  # noqa: BLE001
                self._slides = []
            self._slides_key = key
            self._layer_cache.clear()
        return self._slides

    def _all_elements(self) -> list[Element]:
        if self.elements_override is not None:
            return self.elements_override
        gr = self.state.spec.graphics
        vs = preview_variables(self.state.spec.variables)          # esempi dove non hai ancora scritto
        W, H = self.frame_size()
        els = anchors.resolve(substitute([e for e in gr.elements if "main" in e.targets], vs), W, H, self.state.spec.brand.safe)
        els += brand_elements(self.state.spec, W, H)
        for i, lt in enumerate(gr.lower_thirds):
            els += lower_third_elements(lt, i, vs)
        return els

    def frame_size(self) -> tuple[int, int]:
        W, H = self.fixed_size or output_size(self.state.spec.image, self.state.spec.export)
        s = PREVIEW_W / W
        return PREVIEW_W, max(2, round(H * s))

    STAGE_PAD = 14

    def _target_rect(self) -> QRectF:
        W, H = self.frame_size()
        pad = self.STAGE_PAD
        aw, ah = max(1, self.width() - 2 * pad), max(1, self.height() - 2 * pad)
        s = min(aw / W, ah / H)
        return QRectF((self.width() - W * s) / 2, (self.height() - H * s) / 2, W * s, H * s)

    # --- composizione
    def compose(self) -> QImage:
        W, H = self.frame_size()
        spec: RenderSpec = self.state.spec
        img = new_image(W, H)
        p = QPainter(img)
        p.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        if self.mode == "scene" and self.scene is not None:
            p.end()
            base = compositor.render_scene_background(self.scene, W, H)
            if self.scene.background.kind == "transparent" and self.frame is not None:
                base = new_image(W, H)
                q = QPainter(base)
                q.drawImage(QRectF(0, 0, W, H), self.frame)
                q.end()
            return compositor.render_frame(self._scene_elements(), W, H, self.out_t, self.seg_dur, base)
        p.fillRect(0, 0, W, H, Qt.black)
        if self.frame is not None and not self.frame.isNull():
            fw, fh = self.frame.width(), self.frame.height()
            if self.mode == "crop":
                s = min(W / fw, H / fh)
                p.drawImage(QRectF((W - fw * s) / 2, (H - fh * s) / 2, fw * s, fh * s), self.frame)
            elif self._is_social() and spec.split.enabled and spec.split.path:
                self._draw_split(p, W, H, spec, fw, fh)
            else:
                social = self._is_social()
                if social and spec.image.reframe == "blur" and abs(fw / fh - W / H) > 0.01:
                    self._draw_blur_bg(p, W, H)
                src, dst = source_to_frame(fw, fh, spec.image, W, H, self.out_t, social)
                p.drawImage(dst, self.frame, src)
                self._draw_slides(p, W, H)
        p.end()
        if self.mode == "crop":
            return img
        out = compositor.render_frame(self._all_elements(), W, H, self.out_t, self._main_dur(), img)
        return self._draw_subtitle(out, W, H)

    def _second_frame(self, path: str, start: float) -> QImage | None:
        """Primo fotogramma del secondo video (da `start`): nell'anteprima il secondo video resta fermo. Si calcola una volta."""
        key = (path, round(start, 2))
        if key not in self._second_cache:
            img = None
            try:
                import subprocess
                import tempfile
                from .. import ffmpeg_wrapper as fw
                with tempfile.TemporaryDirectory() as td:
                    png = Path(td) / "f.png"
                    subprocess.run([fw.ffmpeg_path(), "-v", "error", "-nostdin", "-y", "-ss", f"{max(0.0, start):.3f}", "-i", path,
                                    "-frames:v", "1", "-vf", "scale=480:-2", str(png)], capture_output=True, timeout=20,
                                   creationflags=fw._CREATIONFLAGS)
                    q = QImage(str(png))
                    img = q if not q.isNull() else None
            except Exception:  # noqa: BLE001 - senza fotogramma si disegna un segnaposto
                img = None
            self._second_cache[key] = img
        return self._second_cache[key]

    def _draw_split(self, p: QPainter, W: int, H: int, spec: RenderSpec, fw: int, fh: int) -> None:
        """Due riquadri uno sopra l'altro: il tuo video (con la sua inquadratura) e il secondo video."""
        sp = spec.split
        top, gap, bot = split_heights(sp, H)
        y_main, h_main = (0, top) if sp.main_on_top else (top + gap, bot)
        y_2, h_2 = (top + gap, bot) if sp.main_on_top else (0, top)
        p.save()
        p.setClipRect(QRectF(0, y_main, W, h_main))
        p.translate(0, y_main)
        if spec.image.reframe == "blur" and abs(fw / fh - W / h_main) > 0.01:
            self._draw_blur_bg(p, W, h_main)
        src, dst = source_to_frame(fw, fh, spec.image, W, h_main, self.out_t, True)
        p.drawImage(dst, self.frame, src)
        p.restore()
        p.save()
        p.setClipRect(QRectF(0, y_2, W, h_2))
        sec = self._second_frame(sp.path, sp.second_start)
        if sec is None:
            p.fillRect(QRectF(0, y_2, W, h_2), QColor("#3a3f4b"))
            p.setPen(QColor("#d0d4dc"))
            p.drawText(QRectF(0, y_2, W, h_2), Qt.AlignCenter, "Secondo video")
        else:
            s = max(W / sec.width(), h_2 / sec.height())
            w, h = sec.width() * s, sec.height() * s
            p.drawImage(QRectF(-(w - W) * min(1.0, max(0.0, sp.second_x)), y_2 - (h - h_2) / 2, w, h), sec)
        p.restore()

    def _draw_subtitle(self, img: QImage, W: int, H: int) -> QImage:
        st = self.state.spec.subtitles
        if not st.enabled:
            return img
        sampling = time.monotonic() < self.state.subtitle_sample_until
        t_in, hl = 1.0, -1                                   # secondi dall'inizio del sottotitolo; parola evidenziata
        if sampling or not st.lines:                         # frase di esempio: si vede lo stile anche prima di creare i sottotitoli
            text = subtitles.SAMPLE_TEXT
            if st.chunk_words:
                text = " ".join(text.split()[:st.chunk_words])
            hl = min(1, len(text.split()) - 1)
        else:
            t_proj = self.state.from_out(self.out_t)
            ln = subtitles.active_line(st, t_proj)
            if ln is None:
                return img
            text, t_in, hl = ln.text, t_proj - ln.start, subtitles.word_index(ln, t_proj)
        return compositor.render_frame([subtitles.preview_element(st, text, W, H, self.state.spec.brand.safe, hl)], W, H, t_in, 1e9, img)

    def _is_social(self) -> bool:
        pr = self.state.project
        return bool(pr and pr.kind == "social")

    def _draw_blur_bg(self, p: QPainter, W: int, H: int) -> None:
        """Sfondo sfocato per il video «intero» in un formato diverso: la stessa immagine ingrandita e sfumata."""
        sw, sh = max(8, W // 10), max(8, H // 10)
        small = self.frame.scaled(sw, sh, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        small = small.copy(max(0, (small.width() - sw) // 2), max(0, (small.height() - sh) // 2), sw, sh)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, W, H), small)
        p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, 40))

    def _draw_safe_zone(self, p: QPainter, tr: QRectF) -> None:
        """Le parti dell'immagine coperte dall'interfaccia di ogni piattaforma, ciascuna di un colore, e l'area sicura per tutte
        (solo anteprima: non finiscono nel file)."""
        for z in self.safe_zones:
            top, bottom, left, right = z["safe"]
            col = QColor(z["color"])
            fill, hatch, edge = QColor(col), QColor(col), QColor(col)
            fill.setAlpha(42)
            hatch.setAlpha(95)
            edge.setAlpha(230)
            rects = [QRectF(tr.x(), tr.y(), tr.width(), tr.height() * top),
                     QRectF(tr.x(), tr.bottom() - tr.height() * bottom, tr.width(), tr.height() * bottom),
                     QRectF(tr.x(), tr.y() + tr.height() * top, tr.width() * left, tr.height() * (1 - top - bottom)),
                     QRectF(tr.right() - tr.width() * right, tr.y() + tr.height() * top, tr.width() * right,
                            tr.height() * (1 - top - bottom))]
            p.setPen(Qt.NoPen)
            for r in rects:
                if r.width() > 1 and r.height() > 1:
                    p.setBrush(fill)
                    p.drawRect(r)
                    p.setBrush(QBrush(hatch, Qt.BDiagPattern))
                    p.drawRect(r)
            inner = QRectF(tr.x() + tr.width() * left, tr.y() + tr.height() * top,
                           tr.width() * (1 - left - right), tr.height() * (1 - top - bottom))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(edge, 2, Qt.DashLine))
            p.drawRect(inner)
        if self.safe_zones and any(self.safe_common):
            top, bottom, left, right = self.safe_common
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#22C55E"), 2))
            p.drawRect(QRectF(tr.x() + tr.width() * left, tr.y() + tr.height() * top,
                              tr.width() * (1 - left - right), tr.height() * (1 - top - bottom)))

    def _main_dur(self) -> float:
        pr = self.state.project
        return max(0.0, self.state.trim_end - self.state.trim_start) if pr else 1e9

    def _scene_elements(self) -> list[Element]:
        if not self.scene:
            return []
        vs = preview_variables(self.state.spec.variables)
        extra = [e for e in self.state.spec.graphics.elements if self.scene_target in e.targets]
        return substitute(list(self.scene.elements), vs) + substitute(extra, vs)

    def _draw_slides(self, p: QPainter, W: int, H: int) -> None:
        spec = self.state.spec
        sls = spec.slides
        if not sls.enabled:
            return
        imgs = self._slides_images()
        ivs = sl.intervals(sls, self._main_dur(), len(imgs) if imgs else 1)
        iv = next((i for i in ivs if i.a <= self.out_t < i.b), None)
        if iv is None or iv.layout == "speaker" or not imgs:
            return
        slide = imgs[iv.slide]
        pip = sls.pip
        frame = self.frame
        key = (iv.layout, iv.slide, W, H, repr(pip))
        layer = self._layer_cache.get(key)
        if layer is None:
            if iv.layout == "slide_full":
                layer = sl.full_slide_png(slide, W, H)
            elif iv.layout == "speaker_full":
                layer = sl.small_slide_png(slide, pip, W, H)
            else:
                layer = sl.side_by_side_png(slide, pip, W, H)
            self._layer_cache[key] = layer
        p.drawImage(0, 0, layer)
        if iv.layout in ("slide_full", "side_by_side"):
            rect = sl.pip_rect(pip, W, H) if iv.layout == "slide_full" else sl.side_rects(pip, W, H)[0]
            p.drawImage(0, 0, sl.decor_png(rect, pip, W, H))
            path = QPainterPath()
            path.addRoundedRect(rect, pip.radius * H, pip.radius * H)
            p.save()
            p.setClipPath(path)
            p.drawImage(rect, frame)
            p.restore()

    # --- disegno
    _tile: tuple | None = None          # (nome del tema, QPixmap) della trama a scacchi

    @classmethod
    def _stage_tile(cls) -> QPixmap:
        t = theme.t
        if cls._tile is None or cls._tile[0] != t.name:
            px = QPixmap(32, 32)
            px.fill(QColor(t.stage))
            q = QPainter(px)
            q.setPen(Qt.NoPen)
            q.setBrush(QColor(t.stage2))
            q.drawRect(0, 0, 16, 16)
            q.drawRect(16, 16, 16, 16)
            q.end()
            cls._tile = (t.name, px)
        return cls._tile[1]

    def _draw_stage(self, p: QPainter, tr: QRectF) -> None:
        """«Palco» a scacchi più chiaro del video, con ombra e bordo: si capisce sempre dove finisce l'immagine."""
        p.fillRect(self.rect(), QBrush(self._stage_tile()))
        for i, a in ((6, 18), (3, 30), (1, 45)):
            c = QColor(0, 0, 0, a)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(tr.adjusted(-i, -i + 2, i, i + 2), 3, 3)
        edge = QColor(theme.t.text)
        edge.setAlphaF(0.55)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(edge, 1))
        p.drawRect(tr.adjusted(-0.5, -0.5, 0.5, 0.5))

    def paintEvent(self, _):
        p = QPainter(self)
        img = self.compose()
        tr = self._target_rect()
        self._draw_stage(p, tr)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(tr, img)
        if self.mode == "video" and self.safe_zones:
            self._draw_safe_zone(p, tr)
        if self.mode == "crop" and self._crop_rect is not None:
            r = self._crop_rect
            p.setPen(QPen(QColor("#3ddc84"), 2))
            p.setBrush(QColor(61, 220, 132, 40))
            p.drawRect(r)
        els = self._edit_elements()
        if self.selected >= 0 and self.selected < len(els) and self.mode != "crop":
            W, H = self.frame_size()
            b = element_bbox(els[self.selected], W, H)
            s = tr.width() / W
            p.setPen(QPen(QColor("#4aa3ff"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(tr.x() + b.x() * s, tr.y() + b.y() * s, b.width() * s, b.height() * s))
        if self.social_edit and self.sel_item and self.mode == "video":
            W, H = self.frame_size()
            for kind, i, r in placement.items(self.state, W, H):
                if (kind, i) == self.sel_item:
                    sc = tr.width() / W
                    p.setPen(QPen(QColor("#4aa3ff"), 2, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(QRectF(tr.x() + r.x() * sc, tr.y() + r.y() * sc, r.width() * sc, r.height() * sc))
        if self._guides and self.show_guides:
            p.setPen(QPen(QColor("#ff4fa3"), 1))
            for axis, v in self._guides:
                if axis == "x":
                    p.drawLine(QPointF(tr.x() + v * tr.width(), tr.y()), QPointF(tr.x() + v * tr.width(), tr.bottom()))
                else:
                    p.drawLine(QPointF(tr.x(), tr.y() + v * tr.height()), QPointF(tr.right(), tr.y() + v * tr.height()))

    # --- interazione
    def _edit_elements(self) -> list[Element]:
        if self.mode == "scene" and self.scene is not None:
            return self.scene.elements
        if self.elements_override is not None:
            return self.elements_override
        return self.state.spec.graphics.elements

    def _snap_safe(self):
        """Area sicura per l'aggancio: quella comune alle piattaforme mostrate, altrimenti quella dell'anteprima."""
        return self.safe_common if any(self.safe_common) else self.state.spec.brand.safe

    def _to_frame(self, pt: QPointF) -> QPointF:
        tr = self._target_rect()
        return QPointF((pt.x() - tr.x()) / tr.width(), (pt.y() - tr.y()) / tr.height())

    def mousePressEvent(self, e):
        pos = e.position()
        if self.mode == "crop":
            self._crop_drag = pos
            self._crop_rect = QRectF(pos, pos)
            return
        W, H = self.frame_size()
        f = self._to_frame(pos)
        if self.social_edit and self.mode == "video":
            found = placement.hit(placement.items(self.state, W, H), f.x() * W, f.y() * H)
            if found:
                kind, i, r = found
                self.sel_item = (kind, i)
                self._item_drag = (kind, i, QPointF(r.center().x() / W - f.x(), r.center().y() / H - f.y()),
                                   r.width() / W, r.height() / H)
                self.itemSelected.emit(kind, i)
            else:
                self.sel_item = None
                self.itemSelected.emit("", -1)
            self.update()
            return
        els = self._edit_elements()
        for i in range(len(els) - 1, -1, -1):
            if not els[i].visible or els[i].locked:
                continue
            b = element_bbox(els[i], W, H)
            if b.contains(f.x() * W, f.y() * H):
                self._drag_idx = i
                self._drag_off = QPointF(els[i].x - f.x(), els[i].y - f.y())
                self.selected = i
                self.elementPicked.emit(i)
                self.update()
                return
        self.selected = -1
        self.elementPicked.emit(-1)
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.mode == "crop" and self._crop_drag is not None:
            self._crop_rect = QRectF(self._crop_drag, pos).normalized()
            self.update()
            return
        if self._item_drag is not None:
            kind, i, off, w, h = self._item_drag
            W, H = self.frame_size()
            f = self._to_frame(pos)
            cx, cy = f.x() + off.x(), f.y() + off.y()
            self._guides = []
            if not (e.modifiers() & Qt.AltModifier):
                cx, cy, self._guides = placement.snap(cx, cy, w / 2, h / 2, W, H, self._snap_safe())
            placement.place(self.state, kind, i, min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0), w, h, W, H)
            self.update()
            return
        if self._drag_idx >= 0:
            f = self._to_frame(pos)
            el = self._edit_elements()[self._drag_idx]
            x, y = f.x() + self._drag_off.x(), f.y() + self._drag_off.y()
            self._guides = []
            thr = 0.012
            for v in (0.5, 0.05, 0.95, 1 / 3, 2 / 3):
                if abs(x - v) < thr:
                    x = v
                    self._guides.append(("x", v))
                if abs(y - v) < thr:
                    y = v
                    self._guides.append(("y", v))
            el.x, el.y = min(max(x, -0.2), 1.2), min(max(y, -0.2), 1.2)
            self.elementMoved.emit(self._drag_idx, el.x, el.y)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.mode == "crop" and self._crop_rect is not None:
            tr = self._target_rect()
            r = self._crop_rect.intersected(tr)
            if r.width() > 8 and r.height() > 8 and self.frame is not None:
                W, H = self.frame_size()
                fw, fh = self.frame.width(), self.frame.height()
                s = min(W / fw, H / fh)
                iw, ih = fw * s / W * tr.width(), fh * s / H * tr.height()
                ix, iy = tr.x() + (tr.width() - iw) / 2, tr.y() + (tr.height() - ih) / 2
                l = min(max((r.left() - ix) / iw, 0), 1)
                t = min(max((r.top() - iy) / ih, 0), 1)
                rr = min(max(1 - (r.right() - ix) / iw, 0), 1)
                b = min(max(1 - (r.bottom() - iy) / ih, 0), 1)
                self.cropChanged.emit(l, t, rr, b)
            self._crop_rect = None
            self._crop_drag = None
            self.update()
        moved = self._item_drag is not None
        self._item_drag = None
        self._drag_idx = -1
        self._guides = []
        self.update()
        if moved:
            self.itemsChanged.emit()
