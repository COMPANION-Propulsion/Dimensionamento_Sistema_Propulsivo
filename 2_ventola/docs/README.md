# Documentazione

Tutti i comandi delle guide vanno eseguiti dalla radice `2_ventola`.

- [Avvio e struttura del progetto](../README.md).
- [Dimensionamento da pressione e portata del Venturi](VENTURI_INPUT.md).
- [Ottimizzazione, input e vincoli](OTTIMIZZAZIONE.md).
- [Blocco 1: specifica](piano/BLOCCO_1_SPECIFICA.md).
- [Blocco 2: input e vincoli](piano/BLOCCO_2_INPUT_E_VINCOLI.md).
- [Blocco 3: modello fisico](piano/BLOCCO_3_MODELLO_FISICO.md).
- [Blocco 4: architettura](piano/BLOCCO_4_ARCHITETTURA.md).
- [Blocco 5: BEMT e dati delle pale](piano/BLOCCO_5_BEMT_E_DATI_PALE.md).
- [Blocco 6: verifica e piano del codice](piano/BLOCCO_6_VERIFICA_E_PIANO_CODICE.md).

I blocchi sono conservati come documenti di pianificazione: le indicazioni di
stato e gli alberi di file al loro interno possono riferirsi a versioni precedenti.
Le esclusioni correnti e la pausa della validazione sono riportate nel README
principale. Il vecchio README è conservato nell'[archivio](../archivio/README.md).

## ParaView

L'esportatore crea `paraview/` nella cartella di ogni nuova esecuzione.

| File | Contenuto |
|---|---|
| `fan_geometry.vtp` | Superfici di tutte le pale della geometria selezionata, in metri; disponibile se esiste una geometria da esportare |
| `results.pvd` | Raccolta dei dataset radiali esportati |
| `run_*.vtp` | Una linea radiale BEMT per coppia profilo/pale riportata e condizione operativa calcolabile |
| `manifest.json` | Associazione dei file alle condizioni, stato di accettazione e motivi delle omissioni |

I campi locali comprendono angolo d'attacco, Reynolds, Mach, induzioni,
confidenza delle polari, fattori di perdita e residuo del bilancio.
Spinta, potenza e rpm sono valori globali associati alla linea.
I campi sono campioni radiali del modello BEMT e non un campo CFD volumetrico.

L'indice temporale della raccolta identifica il punto operativo (0, 1, ...),
non il tempo fisico. La durata di ogni condizione resta un input del ciclo.
L'esportazione attuale riguarda il candidato riportato per ogni coppia;
i singoli avvii SLSQP sono documentati in `optimization.json`.
I dataset dei candidati esclusi, se calcolabili, hanno `accepted = 0`.
La superficie delle pale è aperta a radice e punta; il solido del mozzo
e gli attacchi non sono modellati.
