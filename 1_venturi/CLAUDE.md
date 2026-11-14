# 1_venturi: note di ripresa

**Aggiornamento 2026-11-11.** Non valgono più, nel testo sotto: la catena comprende ora anche `2_ventola` e `3_sistema`, collegati da `../run_sistema.py` (quindi non valgono "2_ventola: non collegata, NON toccarla", "Non toccare `../2_ventola/`" né "Il collegamento con `2_ventola` è da fare"); `gap_parete` nell'input attuale è 3 mm (non 5 mm); `semiangolo_max_deg` nell'input attuale è 5 gradi (non 4; massimo deciso dal team, oltre 4-5 gradi il diffusore può separare); il raggio della bocca d'imbocco è l'input `raggio_bocca_su_D`; l'input ha ora `L_min` = 0.10 m (non c'è più "nessun vincolo di lunghezza minima"); la griglia `fine` è stata eseguita (risultati con griglia 256x102 in `risultati/TEST_Dati_CAD_Correzione/2_venturi/00_sintesi/risultati.json`).

Stato al 2026-11-03. Il venturi ora risolve il problema **inverso**: dalla spinta per ugello e
dall'ingombro del tubo trova forma, diametro e posizione della ventola e il **Δp** del disco
attuatore, che andrà allo script della ventola. Valori ancora **segnaposto** in `../input.py`.
Nessun commit fatto: Samuele valuta in locale e decide lui commit e push.
Indicazione di Samuele: restare al **primo ordine**, prima una catena che funziona; i casi in cui
il solver non converge si analizzano dopo.

## Catena del progetto

```
../input.py          CASO, SPINTA, VENTURI (unico file di input)
../run_sistema.py    0_spinta -> 1_venturi -> (2_ventola: non collegata, NON toccarla)
../0_spinta/         spinta per ugello = m a / n_ugelli (bang-bang o trapezio)
../risultati/<caso>/ 1_spinta/, 2_venturi/, caso.json, input_usato.py
```

Il nome del caso viene da `CASO["nome"]` o dagli input più un hash
(`0_spinta/spinta_designer/caso.py`, caricato dal venturi per percorso in `cli.py`).
La spinta arriva da `risultati/<caso>/1_spinta/spinta.json`, oppure da `VENTURI["T_ugello"]`.

## Decisioni prese con Samuele

- Ingombro imposto: `D_ext_max`, `L_max` del tubo (bocca d'imbocco e labbri inclusi);
  condotto interno e ventola entro `D_ext_max/2 - gap_parete` (gap 5 mm).
- Diametro e posizione della ventola li sceglie l'ottimizzatore: `R_disk` è la variabile `x[-3]`
  del vettore di progetto, la posizione segue da `L_up`. Nessun raggio sotto `R_disk`.
- Il modo "misuratore Venturi" (wizard, `sizing.py`, `validation.py`) resta; scrive in
  `../risultati/misuratore_*`.

## Comandi (da questa cartella)

```
python run_venturi.py --optimize
python -m venturi_designer.analysis.grid_study --duct <caso>/2_venturi/05_convergenza/design.json
python -m pytest tests -q -p no:cacheprovider -m "not slow"
```

## Ciclo su Δp (`optimization/target_thrust.py`)

1. `Δp0 = T/(2 A_uscita)` della forma iniziale.
2. Ottimizzazione di forma a Δp fisso (max spinta, SLSQP + adjoint), griglie `optimise`.
3. A forma fissa, secante su log T / log Δp fino a errore 1e-3; dà anche l'esponente k (≈ 1.01).
   Su forme separate T(Δp) ha rumore ~1 %: esponente accettato solo in 0.5..2, passi tenuti nella
   forcella, a fine passi si tiene il punto più vicino con un avviso.
4. Ripete 2-3 finché Δp cambia meno di `tol_dp`.
5. Studio di griglia sulle griglie `verify`, poi Δp ricalcolato sulla griglia più fine.
   Errore su Δp = Δp · GCI% / k.

`design.json` contiene tutto il caso (Δp incluso): lo studio di griglia non rilegge `input.py`.

## Uscite: `risultati/<caso>/2_venturi/`

`00_sintesi` (RISULTATO.md, risultati.json per la ventola), `01_grafici` (14 svg), `02_excel`,
`03_cad` (tubo, fluido, zona_disco in STEP e STL; patch STL del fluido; DXF; CSV),
`04_cfd` (vts del piano meridiano, nuvola di punti CSV; il 3D si ottiene in ParaView), `05_convergenza`. Le sottocartelle vengono svuotate a ogni corsa.
STEP: la parete è la B-spline esatta (`MorphedGeometry.bspline_curves`, poli alle ascisse di
Greville); STL con tolleranza di corda 0.005 mm, chiusi (verificato con pyvista).

## Misurato (input segnaposto: 10 kg, 1 m in 10 s, 2 ugelli -> 0.2 N; tubo 70 x 150 mm)

Griglie 64x26 / 90x36 / 128x51: Δp = 37.84 ± 0.03 Pa, spinta 0.2000 N, GCI 0.08 %, affidabile,
ordine 1.19, ventola 59.9 mm, Q = 21.3 L/s, P = 0.81 W, 182 s in tutto. La forma ottima è un
tubo **dritto e corto** al diametro massimo: a spinta data il Δp minimo vuole l'uscita più larga,
e senza un vincolo di lunghezza minima l'attrito spinge a accorciare. Atteso dalla fisica del modello.

## Scelte numeriche da non perdere

- Partenza a freddo: la marcia nel tempo tiene fissa la portata d'ingresso; da una portata troppo
  lontana Newton non converge. `START_FLOW = (0.85, 0.6, 0.45, 1.0)` della portata ideale, in ordine.
  Con 0.85 soltanto, il tubo dritto a R_int_max non convergeva.
- Ogni soluzione non convergente a caldo riparte da freddo; l'ottimizzatore accetta come migliore
  solo forme con flusso convergente.
- Griglie sotto 64x26 (40x18) non convergono: non usarle nei test.
- Partenza calda tra Δp diversi (`DuctProblem.warm_start`): incognite scalate con il getto ideale,
  `nu_t` scalata dello stesso fattore.
- Forma iniziale: semicoseni con pendenza massima 0.6 di quella ammessa (`START_SLOPE`), così parte
  sempre dentro i vincoli (provata da Ø40x60 a Ø170x600 mm).
- `bell_envelope` in `export/cad.py` è la formula chiusa dell'ingombro della bocca d'imbocco usata
  come vincolo; coincide al micron con il tubo CAD.
- Restano valide le note del solver: `KAPPA_FLUX = 0.1`, van Albada, `RELAX_DECAY` su `nu_t`,
  `df/dU` centrale, `wall_clustering = 3.5`.
- Le fixture dei test del solver usano `reference_design` (disco 100 mm, cono 30°/5°) e
  `Re_ref = V*0.10/nu`, le condizioni di prima.
- `test_no_oddeven_mode_left` e il gradiente laminare con k = 0 **fallivano già sul commit
  b1df9d1** (prima di questo lavoro): segnati `xfail`, da analizzare quando si esce dal primo ordine.
- Studio di griglia: se le tre spinte differiscono meno dello 0.05 % (`FLAT_TOL`) il risultato è
  indipendente dalla griglia, l'errore è 1.25 volte la dispersione e l'ordine non si calcola
  (prima dava ordine 6.7 e "non affidabile").

## Da ricordare

1. Spinta e bilancio delle forze: 0.1 % di scarto sulle griglie coarse, 1.3 % su 90x36..180x72
   (0.19993 contro 0.19743 N), come già notato prima: il GCI non copre questo scarto.
2. Nessun vincolo di lunghezza minima del condotto né di mozzo della ventola: chiederlo a Samuele
   se il tubo corto non va bene.
3. La griglia `fine` (fino a 256x102) non è mai stata eseguita.
4. Il collegamento con `2_ventola` è da fare (Δp, diametro e portata sono in `risultati.json`).

## Avvertenze

- Non toccare `../2_ventola/`. Comandi fuori dalla cartella del progetto: chiedere prima.
- Se ricompare `No module named 'venturi'`, la cache Numba è vecchia: eliminare i `.nbi`/`.nbc`.
- Nella shell i blocchi lunghi con `'''` si rompono: usare un file di script.

**Aggiornamento 2026-11-14.** `VENTURI["D_ventola"]` vale anche per l'ottimizzazione di forma
(`griglia+forma`, `slsqp`): numero [m] o `"max"` (massimo da `inlet_radius_limit` e `R_int_max`,
`cli.resolve_fan_diameter`) tengono fisso `R_disk` (`PropulsionCase.R_disk_fisso`: in `optimise` la
variabile `x[-3]` è tolta dal vettore di SLSQP); `None` = libero come prima. `../run_sistema.py`
la usa per la ventola adattiva: se la ventola fallisce rifà il venturi con D crescente fino al massimo.

## Revisione 2026-11-07 (richiesta in 7 punti)

- Spinta: T = Σ(ρF²/A + (p − p_amb)A) − ρQV0 all'uscita (termine di pressione 0 per la condizione
  d'uscita); controllo con `momentum_balance`, `thrust_check_pct` e β = T/(ṁ v_media) nel report.
- Ingresso: profilo PIATTO (`adjoint.FLAT_INLET`), p_t = 0 come media. Prima era il profilo
  sviluppato di Nikuradse (asse/media 1.24, p_t +24 Pa sull'asse). Restano fino a +8 Pa di p_t
  nelle celle vicine alla parete a z < 5 mm: stesso difetto pari/dispari del τ_w a dente di sega,
  NON risolto alzando KAPPA_FLUX (0.3 e 0.6 peggiorano τ_w). Estendere il dominio alla bocca
  d'imbocco richiede una griglia diversa.
- Curva della ventola: `optimization/fan_curve.py`, `VENTURI["curva_ventola"]`; il punto di lavoro
  e la spinta diventano risultati (secante su dp = curva(Q(dp))).
- Ottimizzatore di default: `optimization/scan.py`, scansione D_uscita x L_diffusore con D ventola
  fisso (`VENTURI["D_ventola"]`); SLSQP resta con `ottimizzatore: "slsqp"`.
- Semiangolo massimo del diffusore 4° (`semiangolo_max_deg`), τ_w minimo nel diffusore per caso.
- Limiti del disco documentati in `core/propulsion.py`; `mozzo_su_D_disco` e `perdita_swirl`.
