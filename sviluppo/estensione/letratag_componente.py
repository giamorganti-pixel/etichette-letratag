# -*- coding: utf-8 -*-
# Stampa su LetraTag - macro per LibreOffice e OpenOffice (Python 2.7 e 3)
#  Calc:   le celle selezionate, una riga = un'etichetta
#  Writer: il testo selezionato = un'etichetta; senza selezione ogni pagina = un'etichetta
#  Draw / Impress: ogni pagina = un'etichetta
from __future__ import unicode_literals

import io
import os
import random
import subprocess
import sys
import time
import traceback

import uno
from com.sun.star.beans import PropertyValue

TITOLO = "Stampa su LetraTag"
SEPARATORE = "@@@@"
MAX_ETICHETTE = 500


def cartella_base():
    la = os.environ.get("LOCALAPPDATA")
    if la:
        return os.path.join(la, "EtichetteLetraTag")
    return os.path.join(os.path.expanduser("~"), ".etichette_letratag")


def scrivi_log(msg):
    try:
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", "replace")
        b = cartella_base()
        if not os.path.isdir(b):
            os.makedirs(b)
        with io.open(os.path.join(b, "macro.log"), "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


_CTX = {"ctx": None, "frame": None}


def messaggio(testo, errore=False):
    try:
        ctx = _CTX["ctx"]
        smgr = ctx.ServiceManager
        toolkit = smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
        parent = _CTX["frame"].getContainerWindow()
        tipo = uno.Enum("com.sun.star.awt.MessageBoxType",
                        "ERRORBOX" if errore else "WARNINGBOX")
        box = toolkit.createMessageBox(parent, tipo, 1, TITOLO, testo)
        box.execute()
    except Exception:
        scrivi_log("messaggio: " + testo)


def supporta(obj, servizio):
    try:
        return obj.supportsService(servizio)
    except Exception:
        return False


# ------------------------------------------------------------------ Calc
def testi_da_calc(doc):
    sel = doc.getCurrentSelection()
    if sel is None:
        return []
    intervalli = []
    if supporta(sel, "com.sun.star.sheet.SheetCellRanges"):
        intervalli = [sel.getByIndex(i) for i in range(sel.getCount())]
    elif hasattr(sel, "getRangeAddress"):
        intervalli = [sel]
    etichette = []
    for rng in intervalli:
        a = rng.getRangeAddress()
        foglio = doc.getSheets().getByIndex(a.Sheet)
        cur = foglio.createCursor()
        cur.gotoEndOfUsedArea(False)
        usata = cur.getRangeAddress()
        ultima_riga = min(a.EndRow, usata.EndRow)
        ultima_col = min(a.EndColumn, usata.EndColumn)
        righe = foglio.getRows()
        for r in range(a.StartRow, ultima_riga + 1):
            if not righe.getByIndex(r).IsVisible:  # righe nascoste/filtrate
                continue
            valori = []
            for c in range(a.StartColumn, ultima_col + 1):
                v = foglio.getCellByPosition(c, r).getString().strip()
                if v:
                    valori.append(v)
            if valori:
                etichette.append("\n".join(valori))
                if len(etichette) >= MAX_ETICHETTE:
                    return etichette
    return etichette


# ---------------------------------------------------------------- Writer
def testo_selezionato_writer(doc):
    sel = doc.getCurrentSelection()
    if sel is None or not supporta(sel, "com.sun.star.text.TextRanges"):
        return ""
    parti = []
    for i in range(sel.getCount()):
        s = sel.getByIndex(i).getString()
        if s:
            parti.append(s)
    testo = "\n".join(parti)
    return testo.replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n")


# ------------------------------------------------------------------ File
def nome_file(coda):
    return os.path.join(coda, "etichetta_%s_%04d" % (time.strftime("%Y%m%d_%H%M%S"),
                                                     random.randint(0, 9999)))


def scrivi_testo(base, etichette):
    tmp = base + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(("\n%s\n" % SEPARATORE).join(etichette))
    os.rename(tmp, base + ".txt")


def esporta_pdf(doc, base, filtro):
    p = PropertyValue()
    p.Name = "FilterName"
    p.Value = filtro
    tmp = base + ".tmp"
    doc.storeToURL(uno.systemPathToFileUrl(tmp), (p,))
    os.rename(tmp, base + ".pdf")


# ------------------------------------------------------------------- App
def app_aperta(coda):
    hb = os.path.join(coda, ".app_attiva")
    try:
        return time.time() - os.path.getmtime(hb) < 8
    except OSError:
        return False


def avvia_app(base_dir, coda):
    if app_aperta(coda):
        return True  # è già aperta: stampa da sola entro un secondo
    if sys.platform.startswith("win"):
        py = os.path.join(base_dir, ".venv", "Scripts", "pythonw.exe")
    else:
        py = os.path.join(base_dir, ".venv", "bin", "python")
    script = os.path.join(base_dir, "etichette_letratag.py")
    if not (os.path.isfile(py) and os.path.isfile(script)):
        messaggio("L'app «Etichette LetraTag» non è installata.\n"
                  "Fai doppio clic su INSTALLA.pyw (una volta sola).\n\n"
                  "L'etichetta resta in attesa: verrà stampata appena apri l'app.")
        return False
    kw = {"cwd": base_dir, "close_fds": True}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_PROCESS_GROUP
    subprocess.Popen([py, script], **kw)
    return True


# --------------------------------------------------------------- Pulsante
def StampaSuLetraTag(doc):
    try:
        base_dir = cartella_base()
        coda = os.path.join(base_dir, "coda")
        if not os.path.isdir(coda):
            os.makedirs(coda)
        base = nome_file(coda)

        if supporta(doc, "com.sun.star.sheet.SpreadsheetDocument"):
            etichette = testi_da_calc(doc)
            if not etichette:
                messaggio("Seleziona le celle da stampare.\nOgni riga diventa un'etichetta.")
                return
            scrivi_testo(base, etichette)
        elif supporta(doc, "com.sun.star.text.TextDocument"):
            sel = testo_selezionato_writer(doc)
            if sel.strip():
                scrivi_testo(base, [sel.strip("\n")])
            else:
                esporta_pdf(doc, base, "writer_pdf_Export")
        elif supporta(doc, "com.sun.star.presentation.PresentationDocument"):
            esporta_pdf(doc, base, "impress_pdf_Export")
        elif supporta(doc, "com.sun.star.drawing.DrawingDocument"):
            esporta_pdf(doc, base, "draw_pdf_Export")
        else:
            messaggio("Questo tipo di documento non è supportato.")
            return
        avvia_app(base_dir, coda)
    except Exception:
        err = traceback.format_exc()
        scrivi_log(err)
        messaggio("Qualcosa è andato storto:\n%s\nRiprova; se continua, rifai INSTALLA.pyw."
                  % err.strip().splitlines()[-1], errore=True)



# --------------------------------------------------------- Componente UNO
# Il pulsante chiama l'indirizzo "it.etichette.letratag:stampa": non è una macro,
# quindi non serve Java e la sicurezza macro non lo blocca.
import unohelper
from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization, XServiceInfo

IMPL = "it.etichette.letratag.Gestore"
PROTOCOLLO = "it.etichette.letratag:"


class Gestore(unohelper.Base, XDispatchProvider, XDispatch, XInitialization, XServiceInfo):
    def __init__(self, ctx, *args):
        self.ctx = ctx
        self.frame = None

    def initialize(self, args):
        if args:
            self.frame = args[0]

    def queryDispatch(self, url, target, flags):
        if url.Protocol == PROTOCOLLO:
            return self
        return None

    def queryDispatches(self, richieste):
        return tuple(self.queryDispatch(r.FeatureURL, r.FrameName, r.SearchFlags) for r in richieste)

    def dispatch(self, url, args):
        if url.Path != "stampa":
            return
        _CTX["ctx"] = self.ctx
        _CTX["frame"] = self.frame
        try:
            doc = self.frame.getController().getModel()
        except Exception:
            scrivi_log(traceback.format_exc())
            return
        StampaSuLetraTag(doc)

    def addStatusListener(self, listener, url):
        pass

    def removeStatusListener(self, listener, url):
        pass

    def getImplementationName(self):
        return IMPL

    def supportsService(self, nome):
        return nome == "com.sun.star.frame.ProtocolHandler"

    def getSupportedServiceNames(self):
        return ("com.sun.star.frame.ProtocolHandler",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Gestore, IMPL, ("com.sun.star.frame.ProtocolHandler",))
