# Blocco 4 — Architettura proposta dello script

Stato: primo incremento implementato: lettura input, controlli, generazione analitica NACA, pala parametrica e export CSV/OBJ/SVG. Moduli atmosferici, polari, BEMT e ottimizzatore ancora da implementare. Per i comandi effettivi vedere README.md; l'albero seguente descrive l'architettura finale prevista.

## Principio

Il pacchetto della ventola è autonomo sotto `2_ventola/ventola_designer/`. Non importa moduli Venturi né legge i loro output. Il modello BEMT rotorico e la futura CFD sono livelli distinti dietro interfacce di prestazione comuni. La CFD del gruppo intubato entra solo quando esistono geometria del condotto e dati adeguati.

Il primo risultato è una previsione del rotore secondo BEMT. Il report deve dichiarare che il contributo del condotto non è quantificato e che quindi la spinta netta installata non è ancora validata.

## Moduli

```text
2_ventola/
├── input.json                 # caso modificabile dall'utente
├── README.md                  # avvio, campi, ipotesi e limiti
├── ventola_designer/
│   ├── config.py              # lettura e controllo input
│   ├── atmosphere.py          # proprietà dell'aria e convenzioni termo
│   ├── geometry.py            # generazione parametrica delle sezioni e controlli
│   ├── airfoils.py            # catalogo interno, polari e interpolazione validata
│   ├── bemt.py                # analisi rotorica per un punto operativo
│   ├── objective.py           # energia totale e vincoli di spinta minima
│   ├── optimizer.py           # SLSQP e confronto numeri discreti di pale
│   ├── results.py             # risultati, avvisi e stato di convergenza
│   └── export.py              # tabelle e geometria preliminare
├── tests/
│   ├── test_atmosphere.py
│   ├── test_geometry.py
│   └── test_bemt.py
└── outputs/                   # report, tabelle e geometrie generate
```

La geometria della pala è generata dallo script: l'utilizzatore specifica requisiti e vincoli, mentre il programma parametrizza e ottimizza corda, calettamento e mozzo, quindi produce le sezioni risultanti. Il profilo è selezionato da un catalogo interno documentato e compatibile con le polari disponibili; non si chiede all'utente di caricare una geometria già progettata. La struttura è indicativa: il codice verrà introdotto quando il modello relativo sarà definito. `airfoils.py` richiede polari documentate; non si devono inventare coefficienti aerodinamici.

## Flusso del programma

1. Caricare il caso e controllare unità, valori e intervalli.
2. Derivare proprietà dell'aria con ipotesi esplicite.
3. Parametrizzare una geometria di pala regolare fra mozzo e raggio esterno imposto.
4. Per ciascun numero di pale ammesso, calcolare ogni punto operativo BEMT e risolvere l'ottimizzazione continua vincolata con SLSQP.
5. Calcolare l'energia totale come somma di potenza meccanica per durata, verificando la spinta minima in ogni caso.
6. Confrontare solo soluzioni ammissibili; riportare chiaramente mancata convergenza, vincoli violati o requisiti non soddisfatti.
7. Esportare geometria, prestazioni e ipotesi. Quando sarà disponibile la geometria del condotto, aggiungere un backend CFD per analisi e raffinamento, senza cambiare l'interfaccia del caso.

## Scelte da finalizzare prima del solutore BEMT

- Forma di parametrizzazione di corda e calettamento, numero di stazioni e limiti geometrici.
- Polari dei profili, intervallo di Re e Mach e trattamento dello stallo.
- Correzioni di induzione, perdite di punta/mozzo e trattamento del flusso statico.
- Limiti numerici di mozzo e regime; normalizzazione di variabili e vincoli per SLSQP.
- Dati e unità d'ingresso definitive, criteri di convergenza e precisione.
- Validazione indipendente del modello rotorico; l'ottimizzatore non deve validare da solo la propria previsione.

## Implementazione progressiva

Costruire prima il caricamento e la validazione di un caso, poi il calcolo delle proprietà dell'aria, quindi una singola analisi BEMT non ottimizzata. Verificare il modello e le sue convenzioni; solo dopo aggiungere SLSQP e il ciclo sui numeri di pale. Questa sequenza rende gli errori del modello distinguibili dagli errori dell'ottimizzazione.
