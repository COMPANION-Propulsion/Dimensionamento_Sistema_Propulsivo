# 2_ventola: dimensionamento della ventola

Dal Δp, dal diametro e dalla portata del Venturi la ventola trova profilo, numero
di pale, mozzo, corde, calettamenti e giri con la minima potenza all'albero
(BEMT a portata imposta + SLSQP). Poi calcola la curva spinta–potenza e scrive
il CAD pronto per CAD e CFD.

## Come si usa

Nella catena completa, dalla radice del progetto:

```powershell
python run_sistema.py
```

Le impostazioni stanno in `VENTOLA` di `input.py`. `run_sistema.py` scrive
l'input della ventola in `risultati/<caso>/input_ventola.json`, con il percorso
del Venturi dello stesso caso, e i risultati in `risultati/<caso>/3_ventola/`.

Da sola, dalla cartella `2_ventola`, con un input JSON nello stesso formato:

```powershell
python -m ventola_designer size --input PERCORSO.json [--jobs N] [--output CARTELLA]
python -m unittest discover -s tests
```

`--jobs N`: coppie profilo/pale in parallelo (default: tutti i core). Senza
`--output` i risultati vanno nel `3_ventola/` del caso Venturi importato, o in
una cartella datata di `ventola_output/` se l'input non viene da un caso.

## Cartelle

| Percorso | Contenuto |
|---|---|
| `ventola_designer/` | codice: BEMT, geometria, ottimizzatore, CAD, curva di potenza, export |
| `ventola_designer/airfoils/` | catalogo dei profili e polari NeuralFoil (Re 2 000–150 000) |
| `tests/` | test automatici |
| `docs/` | guide: [input dal Venturi](docs/VENTURI_INPUT.md), [ottimizzazione](docs/OTTIMIZZAZIONE.md), [mappa Cp](docs/CP_MAP.md) |
| `tools/xfoil/` | XFOIL 6.99 per Windows (GPL), usato dalla mappa di Cp |
| `input_esempio.json` | caso del vecchio modo "rotore libero" (spinta imposta), usato dai test |
| `ventola_output/` | esecuzioni manuali fuori da un caso |

Le dipendenze sono in `../requirements.txt`.

## Risultati (`risultati/<caso>/3_ventola/`)

| Cartella | Contenuto |
|---|---|
| `00_sintesi` | `RISULTATO.md` (da leggere per primo), `report.json`, `curva_potenza.json` |
| `01_grafici` | `preview.svg` (pala), `curva_potenza.svg` (spinta dell'ugello da 0 a P_max) |
| `02_excel` | `sections.csv` (corda e calettamento per raggio), `curva_potenza.xlsx` |
| `03_cad` | `ventola_A` e `ventola_B_speculare` (mozzo + pale, STEP e STL), `pala`, `CAD_info.json`, `blade_points.csv`, profilo `.dat` |
| `04_cfd` | file ParaView delle grandezze radiali BEMT, mappe di Cp |
| `05_convergenza` | `optimization.json`: tutti i candidati e le verifiche |

**CAD.** Solidi validi in mm, nel riferimento del condotto: asse X lungo il
flusso, x = 0 al piano d'ingresso del condotto, ventola già al suo posto. Si
importano insieme a `2_venturi/03_cad/tubo` e `fluido` senza spostamenti. Il
diametro delle pale è ridotto del gioco di punta (`VENTOLA["gioco_punta_m"]`).
`ventola_A` gira in senso orario vista da valle, `ventola_B_speculare` in senso
antiorario: montate su ugelli vicini, i momenti di reazione si annullano.

**Curva di potenza.** Condotto e pale fissi, giri variabili: per ogni regime si
trova dove la ventola e il condotto danno lo stesso Δp. Si leggono la spinta
dell'ugello (tubo + pale) e quella sulle sole pale, da 0 a `VENTOLA["potenza_max_W"]`
(None = il doppio della potenza di progetto).

## Modello e limiti

- Requisito sul Δp **assiale** (swirl escluso), lo stesso del disco del Venturi:
  senza statore lo swirl esce col getto e non dà spinta.
- **Statore** (`VENTOLA["statore"]`): schiera di pale fisse dopo il rotore,
  progettata anello per anello (`stator.py`): CL che serve a togliere lo swirl,
  incidenza e CD dalle polari, perdita di profilo, stallo se il CL non basta.
  Entra nell'ottimizzazione del rotore, va nel CAD e annulla la coppia netta.
  A Reynolds molto bassi l'attrito dello statore può costare più dello swirl che
  recupera: il report lo mostra (recupero negativo).
- Mozzo fra `VENTOLA["mozzo_su_D"]` volte il diametro della ventola.
- Velocità uniforme sull'anello libero dal mozzo, ingresso senza swirl, densità
  costante. Perdite al mozzo, alle pareti e di gioco di punta non modellate.
- Polari numeriche NeuralFoil, non validate sperimentalmente. Ricerca SLSQP
  locale: il minimo globale non è garantito.
- Il modo storico a spinta del rotore libero (`input_esempio.json`) resta per i
  test e per confronto; nella catena si usa solo `pressure_flow`.
