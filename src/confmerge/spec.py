"""Specifica completa di rendering (immagine, audio, grafica, slide, credito, export)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .render.model import Element, LowerThird, Scene
from .serde import from_dict, to_dict

RES_SHORT = {"720p": 720, "1080p": 1080, "1440p": 1440, "4K": 2160}
ASPECTS = {"16:9": (16, 9), "4:3": (4, 3), "1:1": (1, 1), "9:16": (9, 16), "4:5": (4, 5)}
LAYOUTS = {
    "speaker": "Solo relatore",
    "slide_full": "Slide a schermo intero, relatore in piccolo",
    "speaker_full": "Relatore a schermo intero, slide in piccolo",
    "side_by_side": "Affiancati",
}
PRESETS = ["YouTube 1080p", "YouTube 1440p", "YouTube 4K", "Veloce (copia stream)", "Personalizzato"]


@dataclass
class ImageSettings:
    resolution: str = "1080p"
    aspect: str = "16:9"
    custom_w: float = 16.0
    custom_h: float = 9.0
    fps: float | None = None
    crop_l: float = 0.0
    crop_t: float = 0.0
    crop_r: float = 0.0
    crop_b: float = 0.0
    zoom: float = 1.0
    cx: float = 0.5
    cy: float = 0.5
    kenburns: bool = False
    zoom2: float = 1.3
    cx2: float = 0.5
    cy2: float = 0.5
    kb_t0: float = 0.0
    kb_t1: float = 10.0
    vertical_mode: str = "bars"   # bars | crop
    fade_in: float = 0.0          # video + audio
    fade_out: float = 0.0
    clip_transition: str = "cut"       # tra una clip e l'altra: cut | fadeblack | fadewhite
    clip_transition_dur: float = 0.6
    reframe: str = "fill"          # come entra un video orizzontale in un formato verticale: fill (ritaglia) | blur | bars
    reframe_x: float = 0.5         # fill: dove sta la finestra di ritaglio (0 = sinistra, 1 = destra)
    reframe_y: float = 0.5


@dataclass
class AudioSettings:
    loudnorm: bool = True
    highpass: bool = False
    denoise: bool = False
    compressor: bool = False
    music_path: str = ""            # brano di sottofondo (vuoto = nessuna musica)
    music_db: float = -12.0         # livello della musica rispetto al parlato, nelle pause
    music_duck: bool = True         # abbassa la musica quando c'è voce
    music_duck_db: float = -8.0     # di quanto si abbassa ancora mentre si parla
    music_fade: float = 2.0         # dissolvenza in entrata e in uscita (s)


@dataclass
class SubLine:
    start: float = 0.0            # secondi sulla linea del tempo del progetto (non del video di uscita)
    end: float = 0.0
    text: str = ""
    times: list[float] = field(default_factory=list)   # inizio di ogni parola (stessa scala di start); vuoto = in proporzione


@dataclass
class SubtitleSettings:
    """Sottotitoli sul video: lo stile fa parte del profilo, le righe appartengono al lavoro corrente."""
    enabled: bool = False
    font: str = "Poppins"
    bold: bool = True
    size: float = 0.048            # frazione dell'altezza
    color: str = "#FFFFFF"
    outline: float = 0.0035        # spessore del bordo (frazione dell'altezza)
    outline_color: str = "#000000"
    shadow: bool = True
    box: bool = False              # sfondo pieno dietro il testo
    box_color: str = "#000000"
    box_opacity: float = 0.65
    position: str = "bottom"       # bottom | middle | top
    margin: float = 0.085          # distanza dal bordo (frazione dell'altezza)
    x: float = 0.5                 # centro trascinato a mano (frazioni del fotogramma); vale solo se y >= 0
    y: float = -1.0                # -1 = segue «position» e «margin»
    uppercase: bool = False
    chunk_words: int = 0           # 0 = una frase per volta; 2-3 = poche parole alla volta, come nei reel
    anim: str = "none"             # none | fade | pop | highlight (la parola detta si colora e si ingrandisce)
    hl_color: str = "#FFE600"      # colore della parola evidenziata
    hl_scale: float = 1.2          # quanto si ingrandisce (1,0 = per niente)
    source_lang: str = "it"        # lingua parlata nel video ("" = la riconosce da sola)
    lang: str = ""                 # lingua dei sottotitoli ("" = la stessa del video: altrimenti si traducono)
    max_chars: int = 38            # lunghezza massima di una riga quando si creano i sottotitoli
    range_start: float = 0.0       # intervallo trascritto (secondi del progetto)
    range_end: float = 0.0
    lines: list[SubLine] = field(default_factory=list)


@dataclass
class PipSettings:
    corner: str = "br"            # tl | tr | bl | br
    size: float = 0.28            # frazione della larghezza
    margin: float = 0.03
    border: float = 0.004
    border_color: str = "#FFFFFF"
    radius: float = 0.012
    shadow: bool = True


@dataclass
class LayoutSpan:
    t: float = 0.0
    layout: str = "speaker"


@dataclass
class SlideChange:
    t: float = 0.0
    index: int = 0


@dataclass
class SlideSettings:
    enabled: bool = False
    files: list[str] = field(default_factory=list)    # PDF o immagini
    video: str = ""                                    # in alternativa: secondo video (cattura schermo)
    video_offset: float = 0.0                          # sync: video_slide(t) ≈ camera(t + offset)
    changes: list[SlideChange] = field(default_factory=list)
    layouts: list[LayoutSpan] = field(default_factory=lambda: [LayoutSpan(0.0, "slide_full")])
    pip: PipSettings = field(default_factory=PipSettings)


@dataclass
class CreditSettings:
    enabled: bool = True
    duration: float = 3.0
    qr: bool = False


@dataclass
class ExportSettings:
    preset: str = "YouTube 1080p"
    custom_height: int = 1080
    bitrate_mbps: float | None = None   # None = valore del preset
    crf_mode: bool = False
    crf: int = 18
    audio_kbps: int | None = None
    encoder: str = "auto"               # auto | libx264 | h264_nvenc | h264_qsv | h264_amf
    out_dir: str = ""
    name: str = "conferenza"


@dataclass
class Graphics:
    elements: list[Element] = field(default_factory=list)
    lower_thirds: list[LowerThird] = field(default_factory=list)
    title: Scene = field(default_factory=lambda: Scene(enabled=False, duration=4.0))
    outro: Scene = field(default_factory=lambda: Scene(enabled=False, duration=4.0))
    title_template: str = ""          # modello scelto dalla galleria (solo per evidenziarlo)
    outro_template: str = ""
    transition_style: str = ""        # stile unico scelto nella modalità Semplice


@dataclass
class LogoPlacement:
    """Un logo del kit del marchio sul video: dove sta, quanto è grande, se si vede."""
    path: str = ""
    role: str = "main"            # main | symbol | …
    name: str = ""
    corner: str = "tr"            # tl | tr | bl | br | free (trascinato: vale x, y)
    x: float = 0.5                # centro, frazione della larghezza (solo con corner = free)
    y: float = 0.5
    size: float = 0.11            # larghezza, frazione della larghezza del video
    opacity: float = 1.0
    enabled: bool = True


@dataclass
class BrandSettings:
    """Marchio applicato al lavoro (copiato dal kit: il video si ricostruisce anche senza l'archivio)."""
    kit_id: str = ""
    name: str = ""
    logos: list[LogoPlacement] = field(default_factory=list)
    safe: list[float] = field(default_factory=list)      # sopra, sotto, sinistra, destra: margini della piattaforma (Studio Social)


@dataclass
class SocialSettings:
    """Studio Social: dove pubblicare e come mostrare le zone di sicurezza (non finiscono mai nel file)."""
    platforms: list[str] = field(default_factory=lambda: ["shorts"])
    show_safe: bool = True
    skip_silence_db: float = 35.0      # sensibilità: quanti dB sotto la voce si considera silenzio
    skip_silence_min: float = 0.7      # pausa minima da togliere (s)
    skip_silence_pad: float = 0.15     # margine tenuto prima e dopo il parlato (s)


@dataclass
class RenderSpec:
    image: ImageSettings = field(default_factory=ImageSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    subtitles: SubtitleSettings = field(default_factory=SubtitleSettings)
    social: SocialSettings = field(default_factory=SocialSettings)
    brand: BrandSettings = field(default_factory=BrandSettings)
    graphics: Graphics = field(default_factory=Graphics)
    slides: SlideSettings = field(default_factory=SlideSettings)
    credit: CreditSettings = field(default_factory=CreditSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    variables: dict[str, str] = field(default_factory=dict)   # testi variabili del profilo (titolo, relatore, data…)

    def to_dict(self) -> dict:
        return to_dict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RenderSpec":
        return from_dict(cls, d)


def output_size(img: ImageSettings, export: ExportSettings | None = None) -> tuple[int, int]:
    """Dimensioni di uscita (pari). La risoluzione indica il lato corto."""
    short = RES_SHORT.get(img.resolution, 1080)
    if export is not None and export.preset == "YouTube 1440p":
        short = 1440
    elif export is not None and export.preset == "YouTube 4K":
        short = 2160
    elif export is not None and export.preset == "YouTube 1080p":
        short = 1080
    elif export is not None and export.preset == "Personalizzato":
        short = export.custom_height
    aw, ah = (img.custom_w, img.custom_h) if img.aspect == "custom" else ASPECTS.get(img.aspect, (16, 9))
    ar = aw / ah
    if ar >= 1:
        h = short
        w = round(h * ar)
    else:
        w = short
        h = round(w / ar)
    return w // 2 * 2, h // 2 * 2


def video_bitrate_bps(export: ExportSettings, h_short: int, fps: float) -> float:
    if export.bitrate_mbps:
        return export.bitrate_mbps * 1e6
    hi = fps > 30.5
    table = {720: (5.0, 7.5), 1080: (8.0, 12.0), 1440: (16.0, 24.0), 2160: (35.0, 53.0)}
    key = min(table, key=lambda k: abs(k - h_short))
    return table[key][1 if hi else 0] * 1e6


def audio_bitrate_bps(export: ExportSettings, h_short: int) -> float:
    if export.audio_kbps:
        return export.audio_kbps * 1000.0
    return 320_000.0 if h_short >= 2160 else 256_000.0 if h_short >= 1440 else 192_000.0


def view_transform(img: ImageSettings, t: float) -> tuple[float, float, float]:
    """(zoom, cx, cy) al tempo t (secondi di uscita). Stessa funzione usata dall'anteprima."""
    if not img.kenburns:
        return img.zoom, img.cx, img.cy
    span = max(img.kb_t1 - img.kb_t0, 1e-3)
    p = min(1.0, max(0.0, (t - img.kb_t0) / span))
    s = p * p * (3 - 2 * p)
    return (img.zoom + (img.zoom2 - img.zoom) * s,
            img.cx + (img.cx2 - img.cx) * s,
            img.cy + (img.cy2 - img.cy) * s)
