"""
Logica di base per stampare etichette sulla DYMO LetraTag 200B via Bluetooth LE.

- Rendering di testo / immagini / PDF in un'immagine alta 30 punti (l'area stampabile)
- Lettura di fogli OpenOffice/LibreOffice Calc (.ods), CSV ed Excel (.xlsx)
- Comunicazione Bluetooth tramite la libreria open source "dymo-bluetooth" (MIT, ysfchn)
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

PRINT_HEIGHT = 30          # punti stampabili in altezza (testina LetraTag)
MAX_WIDTH = 8000           # lunghezza massima del raster accettata
MIN_WIDTH = 40             # lavori troppo corti vengono ignorati dalla stampante


# --------------------------------------------------------------------------- #
#  Font
# --------------------------------------------------------------------------- #

FONT_CANDIDATES = {
    "Sans": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
             "Helvetica.ttc"],
    "Sans grassetto": ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                       "LiberationSans-Bold.ttf"],
    "Serif": ["times.ttf", "Times New Roman.ttf", "DejaVuSerif.ttf",
              "LiberationSerif-Regular.ttf"],
    "Monospace": ["consola.ttf", "cour.ttf", "Courier New.ttf", "DejaVuSansMono.ttf",
                  "LiberationMono-Regular.ttf"],
    "Condensato": ["arialn.ttf", "Arial Narrow.ttf", "DejaVuSansCondensed.ttf",
                   "LiberationSansNarrow-Regular.ttf"],
}

_FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.expanduser(r"~\AppData\Local\Microsoft\Windows\Fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype",
    "/Library/Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
]


def _find_font_file(family: str) -> Optional[str]:
    for name in FONT_CANDIDATES.get(family, []):
        try:  # Pillow cerca da solo nelle cartelle di sistema
            ImageFont.truetype(name, 10)
            return name
        except OSError:
            pass
        for d in _FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def load_font(family: str, size: int):
    path = _find_font_file(family)
    if path:
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow vecchio
        return ImageFont.load_default()


# --------------------------------------------------------------------------- #
#  Rendering
# --------------------------------------------------------------------------- #

def render_text(text: str, family: str = "Sans grassetto", size: int = 0,
                frame: bool = False, invert: bool = False, margin: int = 6,
                align: str = "center") -> Image.Image:
    """Restituisce un'immagine 'L' alta PRINT_HEIGHT con il testo (nero su bianco).
    size = 0 -> dimensione automatica, la più grande che entra in altezza."""
    lines = [l for l in (text or "").replace("\r", "").split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        lines = [" "]

    inner_h = PRINT_HEIGHT - (4 if frame else 0)
    line_gap = 1

    def measure(sz):
        f = load_font(family, sz)
        boxes = [f.getbbox(l or " ") for l in lines]
        asc, desc = f.getmetrics()
        lh = asc + desc
        total_h = lh * len(lines) + line_gap * (len(lines) - 1)
        w = max(b[2] - b[0] for b in boxes)
        return f, lh, total_h, w

    if size and size > 0:
        font, lh, total_h, w = measure(size)
    else:
        size = 60
        while size > 5:
            font, lh, total_h, w = measure(size)
            # usa l'ingombro reale dell'inchiostro, non quello tipografico
            if _ink_height(lines, font, lh, line_gap) <= inner_h:
                break
            size -= 1
        font, lh, total_h, w = measure(size)

    pad = 4
    canvas_w = w + 2 * pad
    canvas_h = total_h + 2 * pad
    img = Image.new("L", (canvas_w, canvas_h), 255)
    d = ImageDraw.Draw(img)
    y = pad
    for l in lines:
        lw = font.getbbox(l or " ")[2] - font.getbbox(l or " ")[0]
        if align == "left":
            x = pad
        elif align == "right":
            x = canvas_w - pad - lw
        else:
            x = (canvas_w - lw) // 2
        d.text((x - font.getbbox(l or " ")[0], y), l, font=font, fill=0)
        y += lh + line_gap

    # ritaglia sull'inchiostro e centra verticalmente in 30 punti
    bbox = ImageChops.invert(img).getbbox()
    if bbox:
        img = img.crop((0, bbox[1], canvas_w, bbox[3]))
        # mantieni la larghezza originale (per l'allineamento) ma togli i bordi
        bx = ImageChops.invert(img).getbbox()
        if bx:
            img = img.crop((bx[0], 0, bx[2], img.height))
    if img.height > inner_h:  # non dovrebbe succedere con la misura automatica
        img = img.resize((max(1, round(img.width * inner_h / img.height)), inner_h),
                         Image.LANCZOS)

    out_w = img.width + 2 * margin + (4 if frame else 0)
    out = Image.new("L", (out_w, PRINT_HEIGHT), 255)
    oy = (PRINT_HEIGHT - img.height) // 2
    ox = margin + (2 if frame else 0)
    out.paste(img, (ox, oy))
    if frame:
        ImageDraw.Draw(out).rectangle((0, 0, out_w - 1, PRINT_HEIGHT - 1), outline=0, width=1)
    if invert:
        out = ImageOps.invert(out)
    return out


def _ink_height(lines, font, lh, gap):
    tmp_h = lh * len(lines) + gap * (len(lines) - 1) + 8
    w = max(font.getbbox(l or " ")[2] for l in lines) + 8
    img = Image.new("L", (max(1, w), tmp_h), 255)
    d = ImageDraw.Draw(img)
    y = 4
    for l in lines:
        d.text((4, y), l, font=font, fill=0)
        y += lh + gap
    b = ImageChops.invert(img).getbbox()
    return (b[3] - b[1]) if b else 0


def fit_image(src: Image.Image, trim: bool = True, margin: int = 4,
              invert: bool = False, rotate: int = 0) -> Image.Image:
    """Adatta un'immagine qualsiasi all'altezza dell'etichetta."""
    img = src
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg
    img = img.convert("L")
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=255)
    if trim:
        b =ImageChops.invert(img).point(lambda v: 255 if v > 10 else 0).getbbox()
        if b:
            img = img.crop(b)
    h = PRINT_HEIGHT
    w = max(1, round(img.width * h / img.height))
    img = img.resize((w, h), Image.LANCZOS)
    out = Image.new("L", (w + 2 * margin, h), 255)
    out.paste(img, (margin, 0))
    if invert:
        out = ImageOps.invert(out)
    return out


def load_image_file(path: str, page: int = 0, dpi: int = 300) -> Image.Image:
    """Apre PNG/JPG/BMP… oppure una pagina di un PDF (es. esportato da OpenOffice)."""
    if path.lower().endswith(".pdf"):
        try:
            import pypdfium2 as pdfium
        except ImportError:
            raise RuntimeError("Per aprire i PDF installa: pip install pypdfium2")
        pdf = pdfium.PdfDocument(path)
        try:
            page = max(0, min(page, len(pdf) - 1))
            return pdf[page].render(scale=dpi / 72).to_pil()
        finally:
            pdf.close()
    return Image.open(path)


def pdf_page_count(path: str) -> int:
    if not path.lower().endswith(".pdf"):
        return 1
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        return len(pdf)
    finally:
        pdf.close()


def to_mono(img: Image.Image, dither: bool = False, threshold: int = 128) -> Image.Image:
    """Converte in bianco/nero puro (modo '1')."""
    g = img.convert("L")
    if dither:
        return g.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    return g.point(lambda v: 255 if v >= threshold else 0).convert("1", dither=Image.Dither.NONE)


def finalize(img: Image.Image, stretch: int = 1, dither: bool = False,
             threshold: int = 128) -> Image.Image:
    """Immagine finale 1-bit, alta PRINT_HEIGHT, larghezza minima garantita."""
    if img.height != PRINT_HEIGHT:
        img = fit_image(img, trim=False, margin=0)
    if stretch > 1:
        img = img.resize((img.width * stretch, img.height), Image.NEAREST)
    if img.width < MIN_WIDTH:
        pad = Image.new("L", (MIN_WIDTH, PRINT_HEIGHT), 255)
        pad.paste(img.convert("L"), ((MIN_WIDTH - img.width) // 2, 0))
        img = pad
    if img.width > MAX_WIDTH:
        raise ValueError(f"Etichetta troppo lunga ({img.width} punti, max {MAX_WIDTH}).")
    return to_mono(img, dither, threshold)


def image_to_canvas(mono: Image.Image):
    """Immagine '1' -> Canvas della libreria dymo-bluetooth."""
    from dymo_bluetooth.printer import Canvas
    c = Canvas()
    px = mono.load()
    w, h = mono.size
    for x in range(w):
        for y in range(min(h, PRINT_HEIGHT)):
            c.set_pixel(x, y, px[x, y] == 0)
    return c


# --------------------------------------------------------------------------- #
#  Fogli di calcolo (OpenOffice Calc .ods, CSV, Excel)
# --------------------------------------------------------------------------- #

_NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


def _odf_cell_text(cell) -> str:
    parts = []
    for p in cell.findall("text:p", _NS):
        parts.append("".join(p.itertext()))
    if parts:
        return "\n".join(parts)
    return cell.get(f"{{{_NS['office']}}}value", "") or ""


def read_ods(path: str) -> List[List[str]]:
    """Legge il primo foglio di un file .ods (OpenOffice / LibreOffice Calc)."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    table = root.find(".//table:table", _NS)
    if table is None:
        return []
    rows: List[List[str]] = []
    T = _NS["table"]
    for row in table.iter(f"{{{T}}}table-row"):
        values: List[str] = []
        for cell in row:
            if cell.tag not in (f"{{{T}}}table-cell", f"{{{T}}}covered-table-cell"):
                continue
            rep = int(cell.get(f"{{{T}}}number-columns-repeated", "1"))
            txt = _odf_cell_text(cell)
            values.extend([txt] * min(rep, 200))
        while values and not values[-1].strip():
            values.pop()
        rrep = int(row.get(f"{{{T}}}number-rows-repeated", "1"))
        if not values:
            rows.extend([[]] * min(rrep, 1))  # niente migliaia di righe vuote
        else:
            rows.extend([list(values) for _ in range(min(rrep, 1000))])
    while rows and not rows[-1]:
        rows.pop()
    return rows


def read_csv(path: str) -> List[List[str]]:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(txt[:4096], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if txt.count(";") > txt.count(",") else ","
    return [r for r in csv.reader(io.StringIO(txt), dialect)]


def read_xlsx(path: str) -> List[List[str]]:
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("Per i file Excel installa: pip install openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [["" if v is None else str(v) for v in r] for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def read_sheet(path: str) -> List[List[str]]:
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("ods", "ots", "fods"):
        if ext == "fods":
            raise RuntimeError("Salva il foglio in formato .ods (non .fods).")
        return read_ods(path)
    if ext in ("csv", "txt", "tsv"):
        return read_csv(path)
    if ext in ("xlsx", "xlsm"):
        return read_xlsx(path)
    raise RuntimeError("Formato non supportato. Usa .ods, .csv o .xlsx")


# --------------------------------------------------------------------------- #
#  Bluetooth
# --------------------------------------------------------------------------- #

class PrinterNotFound(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
#  Cartelle e coda di stampa (usata dal pulsante in LibreOffice/OpenOffice)
# --------------------------------------------------------------------------- #

def base_dir() -> str:
    la = os.environ.get("LOCALAPPDATA")
    if la:
        return os.path.join(la, "EtichetteLetraTag")
    return os.path.join(os.path.expanduser("~"), ".etichette_letratag")


def queue_dir() -> str:
    return os.path.join(base_dir(), "coda")


LABEL_SEPARATOR = "@@@@"
QUEUE_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".txt")


def read_label_txt(path: str) -> List[str]:
    """File .txt scritto dalla macro: etichette separate da una riga '@@@@'."""
    raw = Path(path).read_bytes()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("cp1252", errors="replace")
    txt = txt.replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n")
    labels, cur = [], []
    for line in txt.split("\n"):
        if line.strip() == LABEL_SEPARATOR:
            labels.append("\n".join(cur))
            cur = []
        else:
            cur.append(line.rstrip())
    labels.append("\n".join(cur))
    return [l.strip("\n") for l in labels if l.strip()]


class LetraTagBLE:
    """Gestisce scansione, connessione e stampa. Tutti i metodi sono coroutine."""

    def __init__(self):
        self.client = None
        self.device = None

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def scan(self, timeout: float = 8.0):
        from bleak import BleakScanner
        from dymo_bluetooth.bluetooth import SERVICE_UUID
        found = {}
        devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
        for addr, (dev, adv) in devices.items():
            name = (dev.name or adv.local_name or "")
            uuids = [u.lower() for u in (adv.service_uuids or [])]
            if name.lower().startswith(("letratag", "dymo lt")) or SERVICE_UUID in uuids:
                found[addr] = dev
        return list(found.values())

    async def connect(self, device):
        from bleak import BleakClient
        await self.disconnect()
        self.device = device
        self.client = BleakClient(device)
        await self.client.connect(timeout=15.0)

    async def disconnect(self):
        if self.client is not None:
            try:
                if self.client.is_connected:
                    await self.client.disconnect()
            except Exception:
                pass
        self.client = None

    async def ensure_connected(self, log=None, attempts: int = 4):
        """Si collega da solo: cerca la LetraTag, si connette, riprova se serve."""
        last = None
        for i in range(attempts):
            if self.connected:
                return
            try:
                if self.device is None:
                    if log:
                        log("Cerco la LetraTag…")
                    devs = await self.scan(6.0)
                    if not devs:
                        raise RuntimeError("LetraTag non trovata")
                    self.device = devs[0]
                if log:
                    log(f"Mi collego a {self.device.name or 'LetraTag'}…")
                await self.connect(self.device)
                if log:
                    log("Collegata.")
                return
            except Exception as e:  # noqa: BLE001
                last = e
                await self.disconnect()
                self.device = None
                await asyncio.sleep(2.0)
        raise PrinterNotFound(
            "Stampante non trovata. Accendi la LetraTag, avvicinala al PC e "
            "chiudi l'app DYMO sul telefono." + (f" ({last})" if last else ""))

    async def print_canvas(self, canvas, timeout: float = 40.0) -> str:
        from dymo_bluetooth.bluetooth import PRINT_REQUEST_UUID, PRINT_REPLY_UUID
        from dymo_bluetooth.printer import command_print

        await self.ensure_connected()

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        state = {"first": True}

        def on_reply(_sender, data: bytearray):
            if len(data) < 3 or data[0] != 0x1B or data[1] != 0x52:
                return
            code = data[2]
            # la prima notifica (0/1) significa "sto stampando": la ignoriamo
            if state["first"] and code in (0, 1):
                state["first"] = False
                return
            if not fut.done():
                fut.set_result(code)

        await self.client.start_notify(PRINT_REPLY_UUID, on_reply)
        try:
            for chunk in command_print(canvas):
                await self.client.write_gatt_char(PRINT_REQUEST_UUID, bytes(chunk), response=True)
                await asyncio.sleep(0.02)
            try:
                code = await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                return "Inviata (nessuna conferma ricevuta)"
        finally:
            try:
                await self.client.stop_notify(PRINT_REPLY_UUID)
            except Exception:
                pass
        return RESULT_TEXT.get(code, f"Codice stampante {code}")


RESULT_TEXT = {
    0: "OK",
    1: "OK",
    2: "ERRORE di stampa",
    3: "OK (batteria scarica)",
    4: "Stampa annullata",
    5: "ERRORE di stampa",
    6: "ERRORE: batteria troppo scarica",
    7: "ERRORE: cassetta nastro mancante",
}


def is_error(result: str) -> bool:
    return result.startswith(("ERRORE", "Stampa annullata"))
