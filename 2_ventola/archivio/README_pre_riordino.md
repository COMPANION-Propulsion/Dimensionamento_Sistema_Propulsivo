# Prototipo della ventola

Versione attuale: geometria parametrica, polari numeriche multi-Reynolds, BEMT rotorico e ottimizzazione locale SLSQP di mozzo, corde, calettamenti e regimi per punto operativo. Le polari sono generate dalle coordinate del generatore mediante NeuralFoil/AeroSandbox, con approssimazione interna Kulfan. Non sono dati sperimentali. Il modello resta preliminare.

Per ottimizzare ed esportare la geometria risultante: `.\.venv\Scripts\python.exe -m ventola_designer.optimizer --profiles NACA4412 --blades 2`. Senza filtri vengono confrontati tutti i candidati del caso. Vedere [OTTIMIZZAZIONE.md](OTTIMIZZAZIONE.md) per limiti, vincoli, verifiche e output. I comandi geometrici e `bemt_trial` descritti sotto restano strumenti separati per il seme e la scansione.

## Avvio

Dalla cartella che contiene questo documento, con Python 3.10 o successivo:

```powershell
python -m ventola_designer --validate-only
python -m ventola_designer --profile NACA4412 --blades 4
python -m ventola_designer.bemt_trial
python -m unittest discover -s tests -v
```

Geometria e BEMT con tabelle già generate non richiedono dipendenze esterne. Per rigenerare le polari:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-polars.txt
.\.venv\Scripts\python.exe -m ventola_designer.generate_polars
```

`--input` seleziona un altro caso JSON nel comando geometrico; la prova `bemt_trial` usa esplicitamente `input_esempio.json`. `--output` sceglie una cartella nuova o vuota per la geometria; normalmente il programma crea una cartella datata sotto `ventola_output`. L'esempio usa valori provvisori dichiarati nel JSON.

`--profile` e `--blades` scelgono il seme da visualizzare, non la soluzione migliore. Senza opzioni viene usato il primo candidato del caso. Il generatore produce automaticamente corda e calettamento illustrativi; in futuro saranno parametri dell'ottimizzatore.

## Risultati

- `preview.svg`: vista assiale delle pale e sezioni del catalogo.
- `sections.csv`: raggio, corda e calettamento.
- `blade_points.csv`: coordinate tridimensionali delle sezioni di una pala.
- `blade_surface.obj`: superficie triangolata di una pala, in metri; aperta alla radice e alla punta, non è un solido pronto per produzione.
- File `.dat`: coordinate analitiche normalizzate di tutti i profili del catalogo.
- `report.json`: input, seme geometrico e limiti; prestazioni non calcolate indicate come `null`.

Ogni esecuzione crea anche `paraview/`. Aprire `fan_geometry.vtp` per vedere tutte le pale della geometria esportata e `results.pvd` per i campi radiali di ogni candidato calcolabile e punto operativo. I file `.vtp` contengono alfa, Reynolds, Mach, induzioni e fattori di perdita sugli anelli BEMT; non rappresentano un campo CFD nel volume. `manifest.json` associa ciascun file alla coppia profilo-pale, al punto operativo e allo stato di accettazione.

Asse del rotore Z. Il calettamento è misurato dal piano di rotazione e applicato al quarto di corda. Le sezioni sono definite sullo sviluppo del cilindro e avvolte sul loro raggio, mantenendo ogni punto entro il diametro imposto. La vista mostra un mozzo schematico; il suo solido e gli attacchi non sono modellati. Il seme non è verificato per interferenze tra pale o resistenza meccanica.

Le coordinate sono generate analiticamente, non scaricate da UIUC. Fonti delle formule: [PDAS spessore NACA](https://www.pdas.com/naca456thick4.html) e [PDAS linea media](https://www.pdas.com/naca456mean2.html). Si conserva lo spessore finito del bordo d'uscita. Ogni tabella conserva coordinate e hash: il BEMT rifiuta un profilo o un generatore geometrico incompatibile.

La velocità in ingresso del caso d'esempio resta da associare con precisione alla sezione fisica del futuro solutore: zero velocità di avanzamento non significa zero flusso attraverso un rotore in funzione. Questa versione geometrica non usa la velocità per prevedere prestazioni.

La prova `bemt_trial` interpreta la velocità immessa come velocità assiale lontano dal rotore, coerente con il bilancio di quantità di moto del suo modello. È una convenzione temporanea diversa dall'input originariamente chiamato velocità *all'ingresso della ventola* e va chiarita nella prossima revisione del modello. La prova usa una scansione grossolana NACA4412, non SLSQP: corda e mozzo restano quelli del seme e il regime è comune ai due punti. Il risultato è in `ventola_output/bemt_multire.json` e contiene spinta rotorica, coppia, potenza, controllo dei residui e confronto fra 32 e 64 anelli.

Le nuove tabelle coprono Re 5000–150000, Mach 0–0.5 e alpha -12°–24°, con Ncrit=9. Il BEMT interpola linearmente in alpha, log(Re) e Mach e rifiuta estrapolazioni o nodi con `analysis_confidence < 0.5`. La soglia è un criterio di screening del progetto, non una garanzia di accuratezza. Un rifiuto durante l'iterazione non dimostra che non esista una soluzione fisica.

Fonte del modello: [NeuralFoil](https://github.com/peterdsharpe/NeuralFoil), attraverso AeroSandbox con correzioni di compressibilità dei coefficienti. Il bilancio di quantità di moto resta incomprimibile. Perdite di punta/mozzo, interazioni di cascata, condotto e motore non sono modellati: la spinta calcolata riguarda solo il rotore e non la spinta complessiva installata. Occorrono ancora un modello adeguato e una validazione indipendente prima del dimensionamento definitivo.

La vecchia polare [SUAVE NACA4412 Re=100000](https://github.com/suavecode/Tutorials/blob/master/Airfoils/Polars/NACA_4412_polar_Re_100000.txt) e `bemt_exploratory.json` restano come storico, non sono più usati dalla prova.
