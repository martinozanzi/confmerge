"""Sottotitoli: stile, raggruppamento delle righe, file .srt, testo ASS per l'export e disegno per l'anteprima.

Nell'export si usa il filtro `ass` di ffmpeg (libass): regge migliaia di righe senza appesantire il filtergraph. Le
righe sono salvate sulla linea del tempo del progetto: se cambi inizio/fine del video le righe restano valide."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontMetricsF

from .render.model import Box, Element, Fill, Outline, Shadow
from .spec import SubLine, SubtitleSettings

SIDE_MARGIN = 0.06                  # margine laterale (frazione della larghezza): il testo va a capo dentro
POSITIONS = {"bottom": "In basso", "middle": "Al centro", "top": "In alto"}

PRESETS: dict[str, dict] = {
    "Classico": dict(font="Poppins", bold=True, size=0.048, color="#FFFFFF", outline=0.0035, outline_color="#000000",
                     shadow=True, box=False, uppercase=False),
    "Su fondo scuro": dict(font="Poppins", bold=True, size=0.044, color="#FFFFFF", outline=0.0, shadow=False,
                           box=True, box_color="#000000", box_opacity=0.65, uppercase=False),
    "Giallo YouTube": dict(font="Poppins", bold=True, size=0.052, color="#FFE600", outline=0.005, outline_color="#000000",
                           shadow=True, box=False, uppercase=False),
    "Grande e centrato": dict(font="Anton", bold=False, size=0.075, color="#FFFFFF", outline=0.006,
                              outline_color="#000000", shadow=True, box=False, uppercase=True, position="middle"),
    "Leggero": dict(font="Inter", bold=False, size=0.04, color="#FFFFFF", outline=0.0, shadow=True, box=False,
                    uppercase=False),
}


def apply_preset(st: SubtitleSettings, name: str) -> None:
    for k, v in PRESETS[name].items():
        setattr(st, k, v)


def effective_lines(st: SubtitleSettings, t0: float | list, t1: float | None = None) -> list[SubLine]:
    """Righe visibili nel video finito, con i tempi di uscita (0 = inizio). Accetta un intervallo (t0, t1) oppure la lista
    degli intervalli tenuti: una riga che attraversa un taglio si spezza in due."""
    ranges = t0 if isinstance(t0, list) else [(t0, t1)]
    from . import edl
    out = []
    for ln in st.lines:
        if not ln.text.strip():
            continue
        for a, b in edl.remap_span(ranges, ln.start, ln.end):
            if b - a > 0.05:
                out.append(SubLine(a, b, ln.text.strip()))
    out.sort(key=lambda x: x.start)
    return out


def active_line(st: SubtitleSettings, t_project: float) -> SubLine | None:
    for ln in st.lines:
        if ln.start <= t_project < ln.end:
            return ln
    return None


# ------------------------------------------------------------------------------------------------ .srt
def _srt_time(t: float) -> str:
    ms = max(0, round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def to_srt(st: SubtitleSettings, t0: float | list = 0.0, t1: float = 1e9) -> str:
    lines = effective_lines(st, t0, t1)
    return "\n".join(f"{i}\n{_srt_time(ln.start)} --> {_srt_time(ln.end)}\n{ln.text}\n"
                     for i, ln in enumerate(lines, 1))


# ------------------------------------------------------------------------------------------------ ASS
def _ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_color(hex_color: str, opacity: float = 1.0) -> str:
    c = hex_color.lstrip("#")
    if len(c) != 6:
        c = "FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    a = round((1.0 - max(0.0, min(1.0, opacity))) * 255)
    return f"&H{a:02X}{b}{g}{r}".upper()


def _font(st: SubtitleSettings, px: float) -> QFont:
    f = QFont(st.font)
    f.setPixelSize(max(4, round(px)))
    f.setBold(st.bold)
    return f


def cell_ratio(st: SubtitleSettings) -> float:
    """Stima teorica: libass misura il corpo come ascendente+discendente. Usata solo se la misura reale fallisce."""
    fm = QFontMetricsF(_font(st, 1000))
    return (fm.ascent() + fm.descent()) / 1000.0


_CALIB: dict[tuple[str, bool], float] = {}
_CALIB_TEXT = "Questo e un sottotitolo di prova"


def libass_scale(st: SubtitleSettings, fonts_dir: Path | None = None) -> float:
    """Fattore tra il corpo in pixel dell'anteprima (Qt) e il «Fontsize» di libass, per quel carattere.

    Misurato davvero: libass calcola il corpo in modo diverso da carattere a carattere, e così anteprima ed export
    mostrano il testo della stessa dimensione anche con i caratteri installati sul computer."""
    key = (st.font, st.bold)
    if key in _CALIB:
        return _CALIB[key]
    k = cell_ratio(st)
    try:
        import subprocess
        import tempfile
        from . import ffmpeg_wrapper as fw
        from PySide6.QtGui import QImage
        with tempfile.TemporaryDirectory() as td:
            ass = Path(td) / "c.ass"
            ass.write_text(
                "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\n"
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
                "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,"
                f"MarginV,Encoding\nStyle: Default,{st.font},100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
                f"{-1 if st.bold else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n[Events]\nFormat: Layer,Start,End,Style,"
                f"Name,MarginL,MarginR,MarginV,Effect,Text\nDialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,"
                f"{_CALIB_TEXT}\n", encoding="utf-8")
            png = Path(td) / "c.png"
            vf = f"ass=filename='{_fp(ass)}'" + (f":fontsdir='{_fp(fonts_dir)}'" if fonts_dir else "")
            res = subprocess.run([fw.ffmpeg_path(), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                                  "color=black:size=1920x1080:rate=25:duration=1", "-vf", vf, "-frames:v", "1", str(png)],
                                 capture_output=True, creationflags=fw._CREATIONFLAGS, timeout=30)
            img = QImage(str(png))
            if res.returncode == 0 and not img.isNull():
                xs = [x for x in range(img.width()) for y in range(0, 400, 2) if img.pixelColor(x, y).red() > 128]
                if xs:
                    ink_ass = max(xs) - min(xs)
                    ink_qt = QFontMetricsF(_font(st, 100)).tightBoundingRect(_CALIB_TEXT).width()
                    if ink_ass > 50 and ink_qt > 50:
                        k = ink_qt / ink_ass
    except Exception:  # noqa: BLE001 - la misura è un'ottimizzazione: senza, resta la stima teorica
        pass
    _CALIB[key] = k
    return k


def _fp(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def to_ass(st: SubtitleSettings, t0: float | list, t1: float | None, W: int, H: int, fonts_dir: Path | None = None) -> str:
    px = st.size * H
    size = px * libass_scale(st, fonts_dir)
    align = {"bottom": 2, "middle": 5, "top": 8}.get(st.position, 2)
    if st.box:
        border, outline_col, border_w = 3, _ass_color(st.box_color, st.box_opacity), max(2.0, px * 0.28)
        shadow = 0.0
    else:
        border, outline_col, border_w = 1, _ass_color(st.outline_color), st.outline * H
        shadow = max(1.0, px * 0.06) if st.shadow else 0.0
    mv = round(st.margin * H) if align != 5 else 0
    ml = round(SIDE_MARGIN * W)
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {W}\nPlayResY: {H}\n\n[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,"
        "StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{st.font},{size:.2f},{_ass_color(st.color)},{_ass_color(st.color)},{outline_col},"
        f"&H80000000,{-1 if st.bold else 0},0,0,0,100,100,0,0,{border},{border_w:.2f},{shadow:.2f},{align},"
        f"{ml},{ml},{mv},1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    body = []
    for ln in effective_lines(st, t0, t1):
        clean = ln.text.replace("\\", "").replace("{", "(").replace("}", ")")
        txt = wrap_text(st, clean, W, H).replace("\n", "\\N")       # a capo deciso qui: uguale all'anteprima
        body.append(f"Dialogue: 0,{_ass_time(ln.start)},{_ass_time(ln.end)},Default,,0,0,0,,{txt}")
    return head + "\n".join(body) + "\n"


def write_ass(st: SubtitleSettings, ranges: list, W: int, H: int, path: Path,
              fonts_dir: Path | None = None) -> bool:
    """Scrive il file ASS; False se nell'intervallo non c'è nessuna riga. `ranges`: intervalli tenuti [(a, b)…]."""
    if not effective_lines(st, ranges):
        return False
    path.write_text(to_ass(st, ranges, None, W, H, fonts_dir), encoding="utf-8")
    return True


# ------------------------------------------------------------------------------------------------ anteprima
def wrap_text(st: SubtitleSettings, text: str, W: int, H: int) -> str:
    """A capo come libass: dentro la larghezza meno i margini laterali."""
    fm = QFontMetricsF(_font(st, st.size * H))
    limit = W * (1 - 2 * SIDE_MARGIN)
    out, cur = [], ""
    for word in (text.upper() if st.uppercase else text).split():
        trial = (cur + " " + word).strip()
        if cur and fm.horizontalAdvance(trial) > limit:
            out.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        out.append(cur)
    return "\n".join(out)


def preview_element(st: SubtitleSettings, text: str, W: int, H: int) -> Element:
    wrapped = wrap_text(st, text, W, H)
    n = wrapped.count("\n") + 1
    y = {"bottom": 1 - st.margin, "top": st.margin, "middle": 0.5}.get(st.position, 1 - st.margin)
    h_frac = st.size * 1.25 * n
    if st.position == "bottom":
        y -= h_frac / 2
    elif st.position == "top":
        y += h_frac / 2
    return Element(
        id="__subtitle", kind="text", text=wrapped, font=st.font, size=st.size, bold=st.bold, x=0.5, y=y,
        align="center", fill=Fill(color=st.color), outline=Outline(st.outline, st.outline_color),
        shadow=Shadow(enabled=st.shadow and not st.box, color="#000000", blur=0.004, distance=0.004, opacity=0.7),
        box=Box(enabled=st.box, color=st.box_color, opacity=st.box_opacity, padding=0.012, radius=0.006))
