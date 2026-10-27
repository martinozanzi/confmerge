"""Design system: token centralizzati, QSS generato dai token, font Inter e icone Lucide da file di risorse.

Nessun colore o dimensione deve comparire altrove nel codice dell'interfaccia: si usano i token di `theme.t`
e le costanti di questo modulo.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

RESOURCES = Path(__file__).resolve().parent.parent / "resources"

# ---- griglia e dimensioni (px logici: Qt scala da solo a 100-200%)
SPACE = 8
S1, S2, S3, S4, S5, S6 = (SPACE * k for k in (1, 2, 3, 4, 5, 6))
RADIUS_CARD = 12
RADIUS_CTRL = 8
CONTROL_H = 32
ICON = 18
FONT_TITLE, FONT_H2, FONT_BODY, FONT_CAPTION = 24, 18, 13, 12
ANIM_FAST, ANIM_BASE, ANIM_SLOW = 150, 200, 250


@dataclass(frozen=True)
class Tokens:
    name: str
    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    text2: str
    accent: str
    accent2: str
    on_accent: str
    btn1: str            # sfumatura dei pulsanti principali (contrasto alto con il testo bianco)
    btn2: str
    stage: str           # «palco» dietro al video nell'anteprima
    stage2: str
    success: str
    warning: str
    error: str
    hover: str            # velo per hover su superfici
    shadow: str           # rgba
    scroll: str


DARK = Tokens("dark", bg="#0E1014", surface="#15181E", surface2="#1D2129", border="#2A2F39", text="#ECEEF3",
              text2="#9CA3B0", accent="#4C8DF6", accent2="#2DD4BF", on_accent="#FFFFFF", btn1="#2563EB", btn2="#1D7FE8",
              stage="#323844", stage2="#2B303B", success="#3DD598", warning="#FFB020", error="#FF5C6C",
              hover="rgba(255,255,255,0.06)", shadow="rgba(0,0,0,0.35)", scroll="#353B47")
LIGHT = Tokens("light", bg="#F4F5F8", surface="#FFFFFF", surface2="#ECEEF3", border="#DADEE6", text="#12151C",
               text2="#586072", accent="#2563EB", accent2="#0EA5A4", on_accent="#FFFFFF", btn1="#2563EB", btn2="#1D7FE8",
               stage="#CDD2DC", stage2="#C4CAD5", success="#14A36B", warning="#B26A00", error="#DC3545",
               hover="rgba(18,21,28,0.06)", shadow="rgba(20,30,60,0.12)", scroll="#C3C9D5")


def with_alpha(color: str, a: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a:.2f})"


class Prefs:
    """Preferenze di interfaccia persistenti (tema, modalità, animazioni, sezioni aperte…)."""

    def __init__(self):
        self.data: dict = {}
        self.save: Callable[[], None] = lambda: None

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        if self.data.get(key) != value:
            self.data[key] = value
            self.save()


class Theme(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode = "dark"            # dark | light | system
        self.t: Tokens = DARK
        self.reduce_motion = False
        self.font_scale = 1.0
        self.prefs = Prefs()
        self._fonts_loaded = False
        self._cache = Path(tempfile.gettempdir()) / "ConfMerge-theme-cache"

    # --- font
    def load_fonts(self) -> None:
        if self._fonts_loaded:
            return
        for f in sorted((RESOURCES / "fonts").glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(f))
        self._fonts_loaded = True

    def px(self, base: int) -> int:
        return max(8, round(base * self.font_scale))

    # --- tema
    def resolve(self) -> Tokens:
        if self.mode == "system":
            app = QApplication.instance()
            try:
                dark = app.styleHints().colorScheme() != Qt.ColorScheme.Light
            except Exception:  # noqa: BLE001
                dark = True
            return DARK if dark else LIGHT
        return LIGHT if self.mode == "light" else DARK

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in ("dark", "light", "system") else "dark"
        self.prefs.set("theme", self.mode)
        self.apply()

    def set_reduce_motion(self, on: bool) -> None:
        self.reduce_motion = on
        self.prefs.set("reduce_motion", on)

    def apply(self, app: QApplication | None = None) -> None:
        app = app or QApplication.instance()
        self.t = self.resolve()
        self.load_fonts()
        icon_cache.clear()
        app.setStyle("Fusion")
        f = QFont("Inter")
        f.setPixelSize(self.px(FONT_BODY))
        app.setFont(f)
        app.setPalette(self._palette())
        app.setStyleSheet(build_qss(self))
        for w in app.topLevelWidgets():
            set_titlebar(w, self.t.name == "dark")
        self.changed.emit()

    def _palette(self) -> QPalette:
        t, p = self.t, QPalette()
        c = QColor
        for role, col in ((QPalette.Window, t.bg), (QPalette.WindowText, t.text), (QPalette.Base, t.surface),
                          (QPalette.AlternateBase, t.surface2), (QPalette.Text, t.text), (QPalette.Button, t.surface2),
                          (QPalette.ButtonText, t.text), (QPalette.ToolTipBase, t.surface2), (QPalette.ToolTipText, t.text),
                          (QPalette.Highlight, t.accent), (QPalette.HighlightedText, t.on_accent),
                          (QPalette.PlaceholderText, t.text2), (QPalette.Link, t.accent)):
            p.setColor(role, c(col))
        return p

    # --- icone
    def icon(self, name: str, color: str | None = None, size: int = ICON) -> QIcon:
        return icon(name, color or self.t.text2, size)

    def cached_icon_path(self, name: str, color: str) -> str:
        """File SVG ricolorato su disco (serve agli `image: url()` del QSS)."""
        self._cache.mkdir(parents=True, exist_ok=True)
        p = self._cache / f"{name}-{color.lstrip('#')}.svg"
        if not p.exists():
            p.write_text(_svg_text(name, color), encoding="utf-8")
        return p.as_posix()


theme = Theme()


# ---------------------------------------------------------------------------------------------------------------- icone
@lru_cache(maxsize=256)
def _svg_text(name: str, color: str) -> str:
    f = RESOURCES / "icons" / f"{name}.svg"
    if not f.exists():
        raise FileNotFoundError(f"Icona mancante: {name}")
    return f.read_text(encoding="utf-8").replace("currentColor", color)


class _IconCache(dict):
    pass


icon_cache = _IconCache()


def icon(name: str, color: str, size: int = ICON) -> QIcon:
    key = (name, color, size)
    if key in icon_cache:
        return icon_cache[key]
    r = QSvgRenderer(_svg_text(name, color).encode("utf-8"))
    big = size * 4                       # alta risoluzione: nitida a 100-200% senza sfocature
    img = QImage(big, big, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    r.render(p, QRectF(0, 0, big, big))
    p.end()
    ic = QIcon(QPixmap.fromImage(img))
    icon_cache[key] = ic
    return ic


def pixmap(name: str, color: str, size: int, dpr: float = 2.0) -> QPixmap:
    r = QSvgRenderer(_svg_text(name, color).encode("utf-8"))
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.transparent)
    p = QPainter(px)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return px


def shadow(widget: QWidget, blur: int = 24, dy: int = 4) -> QGraphicsDropShadowEffect:
    e = QGraphicsDropShadowEffect(widget)
    e.setBlurRadius(blur)
    e.setOffset(0, dy)
    c = QColor(0, 0, 0, 90 if theme.t.name == "dark" else 28)
    e.setColor(c)
    widget.setGraphicsEffect(e)
    return e


def set_titlebar(win: QWidget, dark: bool) -> None:
    """Barra del titolo scura/chiara su Windows 10 (20H1+) e 11 con DwmSetWindowAttribute; altrove non fa nulla."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = int(win.winId())
        val = ctypes.c_int(1 if dark else 0)
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        for attr in (20, 19):            # DWMWA_USE_IMMERSIVE_DARK_MODE (nuovo / vecchio valore)
            if dwm(wintypes.HWND(hwnd), attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:  # noqa: BLE001  - fallback silenzioso
        pass


# ---------------------------------------------------------------------------------------------------------------- QSS
def build_qss(th: Theme) -> str:
    t = th.t
    px = th.px
    r_c, r_k = RADIUS_CARD, RADIUS_CTRL
    chk = th.cached_icon_path("check", t.on_accent)
    down = th.cached_icon_path("chevron-down", t.text2)
    up = th.cached_icon_path("chevron-up", t.text2)
    grad = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t.accent},stop:1 {t.accent2})"          # barre di avanzamento, slider
    btn = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t.btn1},stop:1 {t.btn2})"               # pulsanti principali
    grad_h = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {QColor(t.btn1).lighter(112).name()},stop:1 {QColor(t.btn2).lighter(112).name()})"
    return f"""
* {{ font-family: "Inter", "Segoe UI", sans-serif; }}
QWidget {{ color: {t.text}; font-size: {px(FONT_BODY)}px; }}
QMainWindow, QDialog, QStackedWidget, #Root {{ background: {t.bg}; }}
QWidget:disabled {{ color: {with_alpha(t.text2, 0.55)}; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: {px(FONT_TITLE)}px; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: {px(FONT_H2)}px; font-weight: 600; }}
QLabel[role="caption"] {{ font-size: {px(FONT_CAPTION)}px; color: {t.text2}; }}
QLabel[role="muted"] {{ color: {t.text2}; }}
QLabel[role="ok"] {{ color: {t.success}; }}
QLabel[role="warn"] {{ color: {t.warning}; }}
QLabel[role="err"] {{ color: {t.error}; }}
QToolTip {{ background: {t.surface2}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px; padding: 6px 8px; }}

QFrame#Card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {r_c}px; }}
QFrame#Card[flat="true"] {{ background: {t.surface2}; border: none; }}
QFrame#Panel {{ background: {t.surface}; border-left: 1px solid {t.border}; }}
QFrame#Sidebar {{ background: {t.surface}; border-right: 1px solid {t.border}; }}
QFrame#Header {{ background: {t.bg}; border-bottom: 1px solid {t.border}; }}

QPushButton {{ background: {t.surface2}; border: 1px solid {t.border}; border-radius: {r_k}px; padding: 0 {S2}px;
    min-height: {CONTROL_H}px; font-weight: 500; }}
QPushButton:hover {{ background: {QColor(t.surface2).lighter(112).name() if t.name == "dark" else QColor(t.surface2).darker(104).name()}; }}
QPushButton:pressed {{ background: {t.border}; }}
QPushButton:focus {{ border: 1px solid {t.accent}; }}
QPushButton:disabled {{ background: {t.surface}; border-color: {t.border}; }}
QPushButton[variant="primary"] {{ background: {btn}; color: {t.on_accent}; border: none; font-weight: 600; padding: 0 {S3}px; }}
QPushButton[variant="primary"]:hover {{ background: {grad_h}; }}
QPushButton[variant="primary"]:pressed {{ background: {t.btn1}; }}
QPushButton[variant="primary"]:focus {{ border: 2px solid {t.text}; }}
QPushButton[variant="primary"]:disabled {{ background: {t.border}; color: {t.text2}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[variant="ghost"]:hover {{ background: {t.hover}; }}
QPushButton[variant="danger"] {{ color: {t.error}; }}
QPushButton[variant="icon"] {{ min-width: {CONTROL_H}px; max-width: {CONTROL_H}px; padding: 0; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {t.accent}; padding: 0 {S1}px; min-height: {S3}px; }}
QPushButton[variant="link"]:hover {{ text-decoration: underline; }}
QPushButton:checked {{ background: {with_alpha(t.accent, 0.18)}; border-color: {t.accent}; color: {t.text}; }}
QPushButton[variant="section"], QPushButton[variant="section"]:checked {{ background: transparent; border: 1px solid transparent;
    text-align: left; font-weight: 600; color: {t.text}; padding: 0 {S1}px; }}
QPushButton[variant="section"]:hover {{ background: {t.hover}; }}
QPushButton[variant="section"]:focus {{ border: 1px solid {with_alpha(t.accent, 0.7)}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
    background: {t.surface2}; border: 1px solid {t.border}; border-radius: {r_k}px; padding: 0 {S1 + 2}px;
    min-height: {CONTROL_H}px; selection-background-color: {t.accent}; selection-color: {t.on_accent}; }}
QPlainTextEdit, QTextEdit {{ padding: {S1}px {S1 + 2}px; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QPlainTextEdit:hover {{ border-color: {t.text2}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {t.accent}; }}
QSpinBox, QDoubleSpinBox {{ padding-right: {S3}px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: {S3}px; border: none; background: transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: {S3}px; border: none; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
QComboBox {{ padding-right: {S4}px; }}
QComboBox::drop-down {{ border: none; width: {S4}px; }}
QComboBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {t.surface2}; border: 1px solid {t.border}; border-radius: {r_k}px; padding: 4px;
    selection-background-color: {with_alpha(t.accent, 0.25)}; selection-color: {t.text}; outline: 0; }}

QCheckBox, QRadioButton {{ spacing: {S1}px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.border}; border-radius: 4px; background: {t.surface2}; }}
QCheckBox::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; image: url({chk}); }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {t.border}; border-radius: 9px; background: {t.surface2}; }}
QRadioButton::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}

QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {grad}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t.text}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; border: 2px solid {t.accent}; }}
QSlider::handle:horizontal:hover {{ background: {t.accent}; }}

QProgressBar {{ background: {t.border}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {grad}; border-radius: 3px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {t.scroll}; border-radius: 3px; min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {t.text2}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; height: 0; width: 0; }}

QTabWidget::pane {{ border: none; background: transparent; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {t.text2}; padding: {S1}px {S2}px; border: none; border-bottom: 2px solid transparent;
    font-weight: 500; margin-right: 2px; }}
QTabBar::tab:hover {{ color: {t.text}; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}

QListWidget, QListView, QTableWidget, QTableView, QTreeWidget {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {r_k}px;
    alternate-background-color: {t.surface2}; gridline-color: {t.border}; outline: 0; }}
QListWidget::item {{ padding: {S1}px {S1 + 2}px; border-radius: 6px; margin: 1px 2px; }}
QListWidget::item:hover {{ background: {t.hover}; }}
QListWidget::item:selected, QTableView::item:selected {{ background: {with_alpha(t.accent, 0.22)}; color: {t.text}; }}
QHeaderView::section {{ background: {t.surface2}; color: {t.text2}; border: none; border-bottom: 1px solid {t.border}; padding: {S1}px {S1 + 2}px; font-weight: 500; }}
QTableCornerButton::section {{ background: {t.surface2}; border: none; }}

QGroupBox {{ border: 1px solid {t.border}; border-radius: {r_c}px; margin-top: {S2}px; padding: {S2}px; background: {t.surface}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {S2}px; padding: 0 {S1}px; color: {t.text2}; font-weight: 500; }}

QMenuBar {{ background: {t.bg}; padding: 2px {S1}px; }}
QMenuBar::item {{ padding: {S1 // 2 + 2}px {S1 + 2}px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {t.hover}; }}
QMenu {{ background: {t.surface2}; border: 1px solid {t.border}; border-radius: {r_k}px; padding: 6px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {with_alpha(t.accent, 0.25)}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 6px 4px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: {S1}px; }}
QSplitter::handle:vertical {{ height: {S1}px; }}
QMessageBox {{ background: {t.surface}; }}
QDialog {{ background: {t.bg}; }}

QFrame[role="sep"] {{ background: {t.border}; max-height: 1px; min-height: 1px; border: none; }}
"""
