# Mappa Cp sulle pale

Dalla cartella `2_ventola`, dopo il dimensionamento:

```powershell
..\1_venturi\.venv\Scripts\python.exe -m ventola_designer cp --report PERCORSO_REPORT_JSON
```

Il comando usa il candidato accettato del report senza ripetere l'ottimizzazione.
Passare il report in `00_sintesi/report.json`. Salva in `04_cfd/cp_<data_ora>/`, con un
`fan_cp_point_XX.vtp` per condizione operativa, i calcoli XFOIL e `cp_manifest.json`.
Aprire il VTP in ParaView, premere Apply e selezionare `Cp` nel menu dei colori.
La geometria standard `fan_geometry.vtp` non viene modificata.

XFOIL deve essere disponibile in PATH, indicato con `--xfoil PERCORSO`, oppure
installato in `Dimensionamento_Sistema_Propulsivo/tools/xfoil/dist/xfoil.exe`. Il pacchetto Windows
usato proviene da https://web.mit.edu/drela/Public/web/xfoil/ (licenza GPL).
Il manifest registra gli hash dell'eseguibile e del report di origine.

## Definizione e limiti

`Cp = (p - p_ref_locale)/(0.5 rho W_relativa²)` è adimensionale: la velocità
di riferimento è quella relativa alla sezione rotante, non la velocità di volo
(che nel caso statico è zero). Non fornisce una pressione assoluta nel condotto.
Si calcolano 17 sezioni distribuite fra i centri del primo e ultimo anello BEMT;
`--sections` permette di cambiarne il numero fino alle stazioni di verifica finale.
Alpha e Reynolds vengono dal BEMT; Mach usa la velocità relativa locale della pala.

La soluzione è viscosa XFOIL per profilo isolato, transizione libera, Ncrit=9,
massimo 250 iterazioni. Ncrit è un'ipotesi di postprocessing, non una misura
della turbolenza del condotto. Coordinate NACA del progetto ripannellate da XFOIL.
La stessa mappa viene ripetuta su ogni pala. I colori fra sezioni sono interpolati
sulla superficie; non vengono estrapolati alla radice o alla punta geometrica.

Solo punti presenti nella polare convergente XFOIL e con Cp finiti e coordinate
coerenti vengono accettati. Le strisce con un estremo non convergente vengono
omesse: eventuali fasce mancanti sono documentate nel manifest e nei log.
Un file può quindi rappresentare una mappa parziale. Nessuna sostituzione inviscida.

Questo postprocessing non aggiorna carichi, potenza o ottimizzazione BEMT,
che usa polari NeuralFoil. XFOIL può restituire carichi diversi; CL e CD sezionali
sono registrati nel manifest. Non sono modellate interazioni fra pale, mozzo,
parete, gioco di punta o altri effetti tridimensionali del rotore nel Venturi.

Fonte del metodo e dei comandi:
https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt
