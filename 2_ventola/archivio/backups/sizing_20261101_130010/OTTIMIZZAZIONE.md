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

Per ogni coppia profilo/numero pale si sceglie un seme ammissibile fra 12 tentativi
deterministici e si esegue una ricerca SLSQP locale. Le variabili continue sono
diametro del mozzo, quattro corde, quattro angoli di calettamento e un regime per
ogni punto operativo. Il rotore resta unico: variano solo i giri tra le condizioni.
Le variabili sono normalizzate fra 0 e 1. L'obiettivo e la somma di potenza
meccanica per durata, in joule, normalizzata con l'energia del seme.

Si impone la spinta minima per ciascun punto con margine numerico dello 0.2%,
Mach locale <= 0.3 e solidita locale <= 0.8 su 65 posizioni radiali.
Limiti provvisori: corda/D fra 0.04 e 0.22 e calettamento fra 0 e 45 gradi;
mozzo e giri mantengono gli intervalli dell'input. Queste scelte sono limiti del
problema esplorativo, non certificazioni di costruibilita o resistenza.

Il BEMT usa 32 anelli nella ricerca e 64 nella verifica finale. Sono accettati
solo risultati con convergenza SLSQP, vincoli rispettati (tolleranza 1e-6), energia
non maggiore del seme e differenza di spinta fra le griglie inferiore all'1%.
Il report conserva anche i tentativi non accettati. In assenza di risultati
accettati il programma termina con codice 2 e non esporta una geometria finale.
Non trovare un seme o non convergere non dimostra l'impossibilita fisica.

`optimization.json` contiene tentativi, impostazioni e migliore candidato
accettato; `report.json` contiene lo stesso report insieme agli export CSV, DAT,
OBJ e SVG della geometria risultante. I risultati vengono salvati in una nuova
cartella sotto `ventola_output`. Nessuna garanzia di minimo globale: un solo
avvio SLSQP per coppia, polari interpolate e rifiuti BEMT discontinui possono
limitare la ricerca. La velocita e ancora interpretata lontano a monte; il
modello e rotorico, senza perdite di punta/mozzo, condotto, CFD o verifica strutturale.

Riferimento dell'algoritmo e dei criteri di arresto:
https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html

## Confronto e verifica aggiuntiva

Al termine di una scansione completa del sottoinsieme richiesto:

```powershell
.\.venv\Scripts\python.exe -m ventola_designer.comparison ventola_output/NOME_CARTELLA/optimization.json
```

Il comando rifiuta report incompleti, produce `comparison.csv` e `CONFRONTO.md`
con esito e motivo di esclusione per ogni coppia, poi ricalcola il migliore
accettato a 128 anelli. `verification_128.json` conserva risultati, variazione
di spinta rispetto a 64 anelli e hash del report sorgente. Codice di uscita 2
se non esiste un candidato accettato o se fallisce la verifica aggiuntiva.
Il confronto non modifica le geometrie e non promuove risultati esclusi.
