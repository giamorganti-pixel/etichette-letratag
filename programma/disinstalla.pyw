"""Toglie Etichette LetraTag dal PC (doppio clic)."""
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

TITOLO = "Disinstalla Etichette LetraTag"
DEST = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EtichetteLetraTag")
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

root = tk.Tk()
root.withdraw()
if messagebox.askyesno(TITOLO, "Vuoi togliere Etichette LetraTag dal PC?"):
    os.chdir(os.path.expanduser("~"))
    # chiede all'app aperta di chiudersi
    try:
        open(os.path.join(DEST, "coda", ".chiudi"), "w").close()
    except OSError:
        pass
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)
        os.remove(os.path.join(buf.value, "Etichette LetraTag.pyw"))
    except Exception:
        pass
    for b in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        for prodotto in ("LibreOffice", "OpenOffice 4", "OpenOffice"):
            u = os.path.join(b, prodotto, "program", "unopkg.com")
            if b and os.path.isfile(u):
                subprocess.run([u, "remove", "it.etichette.letratag"], creationflags=NO_WINDOW)
    import time
    time.sleep(3)
    shutil.rmtree(DEST, ignore_errors=True)
    messagebox.showinfo(TITOLO, "Fatto. Se LibreOffice era aperto, il pulsante sparisce "
                                "quando lo riapri.")
