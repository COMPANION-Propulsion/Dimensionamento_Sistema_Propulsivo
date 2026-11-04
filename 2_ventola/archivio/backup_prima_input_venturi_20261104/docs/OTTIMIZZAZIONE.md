# Ottimizzazione preliminare del rotore

Eseguire dalla cartella `2_ventola` con l'ambiente Python del progetto:

```powershell
.\.venv\Scripts\python.exe -m ventola_designer.optimizer --profiles NACA4412 --blades 2
.\.venv\Scripts\python.exe -m ventola_designer.optimizer
```

Il primo comando limita il confronto a una coppia; il secondo considera tutti i
profili e numeri di pale ammessi nell'input. Supportati `--input`, `--output`
(cartella non esistente), `--maxiter`, `--profiles` e `--blades`.
Richiede NumPy e SciPy, gia presenti nell'ambiente per le polari.

Per ogni coppia profilo/numero pale si generano `seed_samples` geometrie entro i
limiti dell'utente, con generatore riproducibile controllato da `random_seed`.
Si eseguono fino a `starts` ricerche SLSQP dai semi ammissibili a minore energia.
Ogni avvio viene verificato separatamente e registrato in `attempts`: la scelta
considera solo quelli accettati. Se i semi ammissibili sono meno di `starts`,
il numero effettivo di avvii viene riportato. Le variabili continue sono
diametro del mozzo, quattro corde, quattro angoli di calettamento e un regime per
ogni punto operativo. Il rotore resta unico: variano solo i giri tra le condizioni.
Le variabili sono normalizzate fra 0 e 1. L'obiettivo e la somma di potenza
meccanica per durata, in joule, normalizzata con l'energia del seme.

La sezione `sizing` del JSON controlla limiti e impostazioni numeriche. I valori
illustrativi dell'esempio sono margine di spinta 0.2%, Mach <= 0.3, solidita <= 0.8,
corda/D fra 0.04 e 0.22 e calettamento fra 0 e 45 gradi.
Mozzo e giri mantengono gli intervalli nella sezione `rotor`. Queste scelte sono limiti del
problema esplorativo, non certificazioni di costruibilita o resistenza.

Le griglie sono `stations_optimization` e `stations_verification` (default 32 e 64).
Sono accettati solo risultati con convergenza SLSQP, vincoli rispettati entro
`constraint_tolerance`, energia non maggiore del seme e differenza di spinta fra
le griglie inferiore a `max_thrust_grid_change` (default 1%).
Il report conserva anche i tentativi non accettati. In assenza di risultati
accettati il programma termina con codice 2 e non esporta una geometria finale.
Non trovare un seme o non convergere non dimostra l'impossibilita fisica.

`optimization.json` contiene tentativi, impostazioni e migliore candidato
accettato; `report.json` contiene lo stesso report insieme agli export CSV, DAT,
OBJ e SVG della geometria risultante. I risultati vengono salvati in una nuova
cartella sotto `ventola_output`. Nessuna garanzia di minimo globale: anche con
piu avvii, polari interpolate e rifiuti BEMT discontinui possono
limitare la ricerca. La velocita e ancora interpretata lontano a monte; il
modello e rotorico, con perdite opzionali per rotore libero, senza condotto, CFD o verifica strutturale.

Riferimento dell'algoritmo e dei criteri di arresto:
https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html

## Confronto e verifica aggiuntiva

Al termine di una scansione completa del sottoinsieme richiesto:

```powershell
.\.venv\Scripts\python.exe -m ventola_designer.comparison ventola_output/NOME_CARTELLA/optimization.json
```

Il comando rifiuta report incompleti, produce `comparison.csv` e `CONFRONTO.md`
con esito e motivo di esclusione per ogni coppia, poi ricalcola il migliore
accettato su `stations_final` anelli (default 128). `verification_final.json`
conserva risultati, variazione rispetto alla griglia di verifica e hash del
report sorgente. Codice di uscita 2
se non esiste un candidato accettato o se fallisce la verifica aggiuntiva.
Il confronto non modifica le geometrie e non promuove risultati esclusi.

La verifica sulla griglia `stations_final` e ora integrata anche nel comando
`size`: ogni avvio che supera i controlli iniziali viene ricalcolato prima di
entrare nella selezione finale. I vincoli devono restare entro tolleranza e
la variazione di spinta rispetto a `stations_verification` deve restare sotto
`max_thrust_grid_change`. Errori di dominio, risultati incompleti e valori non
finiti escludono il candidato. Non viene eseguita una nuova ottimizzazione.

La selezione usa l'energia della griglia finale. I dati precedenti rimangono in
`verification_grid_energy_J` e `verification_grid_cases`; `final_verification`
contiene esito e diagnostica. Se un avvio fallisce, altri avvii accettati possono
essere selezionati. Se falliscono tutti, `best` e null, il codice di uscita e 2
e non viene esportata una geometria finale. `optimization.json`, `report.json`
e `RISULTATO.md` sono disponibili anche in questo caso. `complete` distingue
un report intermedio da un'esecuzione che ha completato tutti i tentativi.

## Configurazione e controllo senza calcolo

```powershell
.\.venv\Scripts\python.exe -m ventola_designer.optimizer --input input_esempio.json --validate-only
```

Questo comando controlla il JSON e stampa le impostazioni risolte senza cercare
una soluzione e senza generare una cartella risultati. I vecchi file privi di
`sizing` ricevono default espliciti, registrati nel report. Chiavi sconosciute,
valori non finiti, intervalli invertiti, conteggi non interi e griglie non
crescenti sono rifiutati. `--maxiter` sovrascrive il valore nel JSON e il report
registra il valore effettivamente usato.

Campi `sizing`:

| Campi | Significato |
|---|---|
| chord_over_D_bounds, pitch_deg_bounds | Limiti delle quattro corde normalizzate e dei quattro calettamenti in gradi |
| max_solidity, max_Mach | Limiti aerodinamici esplorativi; non certificano validita fisica del modello |
| thrust_numerical_margin | Margine numerico relativo sulla spinta minima |
| stations_optimization, stations_verification, stations_final | Numero crescente di anelli per le tre griglie |
| solidity_stations | Punti di controllo della solidita |
| starts, seed_samples, random_seed | Numero massimo di avvii, tentativi iniziali e seme riproducibile |
| maxiter, ftol, finite_difference_step | Iterazioni massime, tolleranza SLSQP, passo nelle variabili normalizzate |
| constraint_tolerance, max_thrust_grid_change | Tolleranza sui vincoli e variazione radiale relativa ammessa |

Il numero di nodi geometrici resta quattro. Le condizioni dell'aria globali
possono essere sovrascritte per punto operativo; la velocita e definita lontano a monte.
Condotto, verifiche strutturali e degli attacchi, motore ed elettronica sono
fuori dall'ambito attuale. La validazione sperimentale delle polari e in pausa.

## Avvio unico e condizioni per punto operativo

```powershell
.\.venv\Scripts\python.exe -m ventola_designer size --input input_esempio.json --validate-only
.\.venv\Scripts\python.exe -m ventola_designer size --input input_esempio.json
```

`size` inoltra le opzioni al dimensionatore SLSQP. Il primo comando valida e
mostra le impostazioni e l'aria risolta per punto senza cercare soluzioni o
scrivere risultati. Il secondo avvia il dimensionamento richiesto dall'utente.
Il vecchio comando `python -m ventola_designer.optimizer` resta compatibile.
Senza `size`, il comando geometrico continua a produrre solo un seme.

Ogni elemento di `operating_points` puo contenere un oggetto `air`, ad esempio:

```json
{
  "name": "condizione_calda",
  "minimum_rotor_thrust_N": 0.6,
  "axial_inlet_velocity_m_s": 0.5,
  "duration_s": 300,
  "air": {
    "temperature_K": 305.15,
    "static_pressure_Pa": 95000
  }
}
```

Valori illustrativi. I campi assenti ereditano quelli dell'oggetto globale `air`.
Sono accettati temperatura assoluta in kelvin, pressione statica assoluta in
pascal e `relative_humidity` null o zero (aria secca). Le condizioni risolte
sono registrate in ogni risultato BEMT e utilizzate per densita, viscosita,
velocita del suono e consultazione delle polari. Gli override non cambiano gli
altri punti operativi.

Il campo globale `velocity_reference` accetta attualmente solo `"far_upstream"`.
Per compatibilita e il default dei file precedenti, esplicitato dopo la lettura
e nel report. Una velocita prescritta sul disco o all'ingresso del condotto
richiede un diverso modello di ingresso: viene rifiutata, non reinterpretata.
Il nome storico `axial_inlet_velocity_m_s` viene mantenuto, ma con questa
convenzione esplicita. Questo incremento non implementa un modello del condotto.

## Correzione opzionale delle perdite

Nella sezione `sizing` aggiungere `"loss_model": "prandtl_free_rotor"` per attivare
la correzione di punta e mozzo per un rotore libero. Il default `"none"` conserva
il modello precedente: non e un'affermazione di assenza di perdite fisiche.
Non usare questa correzione come validazione della ventola intubata: non descrive
gioco pala-parete, trafilamento, strati limite sulle pareti o forza sul condotto.

Con B pale, r raggio locale, R raggio esterno, Rh raggio del mozzo e phi angolo
del flusso dal piano rotorico (radianti):

```
f_tip = B*(R-r)/(2*r*abs(sin(phi)))
f_hub = B*(r-Rh)/(2*Rh*abs(sin(phi)))
F_tip = 2/pi*acos(exp(-f_tip))
F_hub = 2/pi*acos(exp(-f_hub))
F = F_tip*F_hub
```

Riferimento: [NREL/TP-5000-63217, equazioni 11-15](https://docs.nrel.gov/docs/fy15osti/63217.pdf).
Nel nostro bilancio propulsivo, a e b sono velocita indotte dimensionali:
`dT/dr = 4*pi*rho*r*F*a*(V+a)` e `dQ/dr = 4*pi*rho*r^2*F*b*(V+a)`.
F viene ricalcolato durante ogni iterazione e incluso nel controllo dei residui.
Non si moltiplica la spinta finale per un rendimento presunto. L'applicazione al
rotore propulsivo resta una scelta di modellazione preliminare, non una validazione.

L'integrazione usa punti medi interni: F si annulla agli estremi ma non si divide
per F=0. Non viene imposto un minimo artificiale al fattore. I risultati locali
registrano F_tip, F_hub, F; quelli globali loss_model e loss_factor_min. Solver
non convergenti e condizioni fuori polare restano rifiutati. Le verifiche testano
limiti analitici, scala geometrica, bilanci e raffinamento radiale su casi fissi.

## Screening della geometria

Tre ulteriori campi `sizing`:

| Campo | Default | Significato |
|---|---:|---|
| geometry_stations | 65 | Stazioni radiali, inclusi mozzo e punta, durante SLSQP |
| minimum_section_thickness_m | 0 | Minimo richiesto al massimo spessore di ciascuna sezione, in metri |
| minimum_circumferential_gap_m | 0 | Spazio richiesto fra inviluppi circonferenziali delle sezioni, in metri |

I default zero non impongono un requisito costruttivo arbitrario. Lo spessore
massimo della sezione deve essere specificato dall'utente secondo il processo
produttivo; non e lo spessore al bordo d'uscita e non dimostra resistenza.
Il profilo e campionato con gli stessi 80 pannelli per lato del generatore.
Lo spessore si misura fra coppie corrispondenti dei punti superiore/inferiore,
normali alla linea media NACA, prima della rotazione e dell'avvolgimento.

Per ogni raggio, il passo circonferenziale e `2*pi*r/B`. Si sottrae l'estensione
massima dello sviluppo tangenziale del profilo ruotato: lo spazio risultante
e quello fra inviluppi, non la minima distanza euclidea delle superfici 3D.
Un valore negativo segnala sovrapposizione degli inviluppi e viene escluso
conservativamente; non dimostra necessariamente collisione reale.
I margini rispetto ai due requisiti vengono divisi per D ed entrano nei vincoli
SLSQP, con `constraint_tolerance` come tolleranza normalizzata.

La verifica finale usa `2*geometry_stations-1` sezioni. Questo e un controllo
campionato, non una prova di non interferenza fra le stazioni o del solido
triangolato esportato. I risultati sono in `geometry_screening` e RISULTATO.md.
Nodi disordinati, corde non positive, diametri incompatibili e valori non finiti
sono rifiutati. Materiale, attacco al mozzo, tensioni, deformazioni, fatica e
vibrazioni non sono verificati: il report mantiene tale limite esplicito.
