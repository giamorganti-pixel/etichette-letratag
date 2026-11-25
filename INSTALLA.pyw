"""
Installazione di Etichette LetraTag (si apre con doppio clic, serve Python da python.org).
Niente .bat, niente PowerShell: solo Python e pip.
"""
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

TITOLO = "Installazione Etichette LetraTag"
QUI = os.path.dirname(os.path.abspath(__file__))
SORGENTE = os.path.join(QUI, "programma")
DEST = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EtichetteLetraTag")
FILE_APP = ["etichette_letratag.py", "letratag_core.py", "etichetta.py", "aggiornamento.py", "versione.json", "lingua.py", "requirements.txt", "StampaLetraTag.oxt",
            "icona.ico", "icona.png", "disinstalla.pyw", "LEGGIMI.txt"]
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
WIN = sys.platform == "win32"


def python_console():
    """python.exe accanto a pythonw.exe (serve per venv e pip)."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(cand):
            return cand
    return exe


def venv_python(gui=False):
    if WIN:
        return os.path.join(DEST, ".venv", "Scripts", "pythonw.exe" if gui else "python.exe")
    return os.path.join(DEST, ".venv", "bin", "python")


def cartella_desktop():
    if WIN:
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
            if buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def trova_unopkg():
    basi = [os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    trovati = []
    for b in basi:
        for prodotto in ("LibreOffice", "OpenOffice 4", "OpenOffice"):
            p = os.path.join(b, prodotto, "program", "unopkg.com")
            if os.path.isfile(p) and p not in trovati:
                trovati.append(p)
    return trovati


def office_aperto():
    if not WIN:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq soffice.bin"], capture_output=True,
                             text=True, creationflags=NO_WINDOW).stdout
        return "soffice.bin" in out.lower()
    except Exception:
        return False


LANCIATORE = '''# Doppio clic per aprire Etichette LetraTag
import os, subprocess
d = {dest!r}
subprocess.Popen([os.path.join(d, ".venv", "Scripts", "pythonw.exe"),
                  os.path.join(d, "etichette_letratag.py")], cwd=d)
'''


class Installatore:
    def __init__(self, root):
        self.root = root
        root.title(TITOLO)
        root.geometry("640x460")
        tk.Label(root, text="Etichette LetraTag", font=("Segoe UI", 18, "bold")).pack(pady=(14, 2))
        tk.Label(root, text="Premi INSTALLA e aspetta. Ci vogliono 1-3 minuti (serve internet).",
                 font=("Segoe UI", 11)).pack()
        self.bar = ttk.Progressbar(root, maximum=6, length=560)
        self.bar.pack(pady=10)
        self.log = tk.Text(root, height=14, font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, padx=12)
        self.btn = tk.Button(root, text="INSTALLA", font=("Segoe UI", 13, "bold"), bg="#facc15",
                             width=16, command=self.avvia)
        self.btn.pack(pady=10)

    def scrivi(self, msg):
        def f():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, f)

    def passo(self, n):
        self.root.after(0, lambda: self.bar.configure(value=n))

    def chiedi(self, fn, *a):
        """Mostra un messagebox dal thread principale e aspetta la risposta."""
        ev, res = threading.Event(), {}

        def f():
            res["v"] = fn(TITOLO, *a, parent=self.root)
            ev.set()
        self.root.after(0, f)
        ev.wait()
        return res["v"]

    def avvia(self):
        self.btn.configure(state="disabled", text="Attendi…")
        threading.Thread(target=self.installa, daemon=True).start()

    def esegui(self, cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                             creationflags=NO_WINDOW, cwd=DEST)
        for riga in p.stdout:
            riga = riga.rstrip()
            if riga and not riga.startswith("  "):
                self.scrivi("   " + riga[:110])
        return p.wait()

    def installa(self):
        try:
            self._installa()
        except Exception as e:  # noqa: BLE001
            self.scrivi(f"\nERRORE: {e}")
            self.chiedi(messagebox.showerror, f"Installazione non riuscita:\n{e}\n\n"
                                              "Controlla internet e riprova.")
            self.root.after(0, lambda: self.btn.configure(state="normal", text="RIPROVA"))

    def _installa(self):
        # 1. Python
        self.scrivi("1/6  Controllo Python…")
        if sys.version_info < (3, 10):
            webbrowser.open("https://www.python.org/downloads/")
            raise RuntimeError("Questo Python è troppo vecchio: serve la versione 3.10 o più recente.\n"
                               "Ho aperto la pagina per scaricarlo: installalo e poi riapri INSTALLA.pyw")
        self.scrivi(f"     Python {sys.version.split()[0]} OK")
        self.passo(1)

        # 2. File
        self.scrivi("2/6  Copio l'app…")
        if not os.path.isdir(SORGENTE):
            raise RuntimeError("Manca la cartella 'programma'. Hai estratto tutto lo ZIP?")
        os.makedirs(DEST, exist_ok=True)
        for f in FILE_APP:
            shutil.copy2(os.path.join(SORGENTE, f), os.path.join(DEST, f))
        self.passo(2)

        # 3. Librerie
        self.scrivi("3/6  Scarico le librerie (la prima volta ci mette un po')…")
        if not os.path.isfile(venv_python()):
            if self.esegui([python_console(), "-m", "venv", os.path.join(DEST, ".venv")]) != 0:
                raise RuntimeError("Impossibile creare l'ambiente Python.")
        self.esegui([venv_python(), "-m", "pip", "install", "--disable-pip-version-check",
                     "-q", "--upgrade", "pip"])
        if self.esegui([venv_python(), "-m", "pip", "install", "--disable-pip-version-check",
                        "-q", "-r", os.path.join(DEST, "requirements.txt")]) != 0:
            raise RuntimeError("Download delle librerie non riuscito.")
        if self.esegui([venv_python(), "-c",
                        "import bleak, dymo_bluetooth, PIL, pypdfium2, tkinter, qrcode, barcode"]) != 0:
            raise RuntimeError("Le librerie non funzionano.")
        self.scrivi("     OK")
        self.passo(3)

        # 4. Pulsante in LibreOffice / OpenOffice
        self.scrivi("4/6  Aggiungo il pulsante «Stampa su LetraTag» a LibreOffice/OpenOffice…")
        unopkg = trova_unopkg()
        if not unopkg:
            self.scrivi("     LibreOffice non trovato: salto questo passo.")
            if self.chiedi(messagebox.askyesno,
                           "LibreOffice non è installato.\n\nVuoi aprire il sito per scaricarlo?\n"
                           "(Dopo averlo installato, riapri questa installazione.)"):
                webbrowser.open("https://it.libreoffice.org/download/download/")
        else:
            while office_aperto():
                if not self.chiedi(messagebox.askretrycancel,
                                   "LibreOffice/OpenOffice è aperto.\n\nSalva i documenti, chiudi TUTTE "
                                   "le sue finestre (anche l'icona vicino all'orologio) e premi Riprova."):
                    break
            ok = False
            for u in unopkg:
                if self.esegui([u, "add", "-f", "-s", os.path.join(DEST, "StampaLetraTag.oxt")]) == 0:
                    ok = True
                    self.scrivi(f"     OK ({os.path.basename(os.path.dirname(os.path.dirname(u)))})")
            if not ok:
                self.scrivi("     Automatico non riuscito: apro l'estensione, premi OK in LibreOffice.")
                os.startfile(os.path.join(DEST, "StampaLetraTag.oxt"))
        self.passo(4)

        # 5. Icona sul desktop
        self.scrivi("5/6  Metto l'icona sul desktop…")
        lanc = os.path.join(cartella_desktop(), "Etichette LetraTag.pyw")
        with open(lanc, "w", encoding="utf-8") as f:
            f.write(LANCIATORE.format(dest=DEST))
        self.passo(5)

        # 6. Avvio
        self.scrivi("6/6  Apro l'app…")
        subprocess.Popen([venv_python(gui=True), os.path.join(DEST, "etichette_letratag.py")], cwd=DEST)
        self.passo(6)
        self.scrivi("\nFATTO! Accendi la LetraTag: l'app la trova da sola.")
        self.root.after(0, lambda: self.btn.configure(text="CHIUDI", state="normal",
                                                      command=self.root.destroy))
        self.chiedi(messagebox.showinfo,
                    "Installazione completata!\n\n"
                    "• Sul desktop trovi «Etichette LetraTag».\n"
                    "• In LibreOffice/OpenOffice c'è il pulsante giallo «Stampa su LetraTag».\n\n"
                    "Puoi cancellare lo ZIP e la cartella scaricata.")


if __name__ == "__main__":
    root = tk.Tk()
    Installatore(root)
    root.mainloop()
