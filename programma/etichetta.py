"""
Motore di disegno delle etichette LetraTag (altezza stampabile 30 punti).

- Tutti i caratteri installati nel PC + stili rapidi
- Emoji e simboli dentro il testo (a colori convertiti in bianco/nero, oppure a contorno)
- Corsivo, sottolineato, barrato, contorno, spaziatura, interlinea
- Cornici, ripetizione (etichette per cavi), lunghezza fissa
- Variabili: {data} {data+7} {ora} {n} {giorno} {mese} {anno}
- Codici: QR, Code128, EAN-13
"""
from __future__ import annotations

import datetime as _dt
import functools
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

H = 30  # punti stampabili in altezza

# --------------------------------------------------------------------------- #
#  Caratteri
# --------------------------------------------------------------------------- #

PRESET_FONTS = {
    "Sans": ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
    "Sans grassetto": ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    "Serif": ["times.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf"],
    "Monospace": ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"],
    "Condensato": ["arialn.ttf", "DejaVuSansCondensed.ttf", "LiberationSansNarrow-Regular.ttf"],
}

FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    "/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
    "/Library/Fonts", "/System/Library/Fonts", os.path.expanduser("~/Library/Fonts"),
]

EMOJI_FONT_FILES = ["seguiemj.ttf", "NotoColorEmoji.ttf", "Apple Color Emoji.ttc"]
SYMBOL_FONT_FILES = ["seguisym.ttf", "DejaVuSans.ttf", "NotoSansSymbols2-Regular.ttf"]

_registry: Dict[str, Tuple[str, int]] = {}


def _find_file(names) -> Optional[str]:
    for n in names:
        for d in FONT_DIRS:
            if not d or not os.path.isdir(d):
                continue
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
            # cerca anche nelle sottocartelle (Linux)
            if d.startswith("/usr") or d.startswith(os.path.expanduser("~")):
                for root, _dirs, files in os.walk(d):
                    if n in files:
                        return os.path.join(root, n)
    return None


def scan_system_fonts(cache_file: Optional[str] = None) -> Dict[str, Tuple[str, int]]:
    """Nome leggibile -> (file, indice). Risultato salvato in cache."""
    files = []
    for d in FONT_DIRS:
        if d and os.path.isdir(d):
            for root, _dirs, fs in os.walk(d):
                for f in fs:
                    if f.lower().endswith((".ttf", ".otf", ".ttc")):
                        files.append(os.path.join(root, f))
    sig = f"{len(files)}:{sum(int(os.path.getmtime(f)) for f in files[:400])}"
    if cache_file and os.path.isfile(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("sig") == sig:
                return {k: tuple(v) for k, v in data["fonts"].items()}
        except Exception:
            pass
    out: Dict[str, Tuple[str, int]] = {}
    for p in files:
        base = os.path.basename(p).lower()
        if base in [x.lower() for x in EMOJI_FONT_FILES]:
            continue
        try:
            fam, style = ImageFont.truetype(p, 12).getname()
        except Exception:
            continue
        if not fam:
            continue
        style = (style or "").strip()
        name = fam if style.lower() in ("", "regular", "normal", "book", "roman") else f"{fam} {style}"
        out.setdefault(name, (p, 0))
    if cache_file:
        try:
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump({"sig": sig, "fonts": out}, fh)
        except Exception:
            pass
    return out


def set_registry(reg: Dict[str, Tuple[str, int]]):
    _registry.clear()
    _registry.update(reg)
    get_font.cache_clear()


def font_names() -> List[str]:
    return list(PRESET_FONTS) + sorted(_registry, key=str.lower)


def has_font(name: str) -> bool:
    return name in PRESET_FONTS or name in _registry


@functools.lru_cache(maxsize=256)
def get_font(name: str, size: int):
    size = max(4, int(size))
    if name in _registry:
        p, idx = _registry[name]
        try:
            return ImageFont.truetype(p, size, index=idx)
        except Exception:
            pass
    p = _find_file(PRESET_FONTS.get(name, PRESET_FONTS["Sans grassetto"])) or \
        _find_file(PRESET_FONTS["Sans"])
    if p:
        return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


@functools.lru_cache(maxsize=1)
def _emoji_path():
    return _find_file(EMOJI_FONT_FILES)


@functools.lru_cache(maxsize=1)
def _symbol_path():
    return _find_file(SYMBOL_FONT_FILES)


@functools.lru_cache(maxsize=64)
def _emoji_font(size: int):
    p = _emoji_path()
    if not p:
        return None, 1.0
    try:
        return ImageFont.truetype(p, size), 1.0
    except OSError:  # font bitmap (Noto): solo 109 px
        return ImageFont.truetype(p, 109), size / 109.0


@functools.lru_cache(maxsize=64)
def _symbol_font(size: int):
    p = _symbol_path()
    return ImageFont.truetype(p, size) if p else None


# --------------------------------------------------------------------------- #
#  Stili rapidi
# --------------------------------------------------------------------------- #

QUICK_STYLES = {
    "Classico": {"font": ["Sans grassetto"]},
    "Moderno": {"font": ["Bahnschrift SemiBold", "Segoe UI Semibold", "Segoe UI Bold", "Sans grassetto"]},
    "Forte": {"font": ["Arial Black", "Impact", "Sans grassetto"]},
    "Elegante": {"font": ["Georgia Bold Italic", "Georgia Italic", "Times New Roman Bold Italic",
                          "DejaVu Serif Bold Italic", "Serif"]},
    "Macchina da scrivere": {"font": ["Courier New Bold", "Consolas Bold", "DejaVu Sans Mono Bold",
                                      "Monospace"]},
    "Scritto a mano": {"font": ["Segoe Print Bold", "Segoe Print", "Ink Free", "Comic Sans MS Bold",
                                "Comic Sans MS", "Sans"]},
    "Calligrafico": {"font": ["Segoe Script Bold", "Segoe Script", "Monotype Corsiva", "Gabriola",
                              "Serif"], "italic": False},
    "Stencil": {"font": ["Stencil", "Arial Black", "Sans grassetto"]},
    "Con cornice": {"font": ["Sans grassetto"], "frame": "Arrotondata"},
    "Negativo (bianco su nero)": {"font": ["Sans grassetto"], "invert": True},
    "Cavo (ripetuto)": {"font": ["Condensato", "Sans grassetto"], "repeat": 3},
}


def apply_quick_style(name: str, style: dict) -> dict:
    s = dict(DEFAULT_STYLE)
    s["dots_mm"] = style.get("dots_mm", DEFAULT_STYLE["dots_mm"])
    s["emoji"] = style.get("emoji", DEFAULT_STYLE["emoji"])
    q = QUICK_STYLES.get(name, {})
    for k, v in q.items():
        if k == "font":
            s["font"] = next((f for f in v if has_font(f)), "Sans grassetto")
        else:
            s[k] = v
    return s


DEFAULT_STYLE = {
    "font": "Sans grassetto", "size": 0, "align": "Centro",
    "italic": False, "underline": False, "strike": False, "outline": False,
    "spacing": 0, "line_gap": 1, "frame": "Nessuna", "margin": 8,
    "emoji": "Dettagliate", "repeat": 1, "repeat_gap": 20, "length_mm": 0,
    "dots_mm": 7.87, "invert": False, "stretch": 1,
}

FRAMES = ["Nessuna", "Sottile", "Spessa", "Arrotondata", "Doppia", "Tratteggiata", "Parentesi"]
EMOJI_MODES = ["Dettagliate", "Retinate", "Piene (sagoma)", "Contorno"]
ALIGNS = ["Sinistra", "Centro", "Destra"]
_FRAME_PAD = {"Nessuna": 0, "Sottile": 3, "Spessa": 4, "Arrotondata": 4, "Doppia": 5,
              "Tratteggiata": 3, "Parentesi": 0}


# --------------------------------------------------------------------------- #
#  Variabili
# --------------------------------------------------------------------------- #

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_VAR = re.compile(r"\{(data|ora|n|giorno|mese|anno|dataesteso)([+-]\d+)?\}", re.I)


def has_counter(text: str) -> bool:
    return bool(re.search(r"\{n\}", text or "", re.I))


def expand(text: str, n: int = 1, digits: int = 0, now: Optional[_dt.datetime] = None) -> str:
    now = now or _dt.datetime.now()

    def rep(m):
        k, off = m.group(1).lower(), int(m.group(2) or 0)
        d = now + _dt.timedelta(days=off)
        if k == "data":
            return d.strftime("%d/%m/%Y")
        if k == "dataesteso":
            return f"{d.day} {MESI[d.month - 1]} {d.year}"
        if k == "ora":
            return now.strftime("%H:%M")
        if k == "n":
            return str(n).zfill(digits) if digits else str(n)
        if k == "giorno":
            return GIORNI[d.weekday()]
        if k == "mese":
            return MESI[d.month - 1]
        if k == "anno":
            return str(d.year)
        return m.group(0)

    return _VAR.sub(rep, text or "")


# --------------------------------------------------------------------------- #
#  Emoji
# --------------------------------------------------------------------------- #

def _is_modifier(cp: int) -> bool:
    return cp in (0xFE0F, 0xFE0E, 0x200D, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F


def _kind(cp: int) -> str:
    if cp >= 0x1F000:
        return "emoji"
    if 0x2190 <= cp <= 0x2BFF or 0x2300 <= cp <= 0x23FF or cp in (0x00A9, 0x00AE, 0x2122, 0x3030, 0x303D):
        return "symbol"
    return "text"


def split_runs(line: str) -> List[Tuple[str, str]]:
    """[(tipo, testo)] con tipo 'text' | 'emoji' | 'symbol'. Le emoji restano un grappolo."""
    runs: List[Tuple[str, str]] = []
    i, chars = 0, list(line)
    while i < len(chars):
        cp = ord(chars[i])
        k = _kind(cp)
        if k == "text":
            j = i
            while j < len(chars) and _kind(ord(chars[j])) == "text" and not _is_modifier(ord(chars[j])):
                j += 1
            if j == i:  # modificatore isolato
                i += 1
                continue
            s = "".join(chars[i:j])
            if runs and runs[-1][0] == "text":
                runs[-1] = ("text", runs[-1][1] + s)
            else:
                runs.append(("text", s))
            i = j
            continue
        # grappolo emoji / simbolo
        j = i + 1
        while j < len(chars):
            c = ord(chars[j])
            if c == 0x200D and j + 1 < len(chars):
                j += 2
            elif _is_modifier(c):
                j += 1
            else:
                break
        cl = "".join(chars[i:j])
        if k == "symbol" and "\ufe0f" in cl:
            k = "emoji"
        runs.append((k, cl))
        i = j
    return runs


def _render_cluster(cluster: str, kind: str, size: int, asc: int, height: int, mode: str):
    """Immagine L (bianco/nero) di un'emoji o simbolo, allineata alla linea di base."""
    im = _render_cluster_inner(cluster, kind, size, asc, height, mode)
    if im is None and mode != "Contorno":
        im = _render_cluster_inner(cluster, kind, size, asc, height, "Contorno")
    return im


def _render_cluster_inner(cluster: str, kind: str, size: int, asc: int, height: int, mode: str):
    use_symbol = kind == "symbol" or mode == "Contorno"
    if use_symbol:
        f = _symbol_font(size)
        if f is not None:
            txt = cluster.replace("\ufe0f", "")
            bb = f.getbbox(txt)
            if bb and bb[2] > bb[0] and _symbol_has(f, txt):
                w = int(f.getlength(txt)) + 2
                img = Image.new("L", (max(1, w), height), 255)
                ImageDraw.Draw(img).text((1, asc), txt, font=f, fill=0, anchor="ls")
                if ImageChops.invert(img).getbbox():
                    return img
        if (kind == "symbol" or mode == "Contorno") and _emoji_font(size)[0] is None:
            return None
        if mode == "Contorno" and kind == "emoji":
            mode = "Dettagliate"
    ef, scale = _emoji_font(size if size else 20)
    if ef is None:
        return None
    try:
        fsz = 109 if scale != 1.0 else size
        w = int(ef.getlength(cluster)) + 4
        hh = int(fsz * 1.4) + 4
        rgba = Image.new("RGBA", (max(1, w), hh), (255, 255, 255, 0))
        ImageDraw.Draw(rgba).text((2, int(fsz * 1.1)), cluster, font=ef, embedded_color=True,
                                  anchor="ls", fill=(0, 0, 0, 255))
    except Exception:
        return None
    bbox = rgba.getbbox()
    if not bbox:
        return None
    rgba = rgba.crop(bbox)
    target_h = max(4, int(size * 0.92))
    if rgba.height != target_h:
        rgba = rgba.resize((max(1, round(rgba.width * target_h / rgba.height)), target_h), Image.LANCZOS)
    rgba = ImageOps.expand(rgba, border=1, fill=(255, 255, 255, 0))  # il contorno chiude anche i bordi
    alpha = rgba.getchannel("A")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    bg.alpha_composite(rgba)
    lum = bg.convert("L")
    edge = alpha.point(lambda a: 255 if a > 110 else 0)
    ring = ImageOps.invert(ImageChops.subtract(edge, edge.filter(_erode())))  # contorno nero
    if mode.startswith("Piene"):
        mono = alpha.point(lambda a: 0 if a > 110 else 255)
    elif mode.startswith("Retinate"):
        from PIL import ImageEnhance
        mono = ImageEnhance.Contrast(lum).enhance(1.4).convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
        mono = ImageChops.darker(mono, ring)
    else:
        # dettagliate: metà dei toni (i più scuri) neri, il resto bianco, più il contorno
        px = sorted(v for v, a in zip(lum.getdata(), alpha.getdata()) if a > 110)
        t = px[len(px) // 2] if px else 128
        t = max(60, min(t, 200))
        mono = ImageChops.darker(lum.point(lambda v: 0 if v < t else 255), ring)
    img = Image.new("L", (mono.width + 2, height), 255)
    top = max(0, asc - mono.height + int(size * 0.12))
    top = min(top, max(0, height - mono.height))
    img.paste(mono, (1, top))
    return img


def _erode():
    from PIL import ImageFilter
    return ImageFilter.MinFilter(3)


def _glyph_bytes(f, c: str) -> bytes:
    sz = getattr(f, "size", 20)
    im = Image.new("L", (sz * 2, sz * 2), 0)
    ImageDraw.Draw(im).text((2, 2), c, font=f, fill=255)
    return im.tobytes()


def _symbol_has(f, txt: str) -> bool:
    """False se il carattere manca nel font (verrebbe disegnato un quadratino)."""
    try:
        missing = _glyph_bytes(f, "\U0010FFFD")
        return all(_glyph_bytes(f, c) != missing for c in txt if c not in "\u200d\ufe0f")
    except Exception:
        return True


def emoji_preview(cluster: str, size: int = 28) -> Image.Image:
    """Anteprima a colori per il selettore."""
    ef, scale = _emoji_font(size)
    img = Image.new("RGBA", (size + 8, size + 8), (255, 255, 255, 0))
    if ef is None:
        return img
    fsz = 109 if scale != 1.0 else size
    big = Image.new("RGBA", (int(fsz * 1.6), int(fsz * 1.6)), (255, 255, 255, 0))
    try:
        ImageDraw.Draw(big).text((4, int(fsz * 1.2)), cluster, font=ef, embedded_color=True, anchor="ls")
    except Exception:
        return img
    bb = big.getbbox()
    if not bb:
        f = _symbol_font(size)
        if f:
            ImageDraw.Draw(img).text((4, size), cluster, font=f, fill=(0, 0, 0, 255), anchor="ls")
        return img
    big = big.crop(bb)
    big.thumbnail((size, size), Image.LANCZOS)
    img.alpha_composite(big, ((img.width - big.width) // 2, (img.height - big.height) // 2))
    return img


# --------------------------------------------------------------------------- #
#  Testo
# --------------------------------------------------------------------------- #

def _render_line(line: str, size: int, st: dict) -> Image.Image:
    font = get_font(st["font"], size)
    asc, desc = font.getmetrics()
    stroke = max(1, size // 16) if st.get("outline") else 0
    height = asc + desc + 2 * stroke + 2
    base = asc + stroke + 1
    spacing = int(st.get("spacing", 0))
    pieces = []  # (x, tipo, contenuto)
    x = stroke + 1
    for kind, txt in split_runs(line):
        if kind == "text":
            if spacing:
                for ch in txt:
                    pieces.append((x, "t", ch))
                    x += font.getlength(ch) + spacing
            else:
                pieces.append((x, "t", txt))
                x += font.getlength(txt)
        else:
            im = _render_cluster(txt, kind, size, base, height, st.get("emoji", "Dettagliate"))
            if im is None:
                continue
            pieces.append((x, "i", im))
            x += im.width + max(0, spacing)
    width = int(x) + stroke + 2
    img = Image.new("L", (max(1, width), height), 255)
    d = ImageDraw.Draw(img)
    for px, k, c in pieces:
        if k == "t":
            if stroke:
                d.text((px, base), c, font=font, fill=255, stroke_width=stroke, stroke_fill=0, anchor="ls")
            else:
                d.text((px, base), c, font=font, fill=0, anchor="ls")
        else:
            img.paste(ImageChops.darker(img.crop((int(px), 0, int(px) + c.width, height)), c), (int(px), 0))
    th = max(1, size // 14)
    ink = ImageChops.invert(img).getbbox()
    x0, x1 = (ink[0], ink[2]) if ink else (0, width)
    if st.get("underline"):
        y = min(height - th, base + max(1, desc // 2))
        d.rectangle((x0, y, x1, y + th - 1), fill=0)
    if st.get("strike"):
        y = base - int(size * 0.32)
        d.rectangle((x0, y, x1, y + th - 1), fill=0)
    return img


def _render_block(lines: List[str], size: int, st: dict) -> Image.Image:
    imgs = [_render_line(l, size, st) for l in lines]
    gap = int(st.get("line_gap", 1))
    # ritaglio verticale per riga sull'inchiostro (le righe stanno più vicine)
    crops = []
    for im in imgs:
        bb = ImageChops.invert(im).getbbox()
        crops.append(im.crop((0, bb[1], im.width, bb[3])) if bb else im.crop((0, 0, im.width, 1)))
    # rifinitura orizzontale per l'allineamento
    trimmed = []
    for im in crops:
        bb = ImageChops.invert(im).getbbox()
        trimmed.append(im.crop((bb[0], 0, bb[2], im.height)) if bb else im)
    w = max(im.width for im in trimmed)
    h = sum(im.height for im in trimmed) + gap * (len(trimmed) - 1)
    out = Image.new("L", (max(1, w), max(1, h)), 255)
    y = 0
    for im in trimmed:
        a = st.get("align", "Centro")
        x = 0 if a == "Sinistra" else (w - im.width if a == "Destra" else (w - im.width) // 2)
        out.paste(im, (x, y))
        y += im.height + gap
    if st.get("italic"):
        sh = 0.22
        extra = int(out.height * sh) + 1
        out = out.transform((out.width + extra, out.height), Image.AFFINE,
                            (1, sh, -extra, 0, 1, 0), resample=Image.BICUBIC, fillcolor=255)
        bb = ImageChops.invert(out).getbbox()
        if bb:
            out = out.crop((bb[0], 0, bb[2], out.height))
    return out


def render_text(text: str, st: dict) -> Image.Image:
    """Etichetta di testo completa (immagine L alta H)."""
    st = {**DEFAULT_STYLE, **(st or {})}
    lines = (text or "").replace("\r", "").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        lines = [" "]
    pad = _FRAME_PAD.get(st["frame"], 0)
    inner = H - 2 * pad
    size = int(st.get("size") or 0)
    if size > 0:
        block = _render_block(lines, size, st)
    else:
        probe = _render_block(lines, 40, st)
        size = max(5, int(40 * inner / max(1, probe.height)) + 3)
        block = _render_block(lines, size, st)
        while block.height > inner and size > 5:
            size -= 1
            block = _render_block(lines, size, st)
    if block.height > inner:
        block = block.resize((max(1, round(block.width * inner / block.height)), inner), Image.LANCZOS)
    return compose(block, st)


def compose(content: Image.Image, st: dict) -> Image.Image:
    """Ripetizione, margini, lunghezza fissa, cornice, negativo."""
    st = {**DEFAULT_STYLE, **(st or {})}
    rep = max(1, int(st.get("repeat") or 1))
    if rep > 1:
        g = int(st.get("repeat_gap", 20))
        tiled = Image.new("L", (content.width * rep + g * (rep - 1), content.height), 255)
        for i in range(rep):
            tiled.paste(content, (i * (content.width + g), 0))
        content = tiled
    pad = _FRAME_PAD.get(st["frame"], 0)
    margin = int(st.get("margin", 8))
    bracket = 6 if st["frame"] == "Parentesi" else 0
    w = content.width + 2 * (margin + pad + bracket)
    target = int(round(float(st.get("length_mm") or 0) * float(st.get("dots_mm") or 7.87)))
    if target > w:
        w = target
    out = Image.new("L", (w, H), 255)
    a = st.get("align", "Centro")
    free = w - content.width - 2 * (pad + bracket)
    if a == "Sinistra":
        x = pad + bracket + margin
    elif a == "Destra":
        x = w - pad - bracket - margin - content.width
    else:
        x = pad + bracket + free // 2
    out.paste(content, (x, (H - content.height) // 2))
    _frame(out, st["frame"])
    if st.get("invert"):
        out = ImageOps.invert(out)
    return out


def _frame(img: Image.Image, kind: str):
    d = ImageDraw.Draw(img)
    w, h = img.size
    if kind == "Sottile":
        d.rectangle((0, 0, w - 1, h - 1), outline=0, width=1)
    elif kind == "Spessa":
        d.rectangle((0, 0, w - 1, h - 1), outline=0, width=2)
    elif kind == "Arrotondata":
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=8, outline=0, width=2)
    elif kind == "Doppia":
        d.rectangle((0, 0, w - 1, h - 1), outline=0, width=1)
        d.rectangle((2, 2, w - 3, h - 3), outline=0, width=1)
    elif kind == "Tratteggiata":
        for x in range(0, w, 6):
            d.line((x, 0, min(w - 1, x + 3), 0), fill=0)
            d.line((x, h - 1, min(w - 1, x + 3), h - 1), fill=0)
        for y in range(0, h, 6):
            d.line((0, y, 0, min(h - 1, y + 3)), fill=0)
            d.line((w - 1, y, w - 1, min(h - 1, y + 3)), fill=0)
    elif kind == "Parentesi":
        for x0, s in ((1, 1), (w - 2, -1)):
            d.line((x0, 1, x0, h - 2), fill=0, width=2)
            d.line((x0, 1, x0 + 4 * s, 1), fill=0, width=2)
            d.line((x0, h - 2, x0 + 4 * s, h - 2), fill=0, width=2)


# --------------------------------------------------------------------------- #
#  Codici
# --------------------------------------------------------------------------- #

CODE_TYPES = ["QR code", "Code128", "EAN-13"]


def render_code(kind: str, data: str, side_text: str, st: dict, module: int = 2) -> Image.Image:
    st = {**DEFAULT_STYLE, **(st or {})}
    data = (data or "").strip()
    if not data:
        raise ValueError("Scrivi il contenuto del codice.")
    if kind == "QR code":
        try:
            import qrcode
            from qrcode.constants import ERROR_CORRECT_L
        except ImportError:
            raise RuntimeError("Manca la libreria qrcode: rifai INSTALLA.pyw")
        q = qrcode.QRCode(error_correction=ERROR_CORRECT_L, box_size=1, border=0)
        q.add_data(data)
        q.make(fit=True)
        m = q.get_matrix()
        n = len(m)
        if n > H:
            raise ValueError("Testo troppo lungo per un QR alto 30 punti: max circa 25 caratteri.")
        sc = max(1, H // n)
        code = Image.new("L", (n * sc, n * sc), 255)
        d = ImageDraw.Draw(code)
        for y, row in enumerate(m):
            for x, v in enumerate(row):
                if v:
                    d.rectangle((x * sc, y * sc, x * sc + sc - 1, y * sc + sc - 1), fill=0)
    else:
        try:
            import barcode
        except ImportError:
            raise RuntimeError("Manca la libreria python-barcode: rifai INSTALLA.pyw")
        if kind == "EAN-13":
            digits = re.sub(r"\D", "", data)
            if len(digits) not in (12, 13):
                raise ValueError("L'EAN-13 vuole 12 o 13 cifre.")
            mods = barcode.get("ean13", digits[:12]).build()[0]
        else:
            mods = barcode.get("code128", data).build()[0]
        module = max(1, int(module))
        quiet = 8 * module
        code = Image.new("L", (len(mods) * module + 2 * quiet, H), 255)
        d = ImageDraw.Draw(code)
        for i, b in enumerate(mods):
            if b == "1":
                x = quiet + i * module
                d.rectangle((x, 0, x + module - 1, H - 1), fill=0)
    frame = st["frame"] if kind == "QR code" else "Nessuna"
    inner = H - 2 * _FRAME_PAD.get(frame, 0)
    if code.height > inner:
        frame, inner = "Nessuna", H
    parts = [code]
    if side_text and side_text.strip():
        tst = {**st, "frame": "Nessuna", "margin": 0, "repeat": 1, "length_mm": 0, "invert": False}
        t = render_text(side_text, tst)
        bb = ImageChops.invert(t).getbbox()
        if bb:
            t = t.crop(bb)
            if t.height > inner:
                t = t.resize((max(1, round(t.width * inner / t.height)), inner), Image.LANCZOS)
            parts.append(t)
    gap = 6
    w = sum(p.width for p in parts) + gap * (len(parts) - 1)
    content = Image.new("L", (w, max(p.height for p in parts)), 255)
    x = 0
    for p in parts:
        content.paste(p, (x, (content.height - p.height) // 2))
        x += p.width + gap
    return compose(content, {**st, "repeat": 1, "frame": frame})


# --------------------------------------------------------------------------- #
#  Raccolta di emoji e simboli per il selettore
# --------------------------------------------------------------------------- #

EMOJI_CATEGORIES = {
    "Simboli": "★☆♥♡✓✔✗✘☐☑☒⚠☢☣♻⚡☎✉✂✏✎⌚⌛☀☁☂☃❄♨☕⚙⚖⚓✈♠♣♦♪♫☺☹☯☮✝✡",
    "Frecce": "←↑→↓↔↕↖↗↘↙⇐⇑⇒⇓⇔➔➜➡⬅⬆⬇↩↪⟲⟳▲▼◀▶△▽◁▷",
    "Numeri": "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳❶❷❸❹❺❻❼❽❾❿ⒶⒷⒸⒹⒺ",
    "Forme": "●○◉◎■□▪▫◆◇◈▲△★☆♦♢⬤⬛⬜",
    "Cucina": "🍎🍐🍊🍋🍌🍉🍇🍓🍒🍑🥝🍅🥕🌽🥔🧅🧄🌶🥦🥬🍄🥜🌰🍞🥖🥐🧀🥚🍳🥓🥩🍗🍖🐟🍤🍝🍕🍔🍟🥗🍚🍜🍲🥫🧂🍯🥛☕🍵🧃🍷🍺🍰🍪🍫🍬🍭🧁🥄🍴🔪🫙",
    "Casa": "🏠🛏🛋🪑🚪🪟🛁🚿🚽🧻🧼🧽🧺🧹🪣🔑🗝💡🔦🕯🔌🔋🧯🧸🪴🌱🧴🪥🧷🪡🧵👕👖👗🧦👟🧤🧣🎁📦",
    "Ufficio": "📁📂🗂📄📃📑📊📈📉📋📌📍📎🖇📏📐✂🖊🖋✒🖌🖍📝📒📓📔📕📗📘📙📚📖🔖🏷💼📅📆🗓📇🗃🗄🗑💻🖥🖨⌨🖱💾💿📀🔒🔓📧📨📮☎📞📱",
    "Lavoro": "🔧🔨⚒🛠🪛🪚🔩⚙🧰🧲🪜🧪🧫🧬🔬🔭📡💊💉🩹🩺⚠🚧⛔🚫🔞📵🚭♿🔥💧🌡",
    "Viaggi": "🚗🚕🚙🚌🚑🚒🚓🚚🚜🏍🚲🛴✈🚀🚢⛵🏖🏕🗺🧭⛽🏥🏫🏢🏭⛪🏰🗼🎒🧳",
    "Natura": "🌞🌙⭐🌟☀⛅🌧⛈❄☃🌈🌊🔥🌸🌹🌻🌷🌼🍀🍁🍂🌲🌳🌵🐶🐱🐭🐰🦊🐻🐼🐸🐔🐧🐦🐝🦋🐞🐠🐬",
    "Faccine": "😀😃😄😁😆😊🙂😉😍🥰😘😎🤓🤔😐😴😮😢😭😡🤯🥳😱🤗👍👎👌✌🤞👏🙏💪👀❤🧡💛💚💙💜🖤🤍💔✨🎉🎂🎈",
    "Bambini": "👶🍼🧸🪀🪁🎨🖍🧩🎲♟🎮🚂🦄🐣🦖🐳🎠🎪",
}
