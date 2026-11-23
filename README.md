# Etichette LetraTag

> ### ⬇️ Prima di tutto: [scarica Python per Windows](https://www.python.org/downloads/)
> Premi il pulsante giallo **Download Python** e installalo spuntando **Add python.exe to PATH**.
> Poi scarica questa app con **Code ▸ Download ZIP** e fai doppio clic su **INSTALLA.pyw**.

App per PC Windows che stampa etichette con la **DYMO LetraTag 200B** via Bluetooth, senza il telefono.

- Testo con tutti i caratteri del PC, stili rapidi, emoji e simboli
- Corsivo, sottolineato, barrato, contorno, bianco su nero, cornici
- Data automatica, numerazione (Scatola 1, 2, 3…), etichette ripetute per i cavi, lunghezza fissa
- Elenchi da Calc, Excel o CSV, QR code e codici a barre
- Preferiti e cronologia
- Pulsante «Stampa su LetraTag» dentro LibreOffice e OpenOffice
- Pulsante **🔄 Aggiorna**: le nuove versioni arrivano da questo repository

## Installazione

1. Installa **Python** da [python.org/downloads](https://www.python.org/downloads/) (spunta *Add python.exe to PATH*). Nello ZIP c'è anche il collegamento **1 - SCARICA PRIMA PYTHON** che apre la stessa pagina.
2. Su questa pagina premi **Code ▸ Download ZIP**, poi sul file scaricato clic destro ▸ **Estrai tutto**.
3. Doppio clic su **INSTALLA.pyw** e premi **INSTALLA**.

Dopo, gli aggiornamenti si installano dall'app con il pulsante **🔄 Aggiorna**.

## Come funziona l'aggiornamento

`programma/versione.json` contiene il numero di versione e l'impronta SHA-256 di ogni file.
L'app lo confronta con la copia installata, scarica solo i file cambiati, controlla le impronte
e li sostituisce solo se sono tutti corretti.

Per pubblicare una versione nuova:

```
python sviluppo/pubblica.py 2.1.0 "Cosa c'è di nuovo"
git commit -am "Versione 2.1.0" && git push
```

## Note

La LetraTag 200B non ha driver per PC: l'app usa il protocollo Bluetooth ricostruito dalla
libreria open source [dymo-bluetooth](https://github.com/ysfchn/dymo-bluetooth) (licenza MIT).
