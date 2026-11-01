# 1_venturi: note di ripresa

Stato al 2026-11-01. La catena completa funziona (ottimizzazione, export, stima dell'errore), ma con
valori **segnaposto** in `../input.py`. La ventola reale arriverà dopo: questa fase va tenuta semplice.
Nessun commit è stato fatto: Samuele valuta in locale e decide lui commit e push.

## Obiettivo

Generare il condotto di un propulsore a massima spinta con ottimizzazione di forma (adjoint +
morphing). Un condotto passivo non produce spinta (`Ve <= V0`), quindi l'energia entra da un disco
attuatore: `dp_disk` è un dato d'ingresso che arriverà dal dimensionamento della ventola.

Decisioni prese con Samuele:
- disco attuatore a `dp_disk` fisso;
- condizioni in `../input.py` (dizionario `VENTURI`);
- griglia scelta in input: `"grid": "coarse" | "medium" | "fine"` (`GRID_LEVELS` in `core/propulsion.py`);
- adjoint Python interno, nessuna dipendenza nuova (niente SU2);
- `D_disk` fisso: se fosse libero, a `dp` fisso l'ottimo sarebbe un tubo dritto a diametro massimo.

Non toccare il resto del progetto. `../run_sistema.py` resta vuoto finché non viene chiesto.

## Comandi (da questa cartella)

```
python run_venturi.py --optimize
python -m venturi_designer.analysis.grid_study --duct results/duct_air_20C/design.json
python -m pytest tests -q -p no:cacheprovider
```

`--optimize` chiude sempre con la convergenza di griglia e stampa `T +/- errore`. Scrive `design.json`,
`thrust_estimate.json` e `grid_study.md`. Se `reliable` è falso, il valore non va usato.

## Struttura di `venturi_designer/`

- `core/`: `config`, `fluids`, `propulsion` (caso, disco, spinta, `GRID_LEVELS`)
- `geometry/`: `venturi` (profilo analitico), `morph` (due B-spline con tratto dritto del disco)
- `solver/`: griglia, proiezione, turbolenza, solver a pseudo-tempo, kernel Numba
- `optimization/`: `sizing` (ex `optimizer.py`), `adjoint` (sistema stazionario, Newton, adjoint),
  `shape_opt` (ciclo SLSQP e vincoli)
- `analysis/`: `validation`, `grid_study` (GCI ed `error_estimate`)
- `export/`, `cli.py`, `tests/`

## Scelte numeriche da non perdere

- Il solver a pseudo-tempo ristagna, quindi serve solo come primo tentativo. Lo stato finale viene da
  Newton in `optimization/adjoint.py`, che include `Q` come incognita.
- Il sistema Newton riusa i kernel del solver ma aggiunge due termini:
  - `KAPPA_FLUX = 0.1`, smorzamento dei flussi a scacchiera. Sulla griglia 64x26 pesa circa lo 0.2 %
    sulla spinta. Valori alti la sporcano: -2.2 % a 1.0, -7 % a 3.0.
  - `EPS_LIMITER`, limitatore van Albada. Con `eps2 = 0`, il default, i kernel usano van Leer.
- Continuazione pseudo-transitoria: la quantità di moto è `dF/dt = +R`, quindi il termine è
  `J - sigma*D`. Il segno opposto integra all'indietro nel tempo.
- `nu_t` non converge da sola: una cella scatta tra strato interno ed esterno di Baldwin-Lomax e la
  spinta resta su un ciclo di periodo 2. Per questo il rilassamento decresce (`RELAX_DECAY`).
- `df/dU` va a differenze centrali: la KS con `rho = 40` piega entro un passo in avanti.
- `wall_clustering = 3.5` è necessario: con 2.7 y+ è 7-12 e la griglia non converge (ordine 0.07).
- I vincoli di separazione (`CF_MIN = 5e-4`) e gli angoli limite sono default da rivedere con Samuele.

## Misurato (condotto iniziale, aria, `dp_disk = 1000 Pa`)

| Griglia | Spinta [N] | Bilancio forze [N] | y+ | Tempo |
|---|---|---|---|---|
| 64x26 | 21.363 | 21.521 | 3.96 | 21 s |
| 90x36 | 21.474 | 21.703 | 2.79 | 55 s |
| 128x51 | 21.555 | 21.834 | 1.96 | 143 s |

GCI: 21.56 +/- 0.22 N (1.04 %), estrapolata 21.73 N, ordine osservato 1.06, rapporto asintotico 1.004.

Gradiente su griglia 64x26, clustering 2.7: in laminare l'adjoint coincide con le differenze finite.
Con Baldwin-Lomax la turbolenza congelata dà uno scarto reale: `x0` 180 contro circa 100, `x12`
(uscita, dominante) 392 contro 376, coseno 0.987 su 6 variabili su 15.

## Da ricordare

1. **Spinta e bilancio di forze si allontanano raffinando la griglia:** 0.7 %, 1.1 %, 1.3 %.
   Dovrebbero avvicinarsi. La causa non è stata cercata, e il GCI non copre questo scarto.
2. Gradiente con turbolenza congelata: basta a far salire la spinta nei test, ma la convergenza
   completa di SLSQP con 40 iterazioni non è ancora stata provata. Se serve, scrivere il ripiego a
   differenze finite in parallelo.
3. La griglia `fine` (fino a 256x102) non è mai stata eseguita: tempi e comportamento sono ignoti.
4. Ordine osservato circa 1, non 2: atteso con limitatore e strato limite, ma non verificato.
5. Oscillazioni di flusso nelle celle di parete vicino all'ingresso: restano, rms circa 0.03 U.
6. Inserire i valori reali in `../input.py`, poi decidere con Samuele il vincolo anti-separazione.

## Avvertenze

- Prima di cancellare qualcosa, verificare davvero se è tracciato da git.
- Se ricompare `No module named 'venturi'`, la cache Numba è vecchia: eliminare i `.nbi`/`.nbc`.
- Nella shell i blocchi lunghi con `'''` si rompono: usare un file di script.
