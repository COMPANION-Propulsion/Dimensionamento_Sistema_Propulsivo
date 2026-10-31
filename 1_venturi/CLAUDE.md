# 1_venturi: note di ripresa

Stato al 2026-10-31. Il codice dell'ottimizzazione è scritto, ma **`--optimize` non è mai stato
eseguito dall'inizio alla fine**. La ventola reale arriverà dopo: questa fase va tenuta semplice.

## Obiettivo

Generare il condotto di un propulsore a massima spinta con ottimizzazione di forma (adjoint +
morphing). Un condotto passivo non produce spinta (`Ve <= V0`), quindi l'energia entra da un disco
attuatore: `dp_disk` è un dato d'ingresso che arriverà dal dimensionamento della ventola.

Decisioni prese con Samuele:
- disco attuatore a `dp_disk` fisso;
- condizioni in `../input.py` (dizionario `VENTURI`, **valori ancora segnaposto**);
- adjoint Python interno, nessuna dipendenza nuova (niente SU2);
- `D_disk` fisso: se fosse libero, a `dp` fisso l'ottimo sarebbe un tubo dritto a diametro massimo.

Non toccare il resto del progetto. `../run_sistema.py` resta vuoto finché non viene chiesto.

## Comandi (da questa cartella)

```
python run_venturi.py --optimize
python -m venturi_designer.analysis.grid_study --duct results/duct_air_20C/design.json
```

## Struttura di `venturi_designer/`

- `core/`: `config`, `fluids`, `propulsion` (caso, disco, spinta)
- `geometry/`: `venturi` (profilo analitico), `morph` (due B-spline con tratto dritto del disco)
- `solver/`: griglia, proiezione, turbolenza, solver a pseudo-tempo, kernel Numba
- `optimization/`: `sizing` (ex `optimizer.py`), `adjoint` (sistema stazionario, Newton, adjoint),
  `shape_opt` (ciclo SLSQP e vincoli)
- `analysis/`: `validation`, `grid_study`
- `export/`, `cli.py`

## Scelte numeriche da non perdere

- Il solver a pseudo-tempo ristagna (residuo 0.036 su un caso in aria, griglia 64x26), quindi nella
  catena di ottimizzazione serve solo come primo tentativo. Lo stato finale viene da Newton in
  `optimization/adjoint.py`, che include `Q` come incognita.
- Il sistema Newton riusa i kernel del solver ma aggiunge due termini, quindi i due risultati
  differiscono di una quantità **non ancora misurata**:
  - `KAPPA_FLUX`, smorzamento dei flussi a scacchiera (tipo Rhie-Chow). Quei modi sono invisibili a
    `uz` e rendevano la Jacobiana quasi singolare.
  - `EPS_LIMITER`, limitatore van Albada al posto di van Leer. Con `eps2 = 0`, il default, i kernel
    usano ancora van Leer.
- Continuazione pseudo-transitoria: la quantità di moto è `dF/dt = +R`, quindi il termine è
  `J - sigma*D`. Il segno opposto integra all'indietro nel tempo e fa divergere.
- La turbolenza è congelata nell'adjoint: Baldwin-Lomax cerca un massimo lungo la normale e non è
  derivabile.
- I vincoli di separazione (`CF_MIN = 5e-4`) e gli angoli limite sono default da rivedere. A `dp`
  fisso è la separazione a fermare l'allargamento dell'uscita, e Baldwin-Lomax lì è poco affidabile.

## Misurato (griglia 64x26, una sola forma, prima della ristrutturazione)

| Controllo | Risultato |
|---|---|
| Newton | residuo circa 1e-9 |
| Adjoint vs differenze finite a turbolenza congelata, una sola variabile | 180.38 / 179.99 su `dT/dx0`, 301.55 / 301.61 sulla separazione |
| Tempo adjoint, 3 funzioni e 15 variabili | 0.88 s |
| Spinta da getto vs bilancio di forze | 21.07 N / 21.23 N, 0.8 % |
| Spinta vs limite ideale `2*dp*Ae` | 21.07 N / 24.61 N, 86 % |

## Prossimi passi, in ordine

1. **Chiarire il gradiente.** Con `nu_t` ricalcolata, `dT/dx0` vale 110 contro 180 dell'adjoint
   (-38 %). Il confronto è su una sola variabile e con passo piccolo: fare una scansione di `T` su
   più variabili e passi più larghi per capire se è un errore reale o rumore del modello. Se è
   reale, scrivere il ripiego a differenze finite in parallelo sugli 8 core.
2. Controllare la retrocompatibilità del solver contro questi valori del codice originale:
   caso default 90x36 con `Cd = 0.97510`, `dp = 6652.12 Pa`, `recovery = 0.88681`, 18556 iterazioni.
3. Eseguire `--optimize` e l'export del condotto, mai provati. `wall_segments` è una polilinea: va
   verificata con l'export CAD.
4. Misurare la differenza tra il solver e il sistema Newton a parità di forma e portata, al variare
   di `KAPPA_FLUX`.
5. Scrivere i test `pytest` in `tests/` (non esistono ancora): fisica (`dp_disk = 0` deve dare
   `T < 0`), morphing, adjoint, end-to-end.
6. Decidere con Samuele il vincolo anti-separazione. Il piano prevedeva che scrivesse quel pezzo.

## Avvertenze

- Prima di cancellare qualcosa, verificare davvero se è tracciato da git.
- Nulla di questo lavoro è ancora stato committato. Gli spostamenti e le rimozioni dei `__pycache__`
  sono in stage.
- Se ricompare `No module named 'venturi'`, la cache Numba è vecchia: eliminare i `.nbi`/`.nbc`.
