"""Lingua dell'interfaccia: italiano (testi originali) o inglese."""
from __future__ import annotations

import json
import os

LINGUE = {"it": "🇮🇹 Italiano", "en": "🇬🇧 English"}
LANG = "it"


def carica(base_dir: str) -> str:
    """Legge la lingua salvata nelle impostazioni (prima dell'avvio dell'interfaccia)."""
    global LANG
    try:
        with open(os.path.join(base_dir, "impostazioni.json"), encoding="utf-8") as f:
            LANG = json.load(f).get("lingua", "it")
    except Exception:
        LANG = "it"
    if LANG not in LINGUE:
        LANG = "it"
    return LANG


def T(s: str) -> str:
    """Traduce un testo dell'interfaccia (gli spazi intorno restano)."""
    if LANG == "it" or not s:
        return s
    core = s.strip()
    tr = EN.get(core)
    if tr is None:
        return s
    i = s.find(core)
    return s[:i] + tr + s[i + len(core):]


EN = {
    # schede e riquadri
    "✏️ Testo": "✏️ Text", "📋 Elenco": "📋 List", "▦ QR e codici a barre": "▦ QR & barcodes",
    "🖼 Immagine / PDF": "🖼 Image / PDF", "⭐ Salvate": "⭐ Saved", "⚙ Impostazioni": "⚙ Settings",
    "Stampante": "Printer", "Stile": "Style", "Anteprima": "Preview",
    "⭐ Preferiti": "⭐ Favourites", "🕘 Ultime stampate": "🕘 Recently printed",
    # pulsanti
    "🔍 Cerca": "🔍 Search", "Connetti": "Connect", "Disconnetti": "Disconnect",
    "🔄 Aggiorna": "🔄 Update", "Aggiorno…": "Updating…", "🖨  STAMPA": "🖨  PRINT",
    "😀 Emoji e simboli": "😀 Emoji & symbols", "📅 Inserisci": "📅 Insert", "🧹 Pulisci": "🧹 Clear",
    "⭐ Salva nei preferiti": "⭐ Save to favourites", "📂 Importa da Calc/Excel/CSV…": "📂 Import from Calc/Excel/CSV…",
    "📋 Incolla": "📋 Paste", "📂 Apri PDF o immagine…": "📂 Open PDF or image…", "Apri": "Open",
    "🖨 Stampa": "🖨 Print", "🗑 Elimina": "🗑 Delete", "Calibra…": "Calibrate…",
    "Apri cartella dei dati": "Open data folder", "🔄 Controlla aggiornamenti": "🔄 Check for updates",
    "Frasi pronte": "Ready-made phrases", "Emoji e simboli": "Emoji & symbols",
    "Cerco la LetraTag…": "Looking for the LetraTag…", "Collegata.": "Connected.",
    "Sito DYMO": "DYMO website",
    # etichette dei campi
    "Colore nastro (solo anteprima)": "Tape colour (preview only)", "Stile rapido": "Quick style",
    "Carattere": "Font", "Dimensione (0 = automatica)": "Size (0 = automatic)", "Allinea": "Align",
    "Corsivo": "Italic", "Sottolineato": "Underline", "Barrato": "Strikethrough",
    "Solo contorno": "Outline only", "Bianco su nero": "White on black", "Spazio lettere": "Letter spacing",
    "Interlinea": "Line spacing", "Cornice": "Frame", "Emoji": "Emoji", "Margini": "Margins",
    "Ripeti (cavi)": "Repeat (cables)", "Lunghezza fissa mm (0 = auto)": "Fixed length mm (0 = auto)",
    "Allarga": "Stretch", "Copie": "Copies", "Numero {n}: parti da": "Number {n}: start at",
    "passo": "step", "cifre": "digits", "Tipo": "Type", "Barre larghe": "Bar width",
    "Contenuto": "Content", "Testo accanto": "Text beside", "Pagina": "Page", "Ruota": "Rotate",
    "Retinatura (foto)": "Dithering (photos)", "Soglia": "Threshold", "Lingua": "Language",
    "Punti per millimetro (calibrazione lunghezza)": "Dots per millimetre (length calibration)",
    "● Non collegata": "● Not connected",
    # testi di aiuto
    "Invio = nuova riga (max 2-3 righe). Le parti tra { } vengono riempite in stampa: {data}, {n}…":
        "Enter = new line (2-3 lines max). Parts in { } are filled in when printing: {date}, {n}…",
    "Loghi, disegni, foto o un PDF: vengono adattati all'altezza del nastro.":
        "Logos, drawings, photos or a PDF: they are scaled to the tape height.",
    "Clicca per inserire nel testo. Puoi anche scriverle con Win + . (punto)":
        "Click to insert into the text. You can also type them with Win + . (full stop)",
    "Stampa un'etichetta, misurala col righello e premi Calibra: le lunghezze in mm diventano precise.":
        "Print a label, measure it with a ruler and press Calibrate: lengths in mm become accurate.",
    "QR_NOTA": ("The tape is 30 dots high: the QR code comes out small (about 4 mm) and only suits short "
                "texts (~25 characters max). Try scanning it with a phone before printing many.\n"
                "Code128 = letters and numbers; EAN-13 = 12 digits (the 13th is calculated for you)."),
    "OFFICE_NOTA": ("LibreOffice / OpenOffice: the yellow «Stampa su LetraTag» button sends the selected cells "
                    "or text to the app,\nwhich prints them with the style chosen here."),
    "LINGUA_NOTA": "The app restarts to change language.",
    # stati e messaggi
    "(niente da stampare)": "(nothing to print)", "✅ Pronta a stampare.": "✅ Ready to print.",
    "Cerco la LetraTag… (accendila)": "Looking for the LetraTag… (switch it on)",
    "🔍 Cerco la LetraTag… accendila.": "🔍 Looking for the LetraTag… switch it on.",
    "⚠ LetraTag non trovata: accendila e chiudi l'app DYMO sul telefono. Riprovo da sola quando stampi.":
        "⚠ LetraTag not found: switch it on and close the DYMO app on your phone. I'll retry when you print.",
    "⚠ Non trovo la LetraTag. Accendila, avvicinala al PC e chiudi l'app DYMO sul telefono.":
        "⚠ I can't find the LetraTag. Switch it on, bring it closer to the PC and close the DYMO app on your phone.",
    "Riprovo tra 20 secondi…": "Retrying in 20 seconds…",
    "⚠ Niente da stampare: le celle o il testo selezionati sono vuoti.":
        "⚠ Nothing to print: the selected cells or text are empty.",
    "✅ Aggiornata! Riavvio l'app…": "✅ Updated! Restarting the app…",
    "⬇ Scarico l'aggiornamento…": "⬇ Downloading the update…",
    "⭐ Salvata nei preferiti (scheda «Salvate»).": "⭐ Saved to favourites («Saved» tab).",
    "Aspetta che finisca la stampa, poi riprova.": "Wait for printing to finish, then try again.",
    "Aspetta: sto finendo l'aggiornamento.": "Please wait: I'm finishing the update.",
    "Disconnessa.": "Disconnected.",
    "Eliminare questa etichetta dall'elenco?": "Delete this label from the list?",
    "Nessuna LetraTag trovata. È accesa? L'app DYMO sul telefono è chiusa?":
        "No LetraTag found. Is it on? Is the DYMO app on your phone closed?",
    "Niente da stampare.": "Nothing to print.",
    "Prepara prima un'etichetta (scheda Testo).": "Prepare a label first (Text tab).",
    "Pronto. Accendi la LetraTag: l'app la cerca da sola.": "Ready. Switch on the LetraTag: the app looks for it by itself.",
    "Pulsante di OpenOffice aggiornato.": "OpenOffice button updated.",
    "Ricerca stampanti Bluetooth (8 s)…": "Searching for Bluetooth printers (8 s)…",
    "Seleziona prima un'etichetta dall'elenco.": "Select a label from the list first.",
    "Si possono salvare testo, elenchi e codici.": "You can save text, lists and codes.",
    "Novità di questa versione:": "What's new in this version:",
    "Importa elenco": "Import list", "Apri PDF o immagine": "Open PDF or image",
    "Fogli di calcolo": "Spreadsheets", "PDF e immagini": "PDFs and images", "Tutti": "All files",
    "Nome per questa etichetta (facoltativo):": "Name for this label (optional):",
    # testi con valori ({} = parte variabile)
    "versione {v}": "version {v}", "Versione installata: {v}   ·   aggiornamenti da {r}":
        "Installed version: {v}   ·   updates from {r}",
    "🔔 Aggiorna alla {v}": "🔔 Update to {v}",
    "🔔 È disponibile la versione {v}: premi «Aggiorna» in alto a destra.":
        "🔔 Version {v} is available: press «Update» at the top right.",
    "Hai già l'ultima versione ({v}).": "You already have the latest version ({v}).",
    "Non riesco a controllare gli aggiornamenti.\nSei collegato a internet?\n\n{e}":
        "I can't check for updates.\nAre you connected to the internet?\n\n{e}",
    "Aggiornare alla versione {v}?\n\n": "Update to version {v}?\n\n", "Novità:\n{n}\n\n": "What's new:\n{n}\n\n",
    "L'app si riavvia da sola alla fine.": "The app restarts by itself at the end.",
    "Aggiornata. Riaprila dall'icona sul desktop.\n({e})": "Updated. Reopen it from the desktop icon.\n({e})",
    "⚠ Aggiornamento non riuscito: {e}": "⚠ Update failed: {e}", "Aggiornamento non riuscito: {e}": "Update failed: {e}",
    "Per aggiornare anche il pulsante di OpenOffice, chiudi OpenOffice/LibreOffice (tutte le finestre) e premi OK.":
        "To update the OpenOffice button too, close OpenOffice/LibreOffice (all windows) and press OK.",
    "Caratteri disponibili: {n}": "Fonts available: {n}",
    "Impossibile leggere il file:\n{e}": "Can't read the file:\n{e}",
    "La prima riga è un'intestazione?\n\n«{r}»": "Is the first row a header?\n\n«{r}»",
    "Importate {n} etichette da {f}": "Imported {n} labels from {f}",
    "{n} etichette · una per riga · usa  |  per andare a capo (es. «Sale | {data}»)":
        "{n} labels · one per line · use  |  for a new line (e.g. «Salt | {date}»)",
    "{i} di {n}": "{i} of {n}", "Lunghezza ≈ {mm} mm": "Length ≈ {mm} mm",
    "Stampa l'etichetta che vedi in anteprima, misurala col righello\n(solo la parte stampata da bordo a bordo) e scrivi i mm:":
        "Print the label shown in the preview, measure it with a ruler\n(only the printed part, edge to edge) and enter the mm:",
    "Calibrazione: {v} punti/mm": "Calibration: {v} dots/mm", "Trovate {n} stampanti.": "Found {n} printers.",
    "Errore Bluetooth: {e}": "Bluetooth error: {e}", "Connessione fallita: {e}": "Connection failed: {e}",
    "Stampo {n} etichette?": "Print {n} labels?",
    "Invio {n} etichette…": "Sending {n} labels…", "🖨  Stampo {n} etichette…": "🖨  Printing {n} labels…",
    "🖨  Stampo {i} di {n}…": "🖨  Printing {i} of {n}…", "⚠ Stampa interrotta: {e}": "⚠ Printing stopped: {e}",
    "✅ Fatto! Stampate {n} etichette.": "✅ Done! Printed {n} labels.",
    "Errore di stampa: {e}": "Print error: {e}", "⚠ Errore di stampa: {e}": "⚠ Print error: {e}",
    "Errore di stampa:\n{e}": "Print error:\n{e}",
    "Da LibreOffice/OpenOffice: {f}": "From LibreOffice/OpenOffice: {f}",
    "⚠ Non riesco a leggere quello che hai mandato: {e}": "⚠ I can't read what you sent: {e}",
    "● Collegata: {n}": "● Connected: {n}", "Stampa completata.": "Printing complete.",
    # risposte della stampante
    "OK": "OK", "OK (batteria scarica)": "OK (low battery)", "Stampa annullata": "Printing cancelled",
    "ERRORE di stampa": "Print ERROR", "ERRORE: batteria troppo scarica": "ERROR: battery too low",
    "ERRORE: cassetta nastro mancante": "ERROR: tape cassette missing",
    "Inviata (nessuna conferma ricevuta)": "Sent (no confirmation received)",
    # valori dei menu
    "Nessuna": "None", "Sottile": "Thin", "Spessa": "Thick", "Arrotondata": "Rounded", "Doppia": "Double",
    "Tratteggiata": "Dashed", "Parentesi": "Brackets",
    "Dettagliate": "Detailed", "Retinate": "Dithered", "Piene (sagoma)": "Solid (silhouette)", "Contorno": "Outline",
    "Sinistra": "Left", "Centro": "Centre", "Destra": "Right",
    "Classico": "Classic", "Moderno": "Modern", "Forte": "Bold", "Elegante": "Elegant",
    "Macchina da scrivere": "Typewriter", "Scritto a mano": "Handwritten", "Calligrafico": "Calligraphy",
    "Stencil": "Stencil", "Con cornice": "Framed", "Negativo (bianco su nero)": "Negative (white on black)",
    "Cavo (ripetuto)": "Cable (repeated)",
    "Bianco": "White", "Giallo": "Yellow", "Trasparente": "Clear", "Rosso": "Red", "Verde": "Green",
    "Blu": "Blue", "Argento": "Silver",
    # categorie emoji
    "Simboli": "Symbols", "Frecce": "Arrows", "Numeri": "Numbers", "Forme": "Shapes", "Cucina": "Kitchen",
    "Casa": "Home", "Ufficio": "Office", "Lavoro": "Workshop", "Viaggi": "Travel", "Natura": "Nature",
    "Faccine": "Faces", "Bambini": "Kids",
    # menu Inserisci
    "Data di oggi": "Today's date", "Data tra 7 giorni": "Date in 7 days", "Data tra 30 giorni": "Date in 30 days",
    "Data per esteso": "Long date", "Ora": "Time", "Giorno della settimana": "Day of the week", "Mese": "Month",
    "Anno": "Year", "Numero progressivo": "Counter",
    "Aperto il {data}": "Opened on {date}", "Scade il … (tra 30 giorni)": "Expires on … (in 30 days)",
    "Congelato il {data}": "Frozen on {date}", "Scatola numerata": "Numbered box", "Fragile": "Fragile",
    "Non toccare": "Do not touch", "Proprietà di…": "Property of…", "Cavo / caricatore": "Cable / charger",
    "Dispensa": "Pantry", "Spezie": "Spices", "Regalo": "Gift", "Medicine": "Medicines",
}

# valori inseriti nel testo quando l'interfaccia è in inglese
FRASI_EN = {
    "Aperto il {data}": "Opened {date}", "Scade il {data+30}": "Expires {date+30}",
    "❄ Congelato\n{data}": "❄ Frozen\n{date}", "📦 Scatola {n}": "📦 Box {n}",
    "⚠ FRAGILE ⚠": "⚠ FRAGILE ⚠", "⛔ Non toccare": "⛔ Do not touch", "Proprietà di ": "Property of ",
    "🎁 Per ": "🎁 For ",
    "{data}": "{date}", "{data+7}": "{date+7}", "{data+30}": "{date+30}", "{dataesteso}": "{longdate}",
    "{ora}": "{time}", "{giorno}": "{day}", "{mese}": "{month}", "{anno}": "{year}",
}


def V(s: str) -> str:
    """Testo da inserire nell'etichetta (frasi pronte e variabili) nella lingua scelta."""
    return FRASI_EN.get(s, s) if LANG == "en" else s


def TK(chiave: str, italiano: str) -> str:
    """Testi lunghi: in inglese usa la traduzione registrata sotto `chiave`."""
    return EN.get(chiave, italiano) if LANG == "en" else italiano
