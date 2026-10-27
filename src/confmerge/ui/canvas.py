"""Tela di anteprima WYSIWYG: video + ritaglio/zoom + slide/PiP + grafica, con lo stesso codice dell'export."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .. import slides as sl
from ..render import compositor
from ..render.model import Element, Scene, lower_third_elements, substitute
from ..render.text_renderer import element_bbox, new_image
from ..spec import RenderSpec, output_size
from ..view import source_to_frame
from .theme import theme

PREVIEW_W = 960


class Canvas(QWidget):
    """mode: 'video' (frame del player + grafica principale) | 'scene' (sfondo scena) | 'crop' (ritaglio a mano)."""
    elementMoved = Signal(int, float, float)
    elementPicked = Signal(int)
    cropChanged = Signal(float, float, float, float)

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
        vs = self.state.spec.variables
        els = substitute([e for e in gr.elements if "main" in e.targets], vs)
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
            else:
                src, dst = source_to_frame(fw, fh, spec.image, W, H, self.out_t)
                p.drawImage(dst, self.frame, src)
                self._draw_slides(p, W, H)
        p.end()
        if self.mode == "crop":
            return img
        return compositor.render_frame(self._all_elements(), W, H, self.out_t, self._main_dur(), img)

    def _main_dur(self) -> float:
        pr = self.state.project
        return max(0.0, self.state.trim_end - self.state.trim_start) if pr else 1e9

    def _scene_elements(self) -> list[Element]:
        if not self.scene:
            return []
        vs = self.state.spec.variables
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
        self._drag_idx = -1
        self._guides = []
        self.update()
