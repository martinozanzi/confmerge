"""Sottotitoli: stile, raggruppamento delle righe, file .srt, testo ASS per l'export e disegno per l'anteprima.

Nell'export si usa il filtro `ass` di ffmpeg (libass): regge migliaia di righe senza appesantire il filtergraph. Le
righe sono salvate sulla linea del tempo del progetto: se cambi inizio/fine del video le righe restano valide."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtGui import QFont, QFontMetricsF

from .render.model import Anim, Box, Element, Fill, Outline, Shadow
from .spec import SubLine, SubtitleSettings

SAMPLE_TEXT = "Così si leggeranno i sottotitoli"
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
    "Reel a blocchi": dict(font="Anton", bold=False, size=0.062, color="#FFFFFF", outline=0.007, outline_color="#000000",
                           shadow=True, box=False, uppercase=True, position="middle", chunk_words=3, anim="pop"),
    "Parola evidenziata": dict(font="Poppins", bold=True, size=0.04, color="#FFFFFF", outline=0.006, outline_color="#000000",
                               shadow=True, box=False, uppercase=True, position="middle", chunk_words=3, anim="highlight",
                               hl_color="#FFE600", hl_scale=1.2),
    "Leggero": dict(font="Inter", bold=False, size=0.04, color="#FFFFFF", outline=0.0, shadow=True, box=False,
                    uppercase=False),
}


PRESET_DEFAULTS = dict(position="bottom", chunk_words=0, anim="none", x=0.5, y=-1.0, box=False, hl_color="#FFE600", hl_scale=1.2)
ANIMS = {"none": "Nessuna", "fade": "Dissolvenza", "pop": "Pop (compare ingrandendosi)",
         "highlight": "Parola evidenziata (si colora e ingrandisce)"}
CHUNKS = {0: "Tutta la frase", 3: "3 parole per volta", 2: "2 parole per volta", 1: "Una parola per volta"}


def apply_preset(st: SubtitleSettings, name: str) -> None:
    for k, v in {**PRESET_DEFAULTS, **PRESETS[name]}.items():
        setattr(st, k, v)


def chunked_lines(st: SubtitleSettings) -> list[SubLine]:
    """Le righe come si vedono: con «poche parole per volta» ogni frase si spezza (il tempo si divide per lunghezza)."""
    if st.chunk_words <= 0:
        return list(st.lines)
    from .transcribe import Line, split_words
    out = []
    for ln in st.lines:
        parts = split_words([Line(ln.start, ln.end, ln.text, list(ln.times) or None)], st.chunk_words)
        out += [SubLine(x.start, x.end, x.text, list(x.times or [])) for x in parts]
    return out


def word_times(ln: SubLine) -> list[float]:
    """Inizio di ogni parola della riga: i tempi veri se ci sono, altrimenti in proporzione alla lunghezza delle parole."""
    toks = ln.text.split()
    if ln.times and len(ln.times) == len(toks):
        return list(ln.times)
    total = sum(len(t) + 1 for t in toks) or 1
    out, pos = [], ln.start
    for t in toks:
        out.append(pos)
        pos += (ln.end - ln.start) * (len(t) + 1) / total
    return out


def word_index(ln: SubLine, t: float) -> int:
    """La parola che si sta dicendo al tempo t (stessa scala della riga)."""
    idx = 0
    for i, ts in enumerate(word_times(ln)):
        if t >= ts - 1e-6:
            idx = i
    return idx


def effective_lines(st: SubtitleSettings, t0: float | list, t1: float | None = None) -> list[SubLine]:
    """Righe visibili nel video finito, con i tempi di uscita (0 = inizio). Accetta un intervallo (t0, t1) oppure la lista
    degli intervalli tenuti: una riga che attraversa un taglio si spezza in due."""
    ranges = t0 if isinstance(t0, list) else [(t0, t1)]
    from . import edl
    out = []
    for ln in chunked_lines(st):
        if not ln.text.strip():
            continue
        times = word_times(ln)
        for a, b in edl.remap_span(ranges, ln.start, ln.end):
            if b - a > 0.05:
                whole = abs((b - a) - (ln.end - ln.start)) < 0.02          # nessun taglio dentro: i tempi si spostano e basta
                out.append(SubLine(a, b, ln.text.strip(), [round(x - ln.start + a, 3) for x in times] if whole else []))
    out.sort(key=lambda x: x.start)
    return out


def active_line(st: SubtitleSettings, t_project: float) -> SubLine | None:
    for ln in chunked_lines(st):
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
    free = f"{{\\an5\\pos({st.x * W:.1f},{st.y * H:.1f})}}" if st.y >= 0 else ""    # trascinati a mano: posizione esatta
    free += {"fade": "{\\fad(140,90)}",
             "pop": "{\\fscx72\\fscy72\\t(0,130,\\fscx108\\fscy108)\\t(130,220,\\fscx100\\fscy100)\\fad(60,60)}"}.get(st.anim, "")
    for ln in effective_lines(st, t0, t1):
        clean = ln.text.replace("\\", "").replace("{", "(").replace("}", ")")
        wrapped = wrap_text(st, clean, W, H)
        if st.anim == "highlight":                                          # un evento per parola: quella detta si colora e cresce
            times = word_times(ln)
            hl = f"{{\\c{_ass_color(st.hl_color)}\\fscx{st.hl_scale * 100:.0f}\\fscy{st.hl_scale * 100:.0f}}}"
            toks = list(re.finditer(r"\S+", wrapped))
            for k in range(min(len(toks), len(times))):
                a = times[k] if k else ln.start
                b = times[k + 1] if k + 1 < len(times) else ln.end
                if b - a < 0.02:
                    continue
                m = toks[k]
                txt = wrapped[:m.start()] + hl + m.group() + "{\\r}" + wrapped[m.end():]
                body.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{free}" + txt.replace("\n", "\\N"))
            continue
        txt = free + wrapped.replace("\n", "\\N")       # a capo deciso qui: uguale all'anteprima
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
    if st.anim == "highlight":
        limit /= max(1.0, st.hl_scale)                       # la parola evidenziata cresce: si lascia il posto
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


def effective_margin(st: SubtitleSettings, safe: list | tuple | None = None) -> float:
    """Distanza dal bordo davvero usata: non meno della zona coperta dall'interfaccia della piattaforma (+ un po' d'aria)."""
    top, bottom = (list(safe or []) + [0.0, 0.0])[:2]
    if st.position == "bottom" and bottom:
        return max(st.margin, bottom + 0.02)
    if st.position == "top" and top:
        return max(st.margin, top + 0.02)
    return st.margin


def preview_element(st: SubtitleSettings, text: str, W: int, H: int, safe: list | tuple | None = None,
                    hl_word: int = -1) -> Element:
    """L'elemento che disegna il sottotitolo: anteprima e trascinamento. L'animazione d'entrata parte a t = 0."""
    wrapped = wrap_text(st, text, W, H)
    n = wrapped.count("\n") + 1
    margin = effective_margin(st, safe)
    y = {"bottom": 1 - margin, "top": margin, "middle": 0.5}.get(st.position, 1 - margin)
    h_frac = st.size * 1.25 * n
    if st.position == "bottom":
        y -= h_frac / 2
    elif st.position == "top":
        y += h_frac / 2
    x = 0.5
    if st.y >= 0:
        x, y = st.x, st.y
    return Element(
        id="__subtitle", kind="text", text=wrapped, font=st.font, size=st.size, bold=st.bold, x=x, y=y,
        align="center", fill=Fill(color=st.color), outline=Outline(st.outline * 2, st.outline_color),
        shadow=Shadow(enabled=st.shadow and not st.box, color="#000000", blur=0.004, distance=0.004, opacity=0.7),
        box=Box(enabled=st.box, color=st.box_color, opacity=st.box_opacity, padding=0.012, radius=0.006),
        anim_in=Anim(kind=st.anim if st.anim in ("fade", "pop") else "none", duration=0.2, easing="back"),
        hl_word=hl_word if st.anim == "highlight" else -1, hl_color=st.hl_color, hl_scale=st.hl_scale)
