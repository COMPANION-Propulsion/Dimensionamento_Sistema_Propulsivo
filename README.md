# Dimensionamento del sistema propulsivo

Progetto COMPANION (Università di Pisa): un cubo di 4.5 kg in moto libero, spinto da ventole intubate, come esperimento per un volo parabolico ESA con una variante per la ISS. Questo repository dimensiona la propulsione di un ugello (ventola intubata) a partire dal requisito di missione: spostamento, tempo e massa danno la spinta per ugello, da questa si ricavano condotto e ventola, e infine si verifica il sistema completo.

## Catena di calcolo

```
input.py (CASO, SPINTA, VENTURI, VENTOLA)
   |
   v
0_spinta   missione -> spinta per ugello
   |
   v
1_venturi  spinta, ingombro -> condotto assialsimmetrico + disco attuatore (Δp, portata, Ø ventola)
   |
   v
2_ventola  Δp, Ø, portata -> rotore, statore, giri, CAD, strato limite
   |
   v
3_sistema  condotto + ventola -> potenza, curva di potenza, statore sì/no, assieme CAD, note e limiti
   |
   v
RIEPILOGO.md
```

| Passo | Ingresso | Uscita |
|---|---|---|
| `0_spinta` | distanza, tempo, massa, numero di ugelli, profilo di moto (`bang_bang` o `trapezio`), fattore di margine, disturbo residuo | spinta della faccia e spinta per ugello |
| `1_venturi` | spinta per ugello, ingombro del tubo | forma del condotto assialsimmetrico con disco attuatore, che dà Δp, portata e diametro della ventola; studio di griglia con errore su Δp; CAD del tubo |
| `2_ventola` | Δp, diametro e portata del Venturi | BEMT a portata imposta, ottimizzazione SLSQP su coppie profilo/numero di pale (corde, calettamenti, mozzo, giri), statore, CAD delle pale, strato limite delle sezioni con XFOIL |
| `3_sistema` | risultati di condotto e ventola | potenza nella manovra, curva di potenza, confronto con/senza statore, condotto con la ventola vera, assieme CAD, confronto terra/volo alla pressione di cabina, note e limiti |

Ogni passo scrive solo ciò che gli appartiene: quello che richiede insieme condotto e ventola sta in `4_sistema/`.

## Installazione

Il codice è scritto e provato con Python 3.14 (3.14.7). Dalla radice del progetto:

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` fissa le versioni usate (numpy, scipy, numba, matplotlib, openpyxl, pyvista, cadquery, ezdxf, neuralfoil, aerosandbox, pytest).

XFOIL 6.99 non è su PyPI ed è incluso in `2_ventola/tools/xfoil/dist/xfoil.exe` (Windows, GPL). `run_sistema.py` lo usa per la mappa di Cp e lo strato limite di rotore e statore. Se manca, quella parte viene saltata con un avviso: il dimensionamento resta valido.

## Uso

Tutti gli ingressi sono in `input.py`, in quattro dizionari. I valori presenti sono quelli dell'ultimo caso lanciato.

- `CASO`: `nome` della cartella dei risultati (`None` = nome costruito dagli ingressi più un hash); `sovrascrivi` permette di riusare una cartella con nome anche se gli ingressi sono cambiati.
- `SPINTA`: `distanza`, `tempo`, `massa`, `n_ugelli` (ugelli che spingono su una faccia), `profilo`, `frazione_crociera` (solo `trapezio`), `fattore_margine`, `disturbo_residuo_g` (accelerazione residua del volo parabolico che la spinta deve vincere).
- `VENTURI`: punto di lavoro (`fluid`, `V0`, `p_amb`, `p_cabina`); ingombro (`D_ext_max`, `L_max`, `L_min`, `gap_parete`, `spessore_parete`, `raggio_bocca_su_D`); ventola nel condotto (`semiangolo_max_deg`, `L_disk`, `D_disk_min_ratio`, `D_ventola`); `T_ugello` (`None` = letta da `1_spinta/spinta.json`); `curva_ventola` (`None` = Δp fisso); ottimizzatore (`griglia` o `slsqp`), griglia di calcolo (`coarse`, `medium`, `fine`), `jobs`, `max_iter`, `tol_dp`.
- `VENTOLA`: limiti di ricerca della ventola. Chiavi principali: `mozzo_su_D` (diametro del mozzo sul diametro della ventola), `statore` (`presente`, `pale`, `solidita`, `profilo`, `gioco_assiale_m`), `giri_min_max_rpm`, `calettamento_min_max_deg`, `corda_su_D_min_max`, `pale_candidate`, `profili_candidati`, `nodi_pala`, `gioco_punta_m`, `potenza_max_W` (fine della curva di potenza, `None` = doppio della potenza di progetto), `jobs`, `sizing`. Diametro, Δp, portata e densità arrivano dal Venturi dello stesso caso. Una chiave sconosciuta in `VENTOLA` o in `VENTOLA["statore"]` dà errore.

L'hash del caso dipende solo da `SPINTA` e `VENTURI` (`0_spinta/spinta_designer/caso.py`, `load_input`: `VENTOLA` non entra nell'hash). Cambiando solo `VENTOLA` si riusa quindi la cartella del caso e si rilancia la ventola senza ricalcolare il condotto. Con `CASO["nome"]` fissato e `sovrascrivi: True` la cartella è comunque quella indicata.

`run_sistema.py` scrive l'ingresso della ventola da `VENTOLA` in `risultati/<caso>/input_ventola.json`, con il percorso esplicito del Venturi di quel caso.

Catena completa:

```bash
python run_sistema.py
```

Un solo passo (`spinta`, `venturi`, `ventola`, `sistema`):

```bash
python run_sistema.py --solo ventola
```

Riscrittura del solo `RIEPILOGO.md` e del confronto per numero di pale, senza calcoli:

```bash
python run_sistema.py --solo riepilogo
```

Indicatori a posteriori di una ventola (sforzo centrifugo alla radice, squilibrio, velocità di punta, inerzia), dalla cartella `2_ventola`; `--pale` limita i numeri di pale confrontati e `--scrivi` scrive `confronto_pale.json` e `CONFRONTO_PALE.md` accanto al report:

```bash
python -m ventola_designer.indicatori ..\risultati\<caso>\3_ventola\00_sintesi\report.json --scrivi
```

Durate: il passo più lungo è `1_venturi` (minuti: ottimizzazione di forma più studio di griglia). `0_spinta` e `--solo riepilogo` sono immediati; la ventola dipende dal numero di coppie profilo/pale e da `jobs`. Senza dati misurati non si danno altre cifre.

I passi si fermano al primo errore (codice diverso da 0 e 3); il codice 3 di `3_sistema` indica passi completati con avvisi annotati in `RISULTATO.md`. In ogni caso `RIEPILOGO.md` viene scritto.

## Risultati

Tutto finisce in `risultati/<caso>/`:

```
risultati/<caso>/
  caso.json              nome e hash del caso
  input_usato.py         copia di input.py usata
  input_ventola.json     ingresso della ventola generato da VENTOLA
  RIEPILOGO.md           i numeri chiave dei quattro passi in una pagina
  1_spinta/              RISULTATO.md, spinta.json, grafici/, excel/
  2_venturi/             00_sintesi, 01_grafici, 02_excel, 03_cad, 04_cfd, 05_convergenza
  3_ventola/             00_sintesi, 01_grafici, 02_excel, 03_cad, 04_cfd, 05_convergenza
  4_sistema/             00_sintesi, 01_grafici, 02_excel, 03_cad, 04_cfd
```

In ogni passo successivo al primo, `00_sintesi` contiene `RISULTATO.md` (da leggere per primo) e i JSON con i numeri; `01_grafici` le figure SVG; `02_excel` le tabelle; `03_cad` i solidi STEP e STL; `04_cfd` i file per ParaView; `05_convergenza` lo studio di griglia (Venturi) e tutti i candidati dell'ottimizzazione (ventola). I solidi di Venturi, ventola e sistema sono nello stesso riferimento (asse X lungo il flusso, x = 0 al piano d'ingresso del condotto).

In `3_ventola/00_sintesi/` sono scritti anche `confronto_pale.json` e `CONFRONTO_PALE.md`: la migliore ventola accettata per ciascun numero di pale, a confronto su potenza, giri, coppia, rendimento, corda, spessore minimo, sforzo centrifugo alla radice, squilibrio e inerzia. Si scrivono in automatico alla fine del passo ventola e di nuovo quando si riscrive il riepilogo.

Come esempio di riepilogo vedi `risultati/RUN_POST_FIX_11-11/RIEPILOGO.md` (i numeri dipendono dal caso e dagli ingressi).

`risultati/` non è sotto git e non va cancellata né svuotata senza chiedere: contiene calcoli lunghi non riproducibili in pochi secondi. Alcune sottocartelle di un passo vengono svuotate a ogni sua nuova esecuzione.

## Test

Ogni suite si lancia dalla cartella del passo.

`0_spinta`:

```bash
python -m pytest tests -q -p no:cacheprovider
```

`1_venturi` (esclude il test dell'intera catena, marcato `slow`; circa 3 minuti, 2 test `xfail` noti):

```bash
python -m pytest tests -q -p no:cacheprovider -m "not slow"
```

`2_ventola`:

```bash
python -m pytest tests -q -p no:cacheprovider
```

`3_sistema`:

```bash
python -m pytest tests -q -p no:cacheprovider
```

## Limiti del modello

- BEMT su anello uniforme, senza perdite di punta e secondarie, con velocità uniforme sull'anello libero dal mozzo e ingresso senza swirl: il rendimento è ottimistico. Perdite al mozzo, alle pareti e di gioco di punta non sono modellate.
- Polari dei profili numeriche (NeuralFoil) a basso Reynolds, non validate sperimentalmente.
- Ottimizzatore SLSQP locale: l'ottimo globale non è garantito. Molte coppie profilo/pale vengono scartate quando SLSQP si ferma su punti BEMT non validi.
- Il condotto con la ventola vera è assialsimmetrico 2D: swirl e corpo del mozzo non sono simulati. Il dimensionamento usa invece un disco uniforme, e lo scarto di spinta tra i due modelli è riportato nei risultati.
- La bocca d'imbocco è fuori dal dominio di calcolo del condotto; l'imbocco è piatto e il calcolo è del primo ordine.
- Potenza solo all'albero: quella elettrica richiede il rendimento di motore e regolatore.
- Dimensionamento a 101325 Pa (`p_amb`) mentre la cabina è a circa 82500 Pa (`p_cabina`): il confronto terra/volo in `4_sistema` usa le leggi di similitudine a geometria fissa e non include il calo di rendimento delle pale per il Reynolds più basso.
- Il dimensionamento riguarda una faccia: con più assi accesi insieme il picco di potenza e il disturbo residuo vanno verificati fuori da questo codice (vedi `4_sistema/00_sintesi/note_e_limiti.json`).

## Struttura del repository

| Voce | Contenuto |
|---|---|
| `input.py` | unico file di ingresso: CASO, SPINTA, VENTURI, VENTOLA |
| `run_sistema.py` | esegue la catena completa o un passo; scrive `RIEPILOGO.md` |
| `requirements.txt` | dipendenze con le versioni provate |
| `0_spinta/` | `spinta_designer` (profilo di moto, spinta, nome del caso in `caso.py`), `run_spinta.py`, `tests` |
| `1_venturi/` | `venturi_designer` (solver del flusso, ottimizzazione, CAD), `run_venturi.py`, `tests`, `CLAUDE.md` (note di ripresa) |
| `2_ventola/` | `ventola_designer` (BEMT, statore, ottimizzatore, CAD, indicatori), `docs/`, `tools/xfoil/`, `tests`, `README.md` proprio |
| `3_sistema/` | `sistema_designer` (potenza di manovra, confronto statore, assieme, note), `tests` |
| `risultati/` | uscite di tutti i casi, fuori da git |
