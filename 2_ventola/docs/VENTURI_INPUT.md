# Ventola a portata imposta dal Venturi

Il comando `size` legge per default `input_venturi.json` nella cartella del progetto,
anche se avviato da un'altra directory. Il campo
`operating_points[].venturi_result` è impostato a `"auto"`: a ogni avvio seleziona
il file modificato più recentemente fra
`../risultati/*/2_venturi/00_sintesi/risultati.json`, con ricerca relativa
all'installazione di `2_ventola`. A parità di data usa l'ordine del percorso.
Stampa il file scelto prima del calcolo e ne registra percorso e hash nel report.
Non ricava dati da risultati intermedi; se l'export scelto è corrotto o incoerente,
si ferma senza passare silenziosamente a un caso più vecchio.

È ancora possibile specificare il percorso di un export preciso al posto di
`"auto"`. I percorsi relativi si risolvono
rispetto al file di input della ventola. Il programma legge solo il JSON;
non importa, esegue o modifica codice del Venturi.

Se nessun export finale è disponibile, il programma indica che occorre completare
il calcolo Venturi. Non viene avviato automaticamente il Venturi.
La durata 1 s e i limiti
di mozzo/giri sono impostazioni iniziali modificabili, non dati importati.
Per un unico punto, la durata scala l'energia senza modificare il minimo di potenza.

| Dato Venturi | Utilizzo |
|---|---|
| ventola.D_ventola_m | Diametro esterno imposto |
| ventola.dp_disk_Pa | Pressione totale minima richiesta |
| ventola.portata_m3_s | Portata volumetrica da conservare |
| ventola.V_disco_m_s | Controllo Q = V disco * pi D²/4 |
| ventola.densita_kg_m3 | Densità costante del calcolo |

Non si usa `flusso.salto_p0_disco_Pa` al posto di `dp_disk_Pa`: il primo è
un risultato del campo CFD, il secondo è il requisito del disco esportato.
Il percorso, l'hash del file sorgente e gli stati numerici a monte sono salvati
nel report. Importare un file non equivale a dichiararlo validato.

Temperatura e pressione assoluta dell'aria restano nell'input ventola, perché
l'export Venturi non contiene tutti i dati termodinamici. La densità importata
è usata direttamente; viscosità e velocità del suono derivano dalla temperatura.
Il contratto qui implementato è per aria secca: usare condizioni coerenti con
il caso Venturi. Il JSON Venturi non identifica da solo il fluido.

Per più condizioni usare più punti, ciascuno con sorgente e durata proprie.
Il diametro importato deve essere lo stesso per tutti. Un diametro manuale
discordante viene rifiutato, così come duplicati discordanti di Q, dp o densità.
In alternativa all'importazione si possono specificare nel JSON:
`rotor.outer_diameter_m`, `volume_flow_m3_s`,
`minimum_total_pressure_rise_Pa` e facoltativamente `density_kg_m3`.
Il modo deve essere `design_mode: pressure_flow`.

## Modello e convenzioni

Per ogni candidato geometrico:

- area libera A = pi (D² - D_mozzo²)/4;
- velocità assiale Va = Q/A, uniforme e costante attraverso il rotore;
- ingresso senza componente tangenziale;
- swirl medio sul piano delle pale b, swirl in uscita 2b.

Si conservano quindi portata e densità del Venturi mentre varia la velocità
sulle pale. Non si applica l'induzione assiale del precedente rotore libero.
Per ogni anello di raggio r, le forze per unità radiale delle pale danno
`dT/dr` e `dC/dr` (C coppia); b è risolto dal momento angolare:

`dC/dr = 4 pi rho r² Va b`.

Con velocità assiale costante e trascurando gli scambi radiali:

`dp_statica(r) = (dT/dr)/(2 pi r)`

`dp_totale(r) = dp_statica(r) + rho (2b)²/2`.

Il salto di pressione totale è mediato pesando con la portata degli anelli.
L'ottimizzatore impone questo salto almeno pari al requisito maggiorato di
`pressure_numerical_margin`. La sensibilità di griglia è verificata sulla
pressione totale con `max_pressure_grid_change`.

`P_albero = omega C`; `P_fluido = Q dp_totale`.
Nel modello, la differenza è la dissipazione di profilo
`integrale B Drag_per_lunghezza W dr`. Si controlla il residuo del bilancio.
Questo usa le polari disponibili, senza introdurre un rendimento arbitrario.

Riferimenti per quantità di moto angolare, lavoro e distinzione delle pressioni:
[MIT, equazione di Eulero](https://web.mit.edu/16.unified/www/SPRING/propulsion/notes/node91.html)
e [MIT, compressori assiali](https://web.mit.edu/16.unified/www/FALL/thermodynamics/notes/node92.html).
La chiusura con swirl medio e profilo uniforme è un'approssimazione del nostro
modello a elementi di pala, non una simulazione tridimensionale del condotto.

La pressione totale include l'energia dello swirl in uscita. Il Venturi usa
un disco ideale senza swirl: il collegamento dei requisiti scalari non
dimostra identiche prestazioni del sistema completo. La redistribuzione radiale,
le perdite su mozzo e pareti, le interazioni di cascata e il gioco di punta non
sono modellati. La correzione Prandtl del rotore libero è rifiutata in questo modo.

## Comandi

Dalla cartella `2_ventola`, con selezione automatica:

```powershell
.\.venv\Scripts\python.exe -m ventola_designer size --validate-only
.\.venv\Scripts\python.exe -m ventola_designer size
```

Risultati: Q, area anulare, velocità sulle pale, dp totale e statica, forza
rotorica, rpm, coppia, potenza all'albero, al fluido, nello swirl e dissipata
dal modello di resistenza di profilo. Il report Markdown e i file ParaView
includono le nuove grandezze; tutti i dettagli rimangono nei JSON.

Il vecchio `input_esempio.json` conserva il modo a spinta del rotore libero,
richiamabile esplicitamente con `--input input_esempio.json`.
