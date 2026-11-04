# Documentazione

Tutti i comandi delle guide vanno eseguiti dalla radice `2_ventola`.

- [Avvio e struttura del progetto](../README.md).
- [Dimensionamento da pressione e portata del Venturi](VENTURI_INPUT.md).
- [Ottimizzazione, input e vincoli](OTTIMIZZAZIONE.md).
- [Mappa Cp sulle pale](CP_MAP.md).

I documenti di pianificazione iniziali sono nella cronologia git.

## ParaView

Per aggiungere il coefficiente di pressione sulla superficie delle pale vedere
[Mappa Cp](CP_MAP.md): comando `python -m ventola_designer cp --report PERCORSO`.

I file ParaView si trovano in `04_cfd/` nella cartella di ogni nuova esecuzione.

| File | Contenuto |
|---|---|
| `fan_geometry.vtp` | Superfici di tutte le pale della geometria selezionata, in metri; disponibile se esiste una geometria da esportare |
| `results.pvd` | Raccolta dei dataset radiali esportati |
| `run_*.vtp` | Una linea radiale BEMT del solo candidato selezionato per condizione operativa |
| `manifest.json` | Associazione dei file alle condizioni, stato di accettazione e motivi delle omissioni |

I campi locali comprendono angolo d'attacco, Reynolds, Mach, induzioni,
confidenza delle polari, fattori di perdita e residuo del bilancio.
Spinta, potenza e rpm sono valori globali associati alla linea.
I campi sono campioni radiali del modello BEMT e non un campo CFD volumetrico.

L'indice temporale della raccolta identifica il punto operativo (0, 1, ...),
non il tempo fisico. La durata di ogni condizione resta un input del ciclo.
L'esportazione attuale riguarda il solo candidato selezionato.
Gli altri candidati e gli avvii SLSQP restano in `05_convergenza/optimization.json`
e `00_sintesi/report.json`.
La superficie delle pale è aperta a radice e punta; il solido del mozzo
e gli attacchi non sono modellati.
