"""
Etichette LetraTag - app per PC per la DYMO LetraTag 200B (Bluetooth)

Avvio:  python etichette_letratag.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageOps, ImageTk

import aggiornamento as AGG
import etichetta as E
import letratag_core as core

APP_TITLE = "Etichette LetraTag 200B"
PREVIEW_SCALE = 5
TAPE_COLORS = {"Bianco": "#ffffff", "Giallo": "#ffe14d", "Trasparente": "#e9eef2",
               "Rosso": "#ff8a8a", "Verde": "#9be59b", "Blu": "#9cc8ff", "Argento": "#d9d9d9"}
FRASI = [
    ("Aperto il {data}", "Aperto il {data}"),
    ("Scade il … (tra 30 giorni)", "Scade il {data+30}"),
    ("Congelato il {data}", "❄ Congelato\n{data}"),
    ("Scatola numerata", "📦 Scatola {n}"),
    ("Fragile", "⚠ FRAGILE ⚠"),
    ("Non toccare", "⛔ Non toccare"),
    ("Proprietà di…", "Proprietà di "),
    ("Cavo / caricatore", "🔌 "),
    ("Dispensa", "🫙 "),
    ("Spezie", "🌿 "),
    ("Regalo", "🎁 Per "),
    ("Medicine", "💊 "),
]
VARIABILI = [
    ("Data di oggi", "{data}"), ("Data tra 7 giorni", "{data+7}"),
    ("Data tra 30 giorni", "{data+30}"), ("Data per esteso", "{dataesteso}"),
    ("Ora", "{ora}"), ("Giorno della settimana", "{giorno}"), ("Mese", "{mese}"),
    ("Anno", "{anno}"), ("Numero progressivo", "{n}"),
]


class AsyncRunner:
    """Esegue le coroutine Bluetooth in un thread separato (la GUI resta reattiva)."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro, on_done=None, on_error=None):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def _cb(f):
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                err = e
                self.root.after(0, lambda: (on_error or (lambda x: None))(err))
                return
            self.root.after(0, lambda: (on_done or (lambda x: None))(res))

        fut.add_done_callback(_cb)
        return fut


# =============================================================================
class EmojiPicker(tk.Toplevel):
    """Finestra con emoji e simboli divisi per categoria."""

    def __init__(self, app: "App"):
        super().__init__(app.root)
        self.app = app
        self.title("Emoji e simboli")
        self.geometry("560x420")
        self.transient(app.root)
        self.photos = []
        ttk.Label(self, text="Clicca per inserire nel testo. Puoi anche scriverle con Win + . (punto)").pack(
            anchor="w", padx=8, pady=(6, 2))
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.frames = {}
        for cat in E.EMOJI_CATEGORIES:
            fr = ttk.Frame(self.nb)
            self.nb.add(fr, text=cat)
            self.frames[str(fr)] = (cat, fr, False)
        self.nb.bind("<<NotebookTabChanged>>", self._fill)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(50, self._fill)

    def _close(self):
        self.app.picker = None
        self.destroy()

    def _fill(self, _e=None):
        key = self.nb.select()
        if key not in self.frames:
            return
        cat, fr, done = self.frames[key]
        if done:
            return
        self.frames[key] = (cat, fr, True)
        canvas = tk.Canvas(fr, highlightthickness=0)
        sb = ttk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        chars = list(E.split_runs(E.EMOJI_CATEGORIES[cat]))
        clusters = []
        for kind, txt in chars:
            clusters.extend(list(txt) if kind == "text" else [txt])
        for i, ch in enumerate(clusters):
            img = E.emoji_preview(ch, 26)
            ph = ImageTk.PhotoImage(img)
            self.photos.append(ph)
            b = tk.Button(inner, image=ph, relief="flat", bd=1, bg="white", activebackground="#ffe14d",
                          command=lambda c=ch: self.app.insert_text(c))
            b.grid(row=i // 14, column=i % 14, padx=1, pady=1)


# =============================================================================
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{APP_TITLE}  —  versione {AGG.versione_locale().get('versione', '?')}")
        root.geometry("1120x860")
        root.minsize(900, 700)

        self.runner = AsyncRunner(root)
        self.ble = core.LetraTagBLE()
        self.devices = []
        self.busy = False
        self.image_path: str | None = None
        self.image_cache: tuple | None = None
        self._preview_job = None
        self._preview_photo = None
        self.preview_index = 0
        self.picker: EmojiPicker | None = None
        self.retry_at = 0.0
        self.qdir = core.queue_dir()
        for sub in ("", "stampati", "errori"):
            os.makedirs(os.path.join(self.qdir, sub), exist_ok=True)
        self.saved = self._load_json("preferiti.json", [])
        self.history = self._load_json("cronologia.json", [])

        self._build_ui()
        self._load_settings()
        self.active_text = self.txt_input
        self._schedule_preview()
        self._heartbeat()
        self.root.after(1500, self._watch_tick)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        if "--minimizzata" in sys.argv:
            root.iconify()
        self.root.after(500, self.auto_connect)
        threading.Thread(target=self._scan_fonts, daemon=True).start()
        self.remote_update = None
        self.updating = False
        self.root.after(4000, lambda: self.check_updates(silent=True))
        self.root.after(3000, self._pending_button)

    # ============================================================ utilità
    def _load_json(self, name, default):
        try:
            with open(os.path.join(core.base_dir(), name), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, name, data):
        try:
            with open(os.path.join(core.base_dir(), name), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except Exception as e:  # noqa: BLE001
            self.log(f"Impossibile salvare {name}: {e}")

    def log(self, msg: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", time.strftime("%H:%M:%S  ") + msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    @staticmethod
    def _int(var, default=0):
        try:
            return int(float(var.get()))
        except (tk.TclError, ValueError):
            return default

    @staticmethod
    def _float(var, default=0.0):
        try:
            return float(str(var.get()).replace(",", "."))
        except (tk.TclError, ValueError):
            return default

    def banner(self, text: str, kind: str = "info"):
        colors = {"ok": ("#e6f6e6", "#065f06"), "info": ("#eef3fb", "#1d3f72"),
                  "warn": ("#fff4d6", "#7a4b00"), "err": ("#fde8e8", "#9b1111")}
        bg, fg = colors.get(kind, colors["info"])
        self.lbl_banner.configure(text=text, background=bg, foreground=fg)

    def show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(800, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    # ======================================================= aggiornamenti
    def check_updates(self, silent=False, then=None):
        def work():
            try:
                res, err = AGG.controlla(), None
            except Exception as e:  # noqa: BLE001
                res, err = None, e
            self.root.after(0, lambda: done(res, err))

        def done(res, err):
            if err is not None:
                if not silent:
                    messagebox.showwarning(APP_TITLE, f"Non riesco a controllare gli aggiornamenti.\n"
                                                      f"Sei collegato a internet?\n\n{err}")
                return
            self.remote_update = res
            if res:
                v = res.get("versione", "?")
                self.btn_update.configure(text=f"🔔 Aggiorna alla {v}")
                if silent and not self.busy:
                    self.banner(f"🔔 È disponibile la versione {v}: premi «Aggiorna» in alto a destra.", "info")
            elif not silent:
                messagebox.showinfo(APP_TITLE, "Hai già l'ultima versione "
                                    f"({AGG.versione_locale().get('versione', '?')}).")
            if then:
                then()

        threading.Thread(target=work, daemon=True).start()

    def update_clicked(self):
        if self.busy or self.updating:
            messagebox.showinfo(APP_TITLE, "Aspetta che finisca la stampa, poi riprova.")
            return
        if not self.remote_update:
            self.check_updates(silent=False, then=lambda: self.remote_update and self.update_clicked())
            return
        r = self.remote_update
        note = r.get("note", "").strip()
        if not messagebox.askyesno(APP_TITLE, f"Aggiornare alla versione {r.get('versione')}?\n\n"
                                   + (f"Novità:\n{note}\n\n" if note else "")
                                   + "L'app si riavvia da sola alla fine."):
            return
        self.updating = True
        self.btn_update.configure(state="disabled", text="Aggiorno…")
        self.btn_print.configure(state="disabled")
        self.banner("⬇ Scarico l'aggiornamento…", "info")

        def chiudi_office():
            ev = threading.Event()

            def ask():
                messagebox.showinfo(APP_TITLE, "Per aggiornare anche il pulsante di OpenOffice, chiudi "
                                    "OpenOffice/LibreOffice (tutte le finestre) e premi OK.")
                ev.set()
            self.root.after(0, ask)
            ev.wait()

        def work():
            try:
                AGG.aggiorna(r, log=lambda m: self.root.after(0, lambda: self.log(m)),
                             chiedi_chiudi_office=chiudi_office)
                self.root.after(0, finished)
            except Exception as e:  # noqa: BLE001
                err = e
                self.root.after(0, lambda: failed(err))

        def finished():
            self.banner("✅ Aggiornata! Riavvio l'app…", "ok")
            self._save_settings()
            try:
                os.remove(os.path.join(self.qdir, HEARTBEAT))
            except OSError:
                pass
            try:
                AGG.riavvia()
            except Exception as e:  # noqa: BLE001
                messagebox.showinfo(APP_TITLE, f"Aggiornata. Riaprila dall'icona sul desktop.\n({e})")
            try:
                self.runner.submit(self.ble.disconnect()).result(timeout=3)
            except Exception:
                pass
            self.root.after(300, self.root.destroy)

        def failed(e):
            self.updating = False
            self.btn_update.configure(state="normal", text="🔄 Aggiorna")
            self.btn_print.configure(state="normal")
            self.banner(f"⚠ Aggiornamento non riuscito: {e}", "err")
            self.log(f"Aggiornamento non riuscito: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _pending_button(self):
        """Se un aggiornamento ha lasciato il pulsante di OpenOffice in sospeso, riprova."""
        if os.path.exists(os.path.join(AGG.QUI, AGG.IN_SOSPESO)):
            def work():
                if AGG.installa_oxt_in_sospeso():
                    self.root.after(0, lambda: self.log("Pulsante di OpenOffice aggiornato."))
            threading.Thread(target=work, daemon=True).start()
            self.root.after(60000, self._pending_button)

    # ============================================================== font
    def _scan_fonts(self):
        try:
            reg = E.scan_system_fonts(os.path.join(core.base_dir(), "caratteri.json"))
        except Exception:
            reg = {}
        self.root.after(0, lambda: self._fonts_ready(reg))

    def _fonts_ready(self, reg):
        E.set_registry(reg)
        self.all_fonts = E.font_names()
        self.cmb_font.configure(values=self.all_fonts)
        self.log(f"Caratteri disponibili: {len(self.all_fonts)}")
        self._schedule_preview()

    def _filter_fonts(self, _e=None):
        q = self.var_font.get().lower().strip()
        vals = [f for f in getattr(self, "all_fonts", E.font_names()) if q in f.lower()] if q else \
            getattr(self, "all_fonts", E.font_names())
        self.cmb_font.configure(values=vals[:400])

    # ================================================================ UI
    def _build_ui(self):
        pad = {"padx": 6, "pady": 3}
        self.lbl_banner = tk.Label(self.root, text="", font=("Segoe UI", 12, "bold"),
                                   anchor="w", padx=12, pady=8, justify="left")
        self.lbl_banner.pack(fill="x", padx=6, pady=(6, 0))
        self.root.bind("<Configure>", lambda e: self.lbl_banner.configure(
            wraplength=max(300, self.root.winfo_width() - 40)))

        top = ttk.LabelFrame(self.root, text="Stampante")
        top.pack(fill="x", **pad)
        self.btn_scan = ttk.Button(top, text="🔍 Cerca", command=self.scan)
        self.btn_scan.pack(side="left", **pad)
        self.cmb_dev = ttk.Combobox(top, state="readonly", width=34)
        self.cmb_dev.pack(side="left", **pad)
        self.btn_conn = ttk.Button(top, text="Connetti", command=self.toggle_connect)
        self.btn_conn.pack(side="left", **pad)
        self.lbl_status = ttk.Label(top, text="● Non collegata", foreground="#b00")
        self.lbl_status.pack(side="left", **pad)
        self.btn_update = ttk.Button(top, text="🔄 Aggiorna", command=self.update_clicked)
        self.btn_update.pack(side="right", **pad)
        self.lbl_version = ttk.Label(top, text=f"versione {AGG.versione_locale().get('versione', '?')}",
                                     foreground="#666")
        self.lbl_version.pack(side="right", **pad)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, **pad)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: (setattr(self, "preview_index", 0),
                                                          self._schedule_preview()))
        self._tab_text()
        self._tab_list()
        self._tab_codes()
        self._tab_file()
        self._tab_saved()
        self._tab_settings()

        self._style_panel()
        self._print_panel()

        pv = ttk.LabelFrame(self.root, text="Anteprima")
        pv.pack(fill="x", **pad)
        row = ttk.Frame(pv)
        row.pack(fill="x")
        self.btn_prev = ttk.Button(row, text="◀", width=3, command=lambda: self._step_preview(-1))
        self.btn_prev.pack(side="left", padx=4)
        self.lbl_pv = ttk.Label(row, text="")
        self.lbl_pv.pack(side="left")
        self.btn_next = ttk.Button(row, text="▶", width=3, command=lambda: self._step_preview(1))
        self.btn_next.pack(side="left", padx=4)
        ttk.Label(row, text="   Colore nastro (solo anteprima)").pack(side="left")
        self.var_tape = tk.StringVar(value="Bianco")
        ttk.Combobox(row, textvariable=self.var_tape, values=list(TAPE_COLORS), width=11,
                     state="readonly").pack(side="left", padx=4)
        self.var_tape.trace_add("write", lambda *a: self._schedule_preview())
        self.pv_canvas = tk.Canvas(pv, height=PREVIEW_SCALE * E.H + 26, bg="#e8e8e8", highlightthickness=0)
        hs = ttk.Scrollbar(pv, orient="horizontal", command=self.pv_canvas.xview)
        self.pv_canvas.configure(xscrollcommand=hs.set)
        self.pv_canvas.pack(fill="x", padx=6, pady=(4, 0))
        hs.pack(fill="x", padx=6, pady=(0, 4))

        self.txt_log = tk.Text(self.root, height=3, state="disabled", bg="#fafafa", font=("Consolas", 9))
        self.txt_log.pack(fill="x", **pad)
        self.log("Pronto. Accendi la LetraTag: l'app la cerca da sola.")

    # ---------------------------------------------------- barra comune
    def _text_tools(self, parent, text_widget_getter, extra=None):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Button(bar, text="😀 Emoji e simboli", command=self.open_picker).pack(side="left")
        mb = ttk.Menubutton(bar, text="📅 Inserisci")
        menu = tk.Menu(mb, tearoff=0)
        for label, val in VARIABILI:
            menu.add_command(label=f"{label}   {val}", command=lambda v=val: self.insert_text(v))
        menu.add_separator()
        sub = tk.Menu(menu, tearoff=0)
        for label, val in FRASI:
            sub.add_command(label=label, command=lambda v=val: self.insert_text(v))
        menu.add_cascade(label="Frasi pronte", menu=sub)
        mb["menu"] = menu
        mb.pack(side="left", padx=6)
        ttk.Button(bar, text="🧹 Pulisci", command=lambda: (text_widget_getter().delete("1.0", "end"),
                                                          self._schedule_preview())).pack(side="left")
        if extra:
            extra(bar)
        return bar

    def _tab_text(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  ✏️ Testo  ")
        self._text_tools(f, lambda: self.txt_input, extra=lambda bar: ttk.Button(
            bar, text="⭐ Salva nei preferiti", command=self.save_favorite).pack(side="right"))
        self.txt_input = tk.Text(f, height=3, font=("Segoe UI", 15), undo=True, wrap="none")
        self.txt_input.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt_input.insert("1.0", "LETRATAG")
        self.txt_input.bind("<<Modified>>", lambda e: self._on_mod(self.txt_input))
        self.txt_input.bind("<FocusIn>", lambda e: setattr(self, "active_text", self.txt_input))
        ttk.Label(f, foreground="#555", text="Invio = nuova riga (max 2-3 righe). Le parti tra { } "
                  "vengono riempite in stampa: {data}, {n}…").pack(anchor="w", padx=8, pady=(0, 4))

    def _on_mod(self, w):
        if w.edit_modified():
            w.edit_modified(False)
            self._schedule_preview()

    def _tab_list(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  📋 Elenco  ")

        def extra(bar):
            ttk.Button(bar, text="📂 Importa da Calc/Excel/CSV…", command=self.import_list).pack(side="left", padx=6)
            ttk.Button(bar, text="📋 Incolla", command=self.paste_list).pack(side="left")
        self._text_tools(f, lambda: self.txt_list, extra)
        self.txt_list = tk.Text(f, height=5, font=("Segoe UI", 12), undo=True, wrap="none")
        self.txt_list.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt_list.insert("1.0", "🍝 Pasta\n🍚 Riso\n🧂 Sale | {data}")
        self.txt_list.bind("<<Modified>>", lambda e: self._on_mod(self.txt_list))
        self.txt_list.bind("<FocusIn>", lambda e: setattr(self, "active_text", self.txt_list))
        self.lbl_list = ttk.Label(f, foreground="#555", text="")
        self.lbl_list.pack(anchor="w", padx=8, pady=(0, 4))

    def _tab_codes(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  ▦ QR e codici a barre  ")
        g = ttk.Frame(f)
        g.pack(fill="x", padx=8, pady=8)
        ttk.Label(g, text="Tipo").grid(row=0, column=0, sticky="w")
        self.var_code = tk.StringVar(value="QR code")
        ttk.Combobox(g, textvariable=self.var_code, values=E.CODE_TYPES, state="readonly",
                     width=12).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(g, text="Barre larghe").grid(row=0, column=2, sticky="e")
        self.var_module = tk.IntVar(value=2)
        ttk.Spinbox(g, from_=1, to=4, width=3, textvariable=self.var_module).grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(g, text="Contenuto").grid(row=1, column=0, sticky="w", pady=4)
        self.var_code_data = tk.StringVar(value="https://www.dymo.com")
        ttk.Entry(g, textvariable=self.var_code_data, width=60).grid(row=1, column=1, columnspan=3, sticky="we", padx=6)
        ttk.Label(g, text="Testo accanto").grid(row=2, column=0, sticky="w")
        self.var_code_text = tk.StringVar(value="Sito DYMO")
        ttk.Entry(g, textvariable=self.var_code_text, width=60).grid(row=2, column=1, columnspan=3, sticky="we", padx=6)
        ttk.Label(f, foreground="#555", justify="left", text=(
            "Il nastro è alto 30 punti: il QR esce piccolo (circa 4 mm) e va bene solo per testi brevi "
            "(max ~25 caratteri). Prova a leggerlo col telefono prima di stamparne tanti.\n"
            "Code128 = lettere e numeri; EAN-13 = 12 cifre (la tredicesima la calcola da solo).")
        ).pack(anchor="w", padx=8)
        for v in (self.var_code, self.var_module, self.var_code_data, self.var_code_text):
            v.trace_add("write", lambda *a: self._schedule_preview())

    def _tab_file(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  🖼 Immagine / PDF  ")
        row = ttk.Frame(f)
        row.pack(fill="x", padx=8, pady=8)
        ttk.Button(row, text="📂 Apri PDF o immagine…", command=self.open_image).pack(side="left")
        ttk.Label(row, text="Pagina").pack(side="left", padx=(12, 2))
        self.var_page = tk.IntVar(value=1)
        self.spn_page = ttk.Spinbox(row, from_=1, to=1, width=4, textvariable=self.var_page)
        self.spn_page.pack(side="left")
        ttk.Label(row, text="Ruota").pack(side="left", padx=(12, 2))
        self.var_rot = tk.StringVar(value="0")
        ttk.Combobox(row, textvariable=self.var_rot, state="readonly", width=4,
                     values=["0", "90", "180", "270"]).pack(side="left")
        self.var_dither = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Retinatura (foto)", variable=self.var_dither).pack(side="left", padx=10)
        ttk.Label(row, text="Soglia").pack(side="left")
        self.var_thr = tk.IntVar(value=160)
        ttk.Scale(row, from_=40, to=230, variable=self.var_thr, length=120,
                  command=lambda e: self._schedule_preview()).pack(side="left")
        self.lbl_file = ttk.Label(f, text="Loghi, disegni, foto o un PDF: vengono adattati all'altezza del nastro.")
        self.lbl_file.pack(anchor="w", padx=8)
        for v in (self.var_page, self.var_rot, self.var_dither):
            v.trace_add("write", lambda *a: self._schedule_preview())

    def _tab_saved(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  ⭐ Salvate  ")
        cols = ttk.Frame(f)
        cols.pack(fill="both", expand=True, padx=8, pady=6)
        for i, (title, attr) in enumerate((("⭐ Preferiti", "lst_fav"), ("🕘 Ultime stampate", "lst_hist"))):
            fr = ttk.LabelFrame(cols, text=title)
            fr.grid(row=0, column=i, sticky="nsew", padx=4)
            cols.columnconfigure(i, weight=1)
            lb = tk.Listbox(fr, height=6, font=("Segoe UI", 11), activestyle="none")
            lb.pack(fill="both", expand=True, padx=4, pady=4)
            setattr(self, attr, lb)
            bb = ttk.Frame(fr)
            bb.pack(fill="x", padx=4, pady=(0, 4))
            src = "fav" if i == 0 else "hist"
            ttk.Button(bb, text="Apri", command=lambda s=src: self.load_saved(s)).pack(side="left")
            ttk.Button(bb, text="🖨 Stampa", command=lambda s=src: self.load_saved(s, stampa=True)).pack(side="left", padx=4)
            ttk.Button(bb, text="🗑 Elimina", command=lambda s=src: self.delete_saved(s)).pack(side="left")
            lb.bind("<Double-Button-1>", lambda e, s=src: self.load_saved(s))
        cols.rowconfigure(0, weight=1)
        self._refresh_saved()

    def _tab_settings(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  ⚙ Impostazioni  ")
        g = ttk.Frame(f)
        g.pack(fill="x", padx=10, pady=10)
        ttk.Label(g, text="Punti per millimetro (calibrazione lunghezza)").grid(row=0, column=0, sticky="w")
        self.var_dots = tk.StringVar(value="7.87")
        ttk.Entry(g, textvariable=self.var_dots, width=7).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(g, text="Calibra…", command=self.calibrate).grid(row=0, column=2, sticky="w")
        ttk.Label(g, foreground="#555", text="Stampa un'etichetta, misurala col righello e premi Calibra: "
                  "le lunghezze in mm diventano precise.").grid(row=1, column=0, columnspan=4, sticky="w")
        ttk.Separator(f).pack(fill="x", padx=10, pady=6)
        ttk.Label(f, justify="left", text=(
            "LibreOffice / OpenOffice: il pulsante giallo «Stampa su LetraTag» manda all'app le celle o il testo "
            "selezionati,\ne li stampa con lo stile scelto qui.")).pack(anchor="w", padx=10)
        ttk.Button(f, text="Apri cartella dei dati", command=lambda: self._open_folder(core.base_dir())).pack(
            anchor="w", padx=10, pady=6)
        ttk.Separator(f).pack(fill="x", padx=10, pady=6)
        v = AGG.versione_locale()
        ttk.Label(f, text=f"Versione installata: {v.get('versione', '?')}   ·   aggiornamenti da "
                  f"github.com/{AGG.REPO}").pack(anchor="w", padx=10)
        if v.get("note"):
            ttk.Label(f, foreground="#555", justify="left", text="Novità di questa versione:\n" + v["note"]).pack(
                anchor="w", padx=10, pady=4)
        ttk.Button(f, text="🔄 Controlla aggiornamenti", command=self.update_clicked).pack(anchor="w", padx=10, pady=4)
        self.var_dots.trace_add("write", lambda *a: self._schedule_preview())

    # ----------------------------------------------------------- stile
    def _style_panel(self):
        st = ttk.LabelFrame(self.root, text="Stile")
        st.pack(fill="x", padx=6, pady=3)
        r1 = ttk.Frame(st)
        r1.pack(fill="x", padx=4, pady=2)
        ttk.Label(r1, text="Stile rapido").pack(side="left")
        self.var_quick = tk.StringVar(value="")
        cq = ttk.Combobox(r1, textvariable=self.var_quick, values=list(E.QUICK_STYLES), state="readonly", width=24)
        cq.pack(side="left", padx=(4, 12))
        cq.bind("<<ComboboxSelected>>", lambda e: self.apply_quick())
        ttk.Label(r1, text="Carattere").pack(side="left")
        self.var_font = tk.StringVar(value="Sans grassetto")
        self.cmb_font = ttk.Combobox(r1, textvariable=self.var_font, values=E.font_names(), width=30)
        self.cmb_font.pack(side="left", padx=(4, 12))
        self.cmb_font.bind("<KeyRelease>", self._filter_fonts)
        ttk.Label(r1, text="Dimensione (0 = automatica)").pack(side="left")
        self.var_size = tk.IntVar(value=0)
        ttk.Spinbox(r1, from_=0, to=80, width=4, textvariable=self.var_size).pack(side="left", padx=(4, 12))
        ttk.Label(r1, text="Allinea").pack(side="left")
        self.var_align = tk.StringVar(value="Centro")
        ttk.Combobox(r1, textvariable=self.var_align, values=E.ALIGNS, state="readonly", width=8).pack(side="left", padx=4)

        r2 = ttk.Frame(st)
        r2.pack(fill="x", padx=4, pady=2)
        self.var_italic = tk.BooleanVar()
        self.var_underline = tk.BooleanVar()
        self.var_strike = tk.BooleanVar()
        self.var_outline = tk.BooleanVar()
        self.var_invert = tk.BooleanVar()
        for txt, v in (("Corsivo", self.var_italic), ("Sottolineato", self.var_underline),
                       ("Barrato", self.var_strike), ("Solo contorno", self.var_outline),
                       ("Bianco su nero", self.var_invert)):
            ttk.Checkbutton(r2, text=txt, variable=v).pack(side="left", padx=(0, 10))
        ttk.Label(r2, text="Spazio lettere").pack(side="left")
        self.var_spacing = tk.IntVar(value=0)
        ttk.Spinbox(r2, from_=-3, to=15, width=4, textvariable=self.var_spacing).pack(side="left", padx=(4, 10))
        ttk.Label(r2, text="Interlinea").pack(side="left")
        self.var_linegap = tk.IntVar(value=1)
        ttk.Spinbox(r2, from_=-2, to=8, width=4, textvariable=self.var_linegap).pack(side="left", padx=4)

        r3 = ttk.Frame(st)
        r3.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Label(r3, text="Cornice").pack(side="left")
        self.var_frame = tk.StringVar(value="Nessuna")
        ttk.Combobox(r3, textvariable=self.var_frame, values=E.FRAMES, state="readonly", width=12).pack(side="left", padx=(4, 10))
        ttk.Label(r3, text="Emoji").pack(side="left")
        self.var_emoji = tk.StringVar(value="Dettagliate")
        ttk.Combobox(r3, textvariable=self.var_emoji, values=E.EMOJI_MODES, state="readonly", width=14).pack(side="left", padx=(4, 10))
        ttk.Label(r3, text="Margini").pack(side="left")
        self.var_margin = tk.IntVar(value=8)
        ttk.Spinbox(r3, from_=0, to=200, width=4, textvariable=self.var_margin).pack(side="left", padx=(4, 10))
        ttk.Label(r3, text="Ripeti (cavi)").pack(side="left")
        self.var_repeat = tk.IntVar(value=1)
        ttk.Spinbox(r3, from_=1, to=10, width=3, textvariable=self.var_repeat).pack(side="left", padx=(4, 10))
        ttk.Label(r3, text="Lunghezza fissa mm (0 = auto)").pack(side="left")
        self.var_length = tk.StringVar(value="0")
        ttk.Spinbox(r3, from_=0, to=500, width=5, textvariable=self.var_length).pack(side="left", padx=(4, 10))
        ttk.Label(r3, text="Allarga").pack(side="left")
        self.var_stretch = tk.IntVar(value=1)
        ttk.Spinbox(r3, from_=1, to=4, width=3, textvariable=self.var_stretch).pack(side="left", padx=4)

        for v in (self.var_font, self.var_size, self.var_align, self.var_italic, self.var_underline,
                  self.var_strike, self.var_outline, self.var_invert, self.var_spacing, self.var_linegap,
                  self.var_frame, self.var_emoji, self.var_margin, self.var_repeat, self.var_length,
                  self.var_stretch):
            v.trace_add("write", lambda *a: self._schedule_preview())

    def _print_panel(self):
        op = ttk.Frame(self.root)
        op.pack(fill="x", padx=6, pady=3)
        ttk.Label(op, text="Copie").pack(side="left")
        self.var_copies = tk.IntVar(value=1)
        ttk.Spinbox(op, from_=1, to=99, width=4, textvariable=self.var_copies).pack(side="left", padx=(4, 14))
        ttk.Label(op, text="Numero {n}: parti da").pack(side="left")
        self.var_n_start = tk.IntVar(value=1)
        ttk.Spinbox(op, from_=0, to=99999, width=6, textvariable=self.var_n_start).pack(side="left", padx=4)
        ttk.Label(op, text="passo").pack(side="left")
        self.var_n_step = tk.IntVar(value=1)
        ttk.Spinbox(op, from_=1, to=100, width=4, textvariable=self.var_n_step).pack(side="left", padx=4)
        ttk.Label(op, text="cifre").pack(side="left")
        self.var_n_digits = tk.IntVar(value=0)
        ttk.Spinbox(op, from_=0, to=6, width=3, textvariable=self.var_n_digits).pack(side="left", padx=4)
        style = ttk.Style()
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=(18, 6))
        self.btn_print = ttk.Button(op, text="🖨  STAMPA", style="Big.TButton", command=self.print_current)
        self.btn_print.pack(side="right")
        self.lbl_len = ttk.Label(op, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_len.pack(side="right", padx=12)
        for v in (self.var_n_start, self.var_n_digits):
            v.trace_add("write", lambda *a: self._schedule_preview())

    # ================================================== stile <-> dict
    def style(self) -> dict:
        return {
            "font": self.var_font.get() or "Sans grassetto", "size": self._int(self.var_size),
            "align": self.var_align.get(), "italic": self.var_italic.get(),
            "underline": self.var_underline.get(), "strike": self.var_strike.get(),
            "outline": self.var_outline.get(), "spacing": self._int(self.var_spacing),
            "line_gap": self._int(self.var_linegap, 1), "frame": self.var_frame.get(),
            "margin": self._int(self.var_margin, 8), "emoji": self.var_emoji.get(),
            "repeat": max(1, self._int(self.var_repeat, 1)), "length_mm": self._float(self.var_length),
            "dots_mm": self._float(self.var_dots, 7.87) or 7.87, "invert": self.var_invert.get(),
            "stretch": max(1, self._int(self.var_stretch, 1)),
        }

    def set_style(self, s: dict):
        m = {"font": self.var_font, "size": self.var_size, "align": self.var_align,
             "italic": self.var_italic, "underline": self.var_underline, "strike": self.var_strike,
             "outline": self.var_outline, "spacing": self.var_spacing, "line_gap": self.var_linegap,
             "frame": self.var_frame, "margin": self.var_margin, "emoji": self.var_emoji,
             "repeat": self.var_repeat, "length_mm": self.var_length, "invert": self.var_invert,
             "stretch": self.var_stretch}
        for k, var in m.items():
            if k in s:
                try:
                    var.set(s[k])
                except tk.TclError:
                    pass

    def apply_quick(self):
        self.set_style(E.apply_quick_style(self.var_quick.get(), self.style()))

    # ======================================================= inserimento
    def insert_text(self, s: str):
        w = self.active_text
        tab = self.nb.index(self.nb.select())
        if tab not in (0, 1):
            self.nb.select(0)
            w = self.txt_input
        w.insert("insert", s)
        w.focus_set()
        self._schedule_preview()

    def open_picker(self):
        if self.picker is not None:
            self.picker.lift()
            return
        self.picker = EmojiPicker(self)

    # =========================================================== elenco
    def list_items(self) -> list[str]:
        out = []
        for line in self.txt_list.get("1.0", "end").splitlines():
            if line.strip():
                out.append("\n".join(p.strip() for p in line.split("|")))
        return out

    def import_list(self):
        p = filedialog.askopenfilename(title="Importa elenco", filetypes=[
            ("Fogli di calcolo", "*.ods *.csv *.xlsx *.txt"), ("Tutti", "*.*")])
        if not p:
            return
        try:
            rows = core.read_sheet(p)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Impossibile leggere il file:\n{e}")
            return
        lines = [" | ".join(c.strip() for c in r if c.strip()) for r in rows]
        lines = [l for l in lines if l]
        if lines and messagebox.askyesno(APP_TITLE, f"La prima riga è un'intestazione?\n\n«{lines[0]}»"):
            lines = lines[1:]
        self.txt_list.delete("1.0", "end")
        self.txt_list.insert("1.0", "\n".join(lines))
        self.log(f"Importate {len(lines)} etichette da {os.path.basename(p)}")
        self._schedule_preview()

    def paste_list(self):
        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            return
        lines = [" | ".join(c.strip() for c in l.split("\t") if c.strip()) for l in clip.splitlines()]
        self.txt_list.insert("end", ("\n" if self.txt_list.get("1.0", "end").strip() else "") +
                             "\n".join(l for l in lines if l))
        self._schedule_preview()

    # ========================================================= immagini
    def open_image(self):
        p = filedialog.askopenfilename(title="Apri PDF o immagine", filetypes=[
            ("PDF e immagini", "*.pdf *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"), ("Tutti", "*.*")])
        if not p:
            return
        self.image_path, self.image_cache = p, None
        try:
            n = core.pdf_page_count(p)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, str(e))
            return
        self.spn_page.configure(to=n)
        self.var_page.set(1)
        self.lbl_file.configure(text=f"{os.path.basename(p)}  ({n} pag.)")
        self._schedule_preview()

    def _source_image(self, path, page):
        key = (path, page, os.path.getmtime(path))
        if not self.image_cache or self.image_cache[0] != key:
            self.image_cache = (key, core.load_image_file(path, page))
        return self.image_cache[1]

    # ======================================================== costruzione
    def _mono(self, img, dither=False, thr=128):
        return core.finalize(img, stretch=max(1, self._int(self.var_stretch, 1)), dither=dither, threshold=thr)

    def render_text_label(self, text: str, n: int = 1) -> Image.Image:
        txt = E.expand(text, n=n, digits=self._int(self.var_n_digits))
        return self._mono(E.render_text(txt, self.style()))

    def _counter(self, i: int) -> int:
        return self._int(self.var_n_start, 1) + i * max(1, self._int(self.var_n_step, 1))

    def build_jobs(self, preview=False):
        """Restituisce (lista immagini da stampare, totale etichette, descrizione per la cronologia)."""
        tab = self.nb.index(self.nb.select())
        copies = 1 if preview else max(1, self._int(self.var_copies, 1))
        if tab in (0, 4, 5):  # testo (anche da Salvate/Impostazioni l'anteprima mostra il testo)
            text = self.txt_input.get("1.0", "end").rstrip("\n")
            if not text.strip():
                return [], 0, None
            if E.has_counter(text):
                imgs = [self.render_text_label(text, self._counter(i)) for i in range(copies)]
            else:
                one = self.render_text_label(text, self._counter(0))
                imgs = [one] * copies
            return imgs, len(imgs), {"tipo": "testo", "testo": text}
        if tab == 1:
            items = self.list_items()
            self.lbl_list.configure(text=f"{len(items)} etichette · una per riga · usa  |  per andare a capo "
                                         "(es. «Sale | {data}»)")
            if not items:
                return [], 0, None
            if preview:
                i = max(0, min(self.preview_index, len(items) - 1))
                self.preview_index = i
                return [self.render_text_label(items[i], self._counter(i))], len(items), None
            imgs = []
            for i, t in enumerate(items):
                im = self.render_text_label(t, self._counter(i))
                imgs.extend([im] * copies)
            return imgs, len(imgs), {"tipo": "elenco", "testo": self.txt_list.get("1.0", "end").strip()}
        if tab == 2:
            data, side = self.var_code_data.get(), self.var_code_text.get()
            imgs = []
            loops = copies if (E.has_counter(data) or E.has_counter(side)) else 1
            for i in range(loops):
                n = self._counter(i)
                dg = self._int(self.var_n_digits)
                im = self._mono(E.render_code(self.var_code.get(), E.expand(data, n, dg), E.expand(side, n, dg),
                                              self.style(), self._int(self.var_module, 2)))
                imgs.append(im)
            if loops == 1:
                imgs = imgs * copies
            return imgs, len(imgs), {"tipo": "codice", "codice": self.var_code.get(), "dati": data,
                                     "accanto": side}
        if tab == 3:
            if not self.image_path:
                return [], 0, None
            src = self._source_image(self.image_path, self._int(self.var_page, 1) - 1)
            img = core.fit_image(src, trim=True, margin=self._int(self.var_margin, 8),
                                 rotate=int(self.var_rot.get() or 0))
            if self.var_invert.get():
                img = ImageOps.invert(img.convert("L"))
            im = self._mono(img, self.var_dither.get(), self._int(self.var_thr, 160))
            return [im] * copies, copies, None
        return [], 0, None

    # ========================================================= anteprima
    def _schedule_preview(self):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(180, self._update_preview)

    def _step_preview(self, d):
        self.preview_index = max(0, self.preview_index + d)
        self._schedule_preview()

    def _update_preview(self):
        self._preview_job = None
        c = self.pv_canvas
        try:
            imgs, total, _ = self.build_jobs(preview=True)
        except Exception as e:  # noqa: BLE001
            c.delete("all")
            c.create_text(10, 40, anchor="w", text=f"⚠ {e}", fill="#b00", font=("Segoe UI", 11))
            self.lbl_len.configure(text="")
            return
        tab = self.nb.index(self.nb.select())
        if tab == 1 and total:
            self.lbl_pv.configure(text=f"{self.preview_index + 1} di {total}")
        else:
            self.lbl_pv.configure(text="")
        if not imgs:
            c.delete("all")
            c.create_text(10, 40, anchor="w", text="(niente da stampare)", fill="#777")
            self.lbl_len.configure(text="")
            return
        self._show_preview_image(imgs[0])

    def _show_preview_image(self, mono):
        c = self.pv_canvas
        c.delete("all")
        tape_rgb = TAPE_COLORS.get(self.var_tape.get(), "#ffffff")
        big = mono.convert("L").resize((mono.width * PREVIEW_SCALE, mono.height * PREVIEW_SCALE), Image.NEAREST)
        tape = Image.new("RGB", (big.width, big.height + 20), tape_rgb)
        black = Image.new("RGB", big.size, (20, 20, 20))
        tape.paste(black, (0, 10), ImageOps.invert(big))
        self._preview_photo = ImageTk.PhotoImage(tape)
        c.create_rectangle(7, 7, 13 + tape.width, 13 + tape.height, fill="#aaa", outline="")
        c.create_image(10, 10, anchor="nw", image=self._preview_photo)
        c.configure(scrollregion=(0, 0, tape.width + 24, tape.height + 24))
        mm = mono.width / (self._float(self.var_dots, 7.87) or 7.87)
        self.lbl_len.configure(text=f"Lunghezza ≈ {mm:.0f} mm")

    # =========================================================== salvate
    def _item_title(self, it):
        t = it.get("testo") or it.get("dati") or ""
        t = t.replace("\n", " ⏎ ")
        if len(t) > 46:
            t = t[:45] + "…"
        icon = {"testo": "✏️", "elenco": "📋", "codice": "▦"}.get(it.get("tipo"), "•")
        name = it.get("nome")
        return f"{icon} {name + ' — ' if name else ''}{t}"

    def _refresh_saved(self):
        self.lst_fav.delete(0, "end")
        for it in self.saved:
            self.lst_fav.insert("end", self._item_title(it))
        self.lst_hist.delete(0, "end")
        for it in reversed(self.history):
            self.lst_hist.insert("end", f"{it.get('quando', '')}  {self._item_title(it)}")

    def _current_item(self):
        tab = self.nb.index(self.nb.select())
        if tab == 1:
            return {"tipo": "elenco", "testo": self.txt_list.get("1.0", "end").strip()}
        if tab == 2:
            return {"tipo": "codice", "codice": self.var_code.get(), "dati": self.var_code_data.get(),
                    "accanto": self.var_code_text.get()}
        if tab == 3:
            return None
        return {"tipo": "testo", "testo": self.txt_input.get("1.0", "end").rstrip("\n")}

    def save_favorite(self):
        info = self._current_item()
        if not info:
            messagebox.showinfo(APP_TITLE, "Si possono salvare testo, elenchi e codici.")
            return
        name = simpledialog.askstring(APP_TITLE, "Nome per questa etichetta (facoltativo):", parent=self.root)
        if name is None:
            return
        self.saved.append({**info, "nome": name.strip(), "stile": self.style()})
        self._save_json("preferiti.json", self.saved)
        self._refresh_saved()
        self.banner("⭐ Salvata nei preferiti (scheda «Salvate»).", "ok")

    def _add_history(self, info):
        if not info:
            return
        entry = {**info, "stile": self.style(), "quando": dt.datetime.now().strftime("%d/%m %H:%M")}
        self.history = [h for h in self.history if not (h.get("tipo") == info.get("tipo") and
                                                       h.get("testo") == info.get("testo") and
                                                       h.get("dati") == info.get("dati"))]
        self.history.append(entry)
        self.history = self.history[-100:]
        self._save_json("cronologia.json", self.history)
        self._refresh_saved()

    def _selected_saved(self, src):
        lb = self.lst_fav if src == "fav" else self.lst_hist
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Seleziona prima un'etichetta dall'elenco.")
            return None, None
        i = sel[0]
        if src == "hist":
            i = len(self.history) - 1 - i
        data = self.saved if src == "fav" else self.history
        return (data[i], i) if 0 <= i < len(data) else (None, None)

    def load_saved(self, src, stampa=False):
        it, _ = self._selected_saved(src)
        if not it:
            return
        if it.get("stile"):
            self.set_style(it["stile"])
        tipo = it.get("tipo")
        if tipo == "elenco":
            self.txt_list.delete("1.0", "end")
            self.txt_list.insert("1.0", it.get("testo", ""))
            self.nb.select(1)
        elif tipo == "codice":
            self.var_code.set(it.get("codice", "QR code"))
            self.var_code_data.set(it.get("dati", ""))
            self.var_code_text.set(it.get("accanto", ""))
            self.nb.select(2)
        else:
            self.txt_input.delete("1.0", "end")
            self.txt_input.insert("1.0", it.get("testo", ""))
            self.nb.select(0)
        self._schedule_preview()
        if stampa:
            self.root.after(300, self.print_current)

    def delete_saved(self, src):
        it, i = self._selected_saved(src)
        if it is None:
            return
        if not messagebox.askyesno(APP_TITLE, "Eliminare questa etichetta dall'elenco?"):
            return
        if src == "fav":
            del self.saved[i]
            self._save_json("preferiti.json", self.saved)
        else:
            del self.history[i]
            self._save_json("cronologia.json", self.history)
        self._refresh_saved()

    # ======================================================= calibrazione
    def calibrate(self):
        try:
            imgs, _, _ = self.build_jobs(preview=True)
        except Exception:
            imgs = []
        if not imgs:
            messagebox.showinfo(APP_TITLE, "Prepara prima un'etichetta (scheda Testo).")
            return
        px = imgs[0].width
        mm = simpledialog.askfloat(APP_TITLE, f"Stampa l'etichetta che vedi in anteprima, misurala col "
                                   f"righello\n(solo la parte stampata da bordo a bordo) e scrivi i mm:",
                                   parent=self.root, minvalue=5, maxvalue=2000)
        if mm:
            self.var_dots.set(f"{px / mm:.2f}")
            self.log(f"Calibrazione: {px / mm:.2f} punti/mm")

    # =========================================================== bluetooth
    def _set_status(self):
        if self.ble.connected:
            name = getattr(self.ble.device, "name", "") or "LetraTag"
            self.lbl_status.configure(text=f"● Collegata: {name}", foreground="#080")
            self.btn_conn.configure(text="Disconnetti")
        else:
            self.lbl_status.configure(text="● Non collegata", foreground="#b00")
            self.btn_conn.configure(text="Connetti")

    def auto_connect(self):
        if self.ble.connected or self.busy:
            return
        self.banner("Cerco la LetraTag… (accendila)", "info")

        def done(_):
            self._set_status()
            self.banner("✅ Pronta a stampare.", "ok")

        def err(e):
            self._set_status()
            self.banner("⚠ LetraTag non trovata: accendila e chiudi l'app DYMO sul telefono. "
                        "Riprovo da sola quando stampi.", "warn")

        self.runner.submit(self.ble.ensure_connected(
            log=lambda m: self.root.after(0, lambda: self.log(m)), attempts=2), done, err)

    def scan(self):
        self.btn_scan.configure(state="disabled")
        self.log("Ricerca stampanti Bluetooth (8 s)…")

        def done(devs):
            self.btn_scan.configure(state="normal")
            self.devices = devs
            self.cmb_dev.configure(values=[f"{d.name or 'LetraTag'}  [{d.address}]" for d in devs])
            if devs:
                self.cmb_dev.current(0)
                self.log(f"Trovate {len(devs)} stampanti.")
            else:
                self.log("Nessuna LetraTag trovata. È accesa? L'app DYMO sul telefono è chiusa?")

        def err(e):
            self.btn_scan.configure(state="normal")
            self.log(f"Errore Bluetooth: {e}")

        self.runner.submit(self.ble.scan(8.0), done, err)

    def toggle_connect(self):
        if self.ble.connected:
            self.runner.submit(self.ble.disconnect(), lambda r: (self._set_status(), self.log("Disconnessa.")))
            return
        i = self.cmb_dev.current()
        if i < 0 or i >= len(self.devices):
            self.auto_connect()
            return
        self.btn_conn.configure(state="disabled")

        def done(_):
            self.btn_conn.configure(state="normal")
            self._set_status()
            self.banner("✅ Pronta a stampare.", "ok")

        def err(e):
            self.btn_conn.configure(state="normal")
            self._set_status()
            self.log(f"Connessione fallita: {e}")

        self.runner.submit(self.ble.connect(self.devices[i]), done, err)

    # ============================================================== stampa
    def print_current(self):
        if self.busy:
            return
        try:
            imgs, total, info = self.build_jobs()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, str(e))
            return
        if not imgs:
            messagebox.showinfo(APP_TITLE, "Niente da stampare.")
            return
        if total > 20 and not messagebox.askyesno(APP_TITLE, f"Stampo {total} etichette?"):
            return
        self._print_images(imgs, done_cb=lambda: self._add_history(info))

    def _print_images(self, jobs, done_cb=None, fail_cb=None, auto=False):
        if not jobs:
            return
        self.busy = True
        self.btn_print.configure(state="disabled")
        tot = len(jobs)
        plural = "a" if tot == 1 else "e"
        self.log(f"Invio {tot} etichett{plural}…")
        self.banner(f"🖨  Stampo {tot} etichett{plural}…", "info")
        ui = lambda f: self.root.after(0, f)  # noqa: E731

        async def run():
            if not self.ble.connected:
                ui(lambda: self.banner("🔍 Cerco la LetraTag… accendila.", "info"))
                await self.ble.ensure_connected(log=lambda m: ui(lambda: self.log(m)))
                ui(self._set_status)
            results = []
            for n, img in enumerate(jobs, 1):
                ui(lambda n=n: self.banner(f"🖨  Stampo {n} di {tot}…", "info"))
                res = await self.ble.print_canvas(core.image_to_canvas(img))
                results.append(res)
                ui(lambda n=n, r=res: self.log(f"  {n}/{tot}: {r}"))
                if core.is_error(res):
                    break
                await asyncio.sleep(1.0)
            return results

        def done(results):
            self.busy = False
            self.btn_print.configure(state="normal")
            self._set_status()
            if results and core.is_error(results[-1]):
                self.banner(f"⚠ Stampa interrotta: {results[-1]}", "err")
                self.show_window()
                if fail_cb:
                    fail_cb(results[-1], fatal=True)
                return
            self.banner(f"✅ Fatto! Stampat{plural} {tot} etichett{plural}.", "ok")
            if done_cb:
                done_cb()

        def err(e):
            self.busy = False
            self.btn_print.configure(state="normal")
            self._set_status()
            self.log(f"Errore di stampa: {e}")
            if isinstance(e, core.PrinterNotFound):
                self.banner("⚠ Non trovo la LetraTag. Accendila, avvicinala al PC e chiudi l'app DYMO "
                            "sul telefono." + (" Riprovo tra 20 secondi…" if fail_cb else ""), "warn")
            else:
                self.banner(f"⚠ Errore di stampa: {e}", "err")
            self.show_window()
            if fail_cb:
                fail_cb(str(e), fatal=False)
            elif not auto and not isinstance(e, core.PrinterNotFound):
                messagebox.showerror(APP_TITLE, f"Errore di stampa:\n{e}")

        self.runner.submit(run(), done, err)

    # ================================================ coda da Office
    def _open_folder(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", path])
        except Exception as e:  # noqa: BLE001
            self.log(str(e))

    def _heartbeat(self):
        try:
            with open(os.path.join(self.qdir, HEARTBEAT), "w") as f:
                f.write(str(time.time()))
            stop = os.path.join(self.qdir, ".chiudi")
            if os.path.exists(stop):
                os.remove(stop)
                self.runner.submit(self.ble.disconnect())
                self.root.after(500, self.root.destroy)
                return
            show = os.path.join(self.qdir, SHOW_REQUEST)
            if os.path.exists(show):
                os.remove(show)
                self.show_window()
        except OSError:
            pass
        self.root.after(2000, self._heartbeat)

    def _watch_tick(self):
        try:
            if not self.busy and time.time() >= self.retry_at:
                files = []
                for f in os.listdir(self.qdir):
                    p = os.path.join(self.qdir, f)
                    if f.lower().endswith(core.QUEUE_EXTS) and os.path.isfile(p):
                        files.append((os.path.getmtime(p), p))
                files.sort()
                if files and time.time() - files[0][0] >= 1.0:
                    self._print_queue_file(files[0][1])
        except Exception as e:  # noqa: BLE001
            self.log(f"Coda: {e}")
        self.root.after(1000, self._watch_tick)

    def _move(self, path, sub):
        dest_dir = os.path.join(self.qdir, sub)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, time.strftime("%Y%m%d-%H%M%S_") + os.path.basename(path))
        try:
            os.replace(path, dest)
        except OSError:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            for f in sorted(os.listdir(dest_dir))[:-50]:
                os.remove(os.path.join(dest_dir, f))
        except OSError:
            pass

    def _print_queue_file(self, path):
        self.log(f"Da LibreOffice/OpenOffice: {os.path.basename(path)}")
        self.show_window()
        try:
            labels = []
            if path.lower().endswith(".txt"):
                for i, t in enumerate(core.read_label_txt(path)):
                    labels.append(self.render_text_label(t, self._counter(i)))
            else:
                for pg in range(min(core.pdf_page_count(path), 50)):
                    src = core.load_image_file(path, pg)
                    img = core.fit_image(src, trim=True, margin=self._int(self.var_margin, 8),
                                         rotate=int(self.var_rot.get() or 0))
                    labels.append(self._mono(img, self.var_dither.get(), self._int(self.var_thr, 160)))
        except Exception as e:  # noqa: BLE001
            self.banner(f"⚠ Non riesco a leggere quello che hai mandato: {e}", "err")
            self._move(path, "errori")
            return
        if not labels:
            self.banner("⚠ Niente da stampare: le celle o il testo selezionati sono vuoti.", "warn")
            self._move(path, "errori")
            return
        self._show_preview_image(labels[0])

        def fail(msg, fatal):
            if fatal:
                self._move(path, "errori")
            else:
                self.retry_at = time.time() + 20

        self._print_images(labels, done_cb=lambda: self._move(path, "stampati"), fail_cb=fail, auto=True)

    # ======================================================== impostazioni
    SETTINGS = ("var_copies", "var_n_start", "var_n_step", "var_n_digits", "var_dither", "var_thr",
                "var_rot", "var_dots", "var_tape", "var_code", "var_module")

    def _settings_path(self):
        return os.path.join(core.base_dir(), "impostazioni.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if isinstance(data.get("stile"), dict):
            self.set_style(data["stile"])
        else:  # vecchio formato
            old = {"font": data.get("var_font"), "size": data.get("var_size"), "frame": None,
                   "margin": data.get("var_margin"), "invert": data.get("var_invert"),
                   "stretch": data.get("var_stretch")}
            self.set_style({k: v for k, v in old.items() if v is not None})
        for k in self.SETTINGS:
            if k in data:
                try:
                    getattr(self, k).set(data[k])
                except tk.TclError:
                    pass
        if data.get("testo"):
            self.txt_input.delete("1.0", "end")
            self.txt_input.insert("1.0", data["testo"])

    def _save_settings(self):
        try:
            data = {k: getattr(self, k).get() for k in self.SETTINGS}
            data["stile"] = self.style()
            data["testo"] = self.txt_input.get("1.0", "end").rstrip("\n")
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _on_close(self):
        if getattr(self, "updating", False):
            messagebox.showinfo(APP_TITLE, "Aspetta: sto finendo l'aggiornamento.")
            return
        pending = [f for f in os.listdir(self.qdir) if f.lower().endswith(core.QUEUE_EXTS)]
        if pending and not messagebox.askyesno(
                APP_TITLE, "Ci sono ancora etichette da stampare. Chiudere lo stesso?\n"
                           "(verranno stampate alla prossima apertura)"):
            return
        self._save_settings()
        try:
            os.remove(os.path.join(self.qdir, HEARTBEAT))
        except OSError:
            pass
        try:
            self.runner.submit(self.ble.disconnect()).result(timeout=3)
        except Exception:
            pass
        self.root.destroy()


HEARTBEAT = ".app_attiva"
SHOW_REQUEST = ".mostra"


def already_running() -> bool:
    if "--dopo-aggiornamento" in sys.argv:
        time.sleep(1.5)  # lascia chiudere la versione vecchia
        return False
    q = core.queue_dir()
    hb = os.path.join(q, HEARTBEAT)
    try:
        if os.path.exists(hb) and time.time() - os.path.getmtime(hb) < 6:
            if "--minimizzata" not in sys.argv:
                open(os.path.join(q, SHOW_REQUEST), "w").close()
            return True
    except OSError:
        pass
    return False


def main():
    os.makedirs(core.queue_dir(), exist_ok=True)
    if sys.stderr is None or sys.executable.lower().endswith("pythonw.exe"):
        log = open(os.path.join(core.base_dir(), "errori.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    if already_running():
        return
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    try:
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icona.png")
        root.iconphoto(True, tk.PhotoImage(file=ico))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            messagebox.showerror(APP_TITLE, traceback.format_exc())
        except Exception:
            pass
