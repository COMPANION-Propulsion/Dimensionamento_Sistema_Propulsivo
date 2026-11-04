# Dimensionamento preliminare della ventola

Per il dimensionamento dal Venturi partire da [input_venturi.json](input_venturi.json):
il campo `venturi_result: "auto"` seleziona l'export Venturi piu recente disponibile.
Avviare dalla cartella `2_ventola` con
`.\.venv\Scripts\python.exe -m ventola_designer size`.
Diametro, pressione totale, portata e
densità vengono importati; la velocità sulle pale è ricalcolata sull'area libera
del mozzo. Guida: [input dal Venturi](docs/VENTURI_INPUT.md).

Le istruzioni seguenti per `input_esempio.json` riguardano il precedente modo a
spinta del rotore libero, mantenuto per compatibilità.
`input_esempio.json` contiene i requisiti modificabili dall'utilizzatore.
I valori inclusi sono dimostrativi. Il dimensionatore genera la geometria delle
pale e cerca con SLSQP un candidato che rispetti la spinta minima in tutte le
condizioni, minimizzando l'energia meccanica del ciclo con il modello BEMT.

## Dove trovare i file

| Percorso | Contenuto e utilizzo |
|---|---|
| [input_esempio.json](input_esempio.json) | Diametro, spinte minime, condizioni dell'aria, velocità, durate e limiti di ricerca |
| [docs/](docs/README.md) | Guida operativa, risultati e documenti del piano |
| `ventola_designer/` | Codice Python: modello, geometria, ottimizzatore ed esportazioni |
| `ventola_designer/airfoils/` | Catalogo e dati aerodinamici usati dal codice |
| `tests/` | Test automatici del software |
| [ventola_output/](ventola_output/) | Risultati delle esecuzioni, in cartelle separate |
| [archivio/](archivio/README.md) | Backup e istruzioni storiche conservati |
| `.venv/` | Ambiente Python locale del progetto |
| [requirements-polars.txt](requirements-polars.txt) | Dipendenze per la generazione delle polari |

## Avvio da PowerShell

Eseguire questi comandi dalla cartella `2_ventola`, usando l'ambiente già presente.
Il controllo dell'input non avvia il dimensionamento:

```powershell
.\.venv\Scripts\python.exe -m ventola_designer size --input input_esempio.json --validate-only
```

Per avviare il dimensionamento con i requisiti del file:

```powershell
.\.venv\Scripts\python.exe -m ventola_designer size --input input_esempio.json
```

Per usare un altro file, sostituire il percorso dopo `--input`. `--output` permette
di scegliere una nuova cartella di destinazione; altrimenti il programma crea
una cartella datata sotto `risultati/<caso>/3_ventola/` se tutti i punti provengono
dallo stesso caso Venturi nella struttura standard. Negli altri casi usa
`2_ventola/ventola_output/`.

Per verificare il software:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Il comando senza `size` genera soltanto un seme geometrico. La guida completa
all'ottimizzatore è in [docs/OTTIMIZZAZIONE.md](docs/OTTIMIZZAZIONE.md).

## Leggere i risultati

Nella cartella dell'esecuzione:

- `RISULTATO.md`: riepilogo leggibile ed esito dei candidati.
- `optimization.json` e `report.json`: input, impostazioni e diagnostica numerica.
- `sections.csv`, `blade_points.csv`, `blade_surface.obj`, `preview.svg` e file
  `.dat`: geometria del candidato selezionato, quando presente.
- `paraview/`: geometria VTP e risultati radiali BEMT; dettagli nella
  [guida ai file ParaView](docs/README.md#paraview).

Le cartelle di risultati precedenti agli ultimi aggiornamenti possono avere
meno file. Un risultato privo di candidati accettati resta un esito documentato:
non dimostra l'impossibilità fisica di soddisfare i requisiti.

## Perimetro attuale

Modello preliminare del solo rotore, indipendente dal Venturi. Il diametro è
imposto; mozzo, corde, calettamenti e regimi sono variabili del dimensionamento.
La velocità assiale in input è riferita alla corrente lontano a monte.
La ricerca è locale e non garantisce un minimo globale.

Condotto, CFD, verifiche strutturali e degli attacchi, motore ed elettronica
sono fuori dall'ambito attuale. La validazione sperimentale delle polari è
in pausa per decisione dell'utente. Le polari attuali sono numeriche.
I controlli geometrici del codice restano screening dimensionali.

Il riordino conserva i percorsi operativi di input, codice e risultati.
I documenti `BLOCCO_*` descrivono l'evoluzione del piano e possono contenere
stati precedenti: per l'utilizzo corrente fare riferimento a questo README
e alla guida all'ottimizzatore.
