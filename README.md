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

Serie di casi. Qualsiasi valore di `SPINTA`, `VENTURI`, `VENTOLA`, `SISTEMA` (anche nei dizionari annidati, come `VENTOLA["statore"]["presente"]`) può essere una stringa con più valori separati da `;`, ad esempio `"massa": "4; 6; 8"`, `"D_ext_max": "None; 0.07"`, `"profilo": "bang_bang; trapezio"`. Ogni parte è letta con `ast.literal_eval` (numeri, `None`, `True`, liste) e resta testo se non è un letterale; una stringa senza `;` è un valore normale. `SISTEMA["combinazioni"]` sceglie `"tutte"` (prodotto delle chiavi con più valori, predefinito) o `"accoppiate"` (l'i-esimo valore di ogni chiave con l'i-esimo delle altre; liste di lunghezza diversa danno errore). Ogni caso è una catena completa (con le varianti statore, se attive) in `risultati/<nome>/<etichetta>/`, con `input_usato.py` e `RIEPILOGO.md` propri; l'etichetta è del tipo `massa_4` o `massa_4__D_ext_max_0.07`. `<nome>` è `CASO["nome"]` oppure il nome automatico con le chiavi variabili indicate da `V` e un hash calcolato sull'ingresso con le stringhe originali, quindi stabile. In `risultati/<nome>/` si trovano anche `RIEPILOGO.md` (tabella dei casi con stato) e `confronto_casi.xlsx` (masse e confronto, `sistema_designer.masse`). Un caso che fallisce non ferma gli altri. `SISTEMA["densita_kg_m3"]` (PLA, 1240) e `SISTEMA["riempimento"]` (1.0) servono alla stima della massa di tubo e pale, scritta in un Excel anche per un caso singolo.

```bash
python run_sistema.py --elenca        # casi ed etichette, senza eseguire nulla
python run_sistema.py                 # tutta la serie
python run_sistema.py --solo ventola  # un passo in ogni caso
python run_sistema.py --solo masse    # riscrive solo gli Excel delle masse
```

Indicatori a posteriori di una ventola (sforzo centrifugo alla radice, squilibrio, velocità di punta, inerzia), dalla cartella `2_ventola`; `--pale` limita i numeri di pale confrontati e `--scrivi` scrive `confronto_pale.json` e `CONFRONTO_PALE.md` accanto al report:

```bash
python -m ventola_designer.indicatori ..\risultati\<caso>\3_ventola\00_sintesi\report.json --scrivi
```

Durate: il passo più lungo è `1_venturi` (minuti: ottimizzazione di forma più studio di griglia). `0_spinta` e `--solo riepilogo` sono immediati; la ventola dipende dal numero di coppie profilo/pale e da `jobs`. Senza dati misurati non si danno altre cifre.

Processi in parallelo (`SISTEMA["processi"]`). È un tetto unico sul NUMERO TOTALE di processi della corsa: `None` = automatico, `min(core fisici, floor(0.6 × RAM libera / 1.5 GB))` e almeno 1 (RAM libera con `psutil` se installato, altrimenti con `GlobalMemoryStatusEx`); `1` = tutto in sequenza, il codice di prima (ogni caso della scansione parte a caldo dal precedente). Il tetto è un budget che si divide andando verso l'interno: ogni livello con più lavori indipendenti (casi di una serie, poi varianti Statore/NoStatore, poi i lavori del venturi: casi della scansione, alternative, punti della scansione dell'uscita, studio di griglia `jobs`, ventola `jobs`) usa `min(lavori, budget)` processi e dà a ciascuno `budget // processi`; dentro un processo con budget 1 tutto va in sequenza. Con 12 processi, due varianti e una scansione di 20 casi: 2 catene da 6 processi ciascuna. Con più processi ogni caso della scansione e ogni punto della scansione dell'uscita parte da freddo (sequenza `START_FLOW`) invece che dal caso precedente: stessi risultati entro la tolleranza del solutore. Ogni catena o caso eseguito in un processo proprio scrive il suo output in `log.txt` nella sua cartella; a video restano inizio, fine e codice di uscita di ognuno e il traceback degli errori. Le passate intermedie della fascia non fanno lo studio di griglia (serve solo come banda d'errore): il Δp finale è comunque calcolato con `match_thrust` sulla griglia più fine; nei dati della passata c'è la nota "studio di griglia solo nella passata finale", e la passata finale è invariata.

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

Decisione massa → potenza. A fine caso e fine serie lo script dice quale variante conviene mettendo la massa sulla stessa scala della potenza: ogni grammo va spinto anch'esso, la spinta richiesta è proporzionale alla massa totale e a geometria fissa la potenza cresce come la spinta^1.5 (disco attuatore). Per ogni candidato `m_tot = massa_rif + n_propulsori·(m_unità − m_unità_rif)` e `P_eff = P_albero·(m_tot/massa_rif)^esponente` (stessa formula per l'energia della manovra), con `massa_rif = SPINTA["massa"]` (veicolo con la variante di riferimento, `Statore`), `n_propulsori = SISTEMA["n_propulsori"]` (`None` = `SPINTA["n_ugelli"]`) ed `esponente = SISTEMA["esponente_potenza_massa"]` (1.5). Vince la `P_eff` minore, a parità entro 0.5 % la più leggera. Il verdetto, con i numeri e la massa di pareggio, è nel foglio `Decisione` di `RIEPILOGO_masse.xlsx` e di `5_confronto_statore/confronto_statore.xlsx` (classifica generale variante × lunghezza del tubo in cima, poi Statore/NoStatore, poi la tabella di compromesso di ogni lunghezza rispetto all'ottimo), nella sezione Decisione di `5_confronto_statore/RISULTATO.md` e di `RIEPILOGO.md`, nel JSON (`decisione`) e a video. Nella serie, `confronto_casi.xlsx` (foglio `Decisione`) dà il migliore di ogni caso con i delta sul primo caso e, solo se `SPINTA` è uguale in tutti i casi, la classifica fra i casi; con `SPINTA` diversa le missioni sono diverse e non si classifica.

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
