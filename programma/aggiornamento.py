"""
Aggiornamenti automatici da GitHub.

Sul repository c'è il file programma/versione.json con:
  {"versione": "2.0.0", "note": "...", "file": {"nome.py": "<sha256>", ...}}
L'app lo confronta con la copia locale, scarica i file cambiati, ne controlla
l'impronta SHA-256 e solo se sono tutti giusti li sostituisce.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = "giamorganti-pixel/etichette-letratag"
RAMO = "main"
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/{RAMO}/programma/"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
QUI = os.path.dirname(os.path.abspath(__file__))


def _get(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "EtichetteLetraTag", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def versione_locale() -> dict:
    try:
        with open(os.path.join(QUI, "versione.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"versione": "0.0.0", "file": {}}


def _tupla(v: str):
    out = []
    for p in str(v).split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def _ultimo_commit() -> str | None:
    """Codice dell'ultima versione pubblicata (l'API di GitHub non ha la cache di 5 minuti)."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/commits/{RAMO}",
                                     headers={"User-Agent": "EtichetteLetraTag",
                                              "Accept": "application/vnd.github.sha"})
        with urllib.request.urlopen(req, timeout=15) as r:
            sha = r.read().decode("ascii").strip()
        return sha if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha) else None
    except Exception:
        return None


def controlla() -> dict | None:
    """Restituisce il manifesto remoto se c'è una versione più nuova, altrimenti None."""
    sha = _ultimo_commit()
    base = f"https://raw.githubusercontent.com/{REPO}/{sha}/programma/" if sha else BASE_URL
    import time
    remoto = json.loads(_get(base + "versione.json?t=" + str(int(time.time()))).decode("utf-8"))
    remoto["_base"] = base  # tutti i file arrivano dalla stessa versione
    if _tupla(remoto.get("versione", "0")) > _tupla(versione_locale().get("versione", "0")):
        return remoto
    return None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(p: str) -> str | None:
    try:
        with open(p, "rb") as f:
            return _sha(f.read())
    except OSError:
        return None


def _unopkg():
    out = []
    for b in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        for prodotto in ("LibreOffice", "OpenOffice 4", "OpenOffice"):
            p = os.path.join(b, prodotto, "program", "unopkg.com")
            if b and os.path.isfile(p) and p not in out:
                out.append(p)
    return out


def office_aperto() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq soffice.bin"], capture_output=True,
                           text=True, creationflags=NO_WINDOW)
        return "soffice.bin" in r.stdout.lower()
    except Exception:
        return False


def aggiorna(remoto: dict, log=print, chiedi_chiudi_office=None) -> list[str]:
    """Scarica e installa. Restituisce l'elenco dei file cambiati."""
    voluti = remoto.get("file", {})
    da_scaricare = [n for n, h in voluti.items() if _sha_file(os.path.join(QUI, n)) != h]
    log(f"File da aggiornare: {len(da_scaricare)}")
    tmp = tempfile.mkdtemp(prefix="letratag_agg_")
    try:
        # 1. scarica tutto e verifica, senza toccare niente
        for n in da_scaricare:
            if "/" in n or "\\" in n or n.startswith("."):
                raise RuntimeError(f"Nome file non valido nel manifesto: {n}")
            data = _get(remoto.get("_base", BASE_URL) + n, timeout=60)
            if _sha(data) != voluti[n]:
                raise RuntimeError(f"Il file {n} è arrivato rovinato: riprova più tardi.")
            with open(os.path.join(tmp, n), "wb") as f:
                f.write(data)
            log(f"  scaricato {n}")
        # 2. sostituisce i file
        for n in da_scaricare:
            os.replace(os.path.join(tmp, n), os.path.join(QUI, n)) if _stesso_disco(tmp, QUI) else \
                shutil.copy2(os.path.join(tmp, n), os.path.join(QUI, n))
        # 3. librerie nuove
        if "requirements.txt" in da_scaricare:
            log("Aggiorno le librerie…")
            py = os.path.join(QUI, ".venv", "Scripts" if sys.platform == "win32" else "bin",
                              "python.exe" if sys.platform == "win32" else "python")
            if os.path.isfile(py):
                subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                                os.path.join(QUI, "requirements.txt")], creationflags=NO_WINDOW,
                               capture_output=True)
        # 4. pulsante di LibreOffice / OpenOffice
        if "StampaLetraTag.oxt" in da_scaricare and _unopkg():
            if office_aperto() and chiedi_chiudi_office:
                chiedi_chiudi_office()
            open(os.path.join(QUI, IN_SOSPESO), "w").close()
            if installa_oxt_in_sospeso():
                log("Pulsante di OpenOffice aggiornato.")
            else:
                log("OpenOffice è aperto: il pulsante si aggiorna da solo appena lo chiudi.")
        # 5. ricorda la versione installata
        with open(os.path.join(QUI, "versione.json"), "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in remoto.items() if not k.startswith("_")}, f, ensure_ascii=False, indent=1)
        return da_scaricare
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


IN_SOSPESO = ".pulsante_da_aggiornare"


def installa_oxt_in_sospeso() -> bool:
    """Reinstalla il pulsante di OpenOffice se un aggiornamento l'ha lasciato in sospeso."""
    flag = os.path.join(QUI, IN_SOSPESO)
    if not os.path.exists(flag):
        return True
    if office_aperto():
        return False
    for u in _unopkg():
        subprocess.run([u, "add", "-f", "-s", os.path.join(QUI, "StampaLetraTag.oxt")],
                       creationflags=NO_WINDOW, capture_output=True)
    try:
        os.remove(flag)
    except OSError:
        pass
    return True


def _stesso_disco(a: str, b: str) -> bool:
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def riavvia():
    """Apre una nuova copia dell'app (la vecchia si chiude subito dopo)."""
    py = os.path.join(QUI, ".venv", "Scripts", "pythonw.exe") if sys.platform == "win32" else sys.executable
    if not os.path.isfile(py):
        py = sys.executable
    kw = {"cwd": QUI}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008  # DETACHED_PROCESS
    subprocess.Popen([py, os.path.join(QUI, "etichette_letratag.py"), "--dopo-aggiornamento"], **kw)
