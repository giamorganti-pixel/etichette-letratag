"""
Prepara una nuova versione da pubblicare.

Uso:  python sviluppo/pubblica.py 2.1.0 "Cosa c'è di nuovo"
Ricostruisce il pulsante di OpenOffice, poi scrive programma/versione.json con le impronte
SHA-256 di tutti i file. Dopo basta fare commit e push: le app installate vedono
la nuova versione e la scaricano col pulsante «Aggiorna».
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(QUI, "..", "programma")

if len(sys.argv) < 2:
    sys.exit(__doc__)
versione = sys.argv[1]
note = sys.argv[2] if len(sys.argv) > 2 else ""

subprocess.run([sys.executable, os.path.join(QUI, "build_oxt.py"), QUI], check=True)
import zipfile


def _contenuto(p):
    """Contenuto dei file (non le date): se è uguale il pulsante non va reinstallato."""
    try:
        if p.endswith(".oxt"):
            with zipfile.ZipFile(p) as z:
                return sorted((i.filename, z.read(i)) for i in z.infolist())
        with open(p, "rb") as fh:
            return fh.read()
    except OSError:
        return None


for f in ("StampaLetraTag.oxt", "icona.ico", "icona.png"):
    nuovo, vecchio = os.path.join(QUI, f), os.path.join(PROG, f)
    if _contenuto(nuovo) != _contenuto(vecchio):
        shutil.copy2(nuovo, vecchio)
        print("aggiornato", f)
    os.remove(nuovo)

file = {}
for n in sorted(os.listdir(PROG)):
    p = os.path.join(PROG, n)
    if n == "versione.json" or n.startswith(".") or not os.path.isfile(p) or n.endswith(".pyc"):
        continue
    with open(p, "rb") as fh:
        file[n] = hashlib.sha256(fh.read()).hexdigest()

with open(os.path.join(PROG, "versione.json"), "w", encoding="utf-8") as fh:
    json.dump({"versione": versione, "note": note, "file": file}, fh, ensure_ascii=False, indent=1)
print(f"versione {versione}: {len(file)} file")
