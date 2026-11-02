# Blocco 5 — BEMT iniziale e dati aerodinamici della pala

Stato: proposta per il prototipo rotorico; equazioni e polari finali richiedono un caso operativo e una fonte di dati.

## Modello iniziale

Usare un BEMT per rotore assiale: dividere la pala in stazioni radiali, valutare velocità relativa e angolo d'attacco a ciascuna stazione, interpolare i coefficienti aerodinamici del profilo e integrare carico assiale, coppia e potenza. Accoppiare il calcolo degli elementi di pala al bilancio di quantità di moto e risolvere iterativamente le velocità indotte.

È un modello rotorico preliminare. Finché manca il condotto non correggere la spinta con un fattore inventato e non dichiarare la spinta netta installata. Il requisito di spinta nell'ottimizzazione si riferisce alla spinta prevista dal BEMT; il report la qualifica come stima rotorica.

## Generazione automatica della geometria parametrica

La pala è un risultato dello script, non un dato geometrico richiesto all'utente. L'utente fornisce requisiti e bounds di progetto; il programma genera e ottimizza la geometria, poi esporta le sezioni ottenute.

- Raggio esterno: fissato dal diametro imposto dall'utente.
- Raggio del mozzo: variabile dell'ottimizzazione entro bounds d'input.
- Corda e calettamento: funzioni radiali continue e regolari, rappresentate inizialmente con pochi nodi di controllo e interpolazione documentata; evitare di ottimizzare una variabile per ogni cella/stazione.
- Numero di pale: ciclo discreto su candidati interi 2–8; numero fissato durante ogni ottimizzazione SLSQP.
- Proposta prototipo: un solo profilo per l'intera pala; confrontare separatamente i candidati del catalogo. Variare profilo lungo il raggio solo in una fase successiva, se polari e modello lo supportano.
- Sezioni: riportare raggio, corda, angolo di calettamento e identificativo del profilo; spessore/geometria del profilo è determinato dalle coordinate del profilo e da una scala coerente.
- Applicare vincoli di regolarità, corda positiva e limiti geometrici per prevenire forme non fabbricabili o oscillazioni della parametrizzazione.

Il programma dovrà includere un piccolo catalogo versionato di profili con coordinate e polari documentate, così da poter generare anche la forma delle sezioni. Un profilo sarà selezionabile dall'ottimizzazione solo quando esistono coordinate e dati aerodinamici appropriati al Reynolds/Mach previsto; non si richiederà all'utente di fornire la geometria della pala.

## Polari dei profili

Ogni profilo usato dal modello deve avere una polare con angolo d'attacco, coefficiente di portanza e coefficiente di resistenza, e indicazioni di Reynolds e Mach, fonte, metodo di generazione e convenzioni. Interpolare solo dentro il campo coperto; fuori campo, segnalare il caso o applicare un'estensione documentata e dichiarata, mai estrapolare in silenzio.

Ordine di preferenza: dati sperimentali adeguati al regime; polari pubblicate o fornite dall'utente; polari ottenute con XFOIL per il Reynolds/Mach locale, contrassegnate come stime numeriche. XFOIL non è una misura e non fornisce da solo una validazione della ventola tridimensionale. Il regime di stallo richiede dati o correzioni specifiche, non un taglio numerico arbitrario.

## Correzioni e limiti

- Implementare prima il nucleo assiale e validarlo con casi noti; aggiungere una correzione per perdita di punta e mozzo solo se specificata da una correlazione per il regime rotorico scelto.
- Il gioco tra punta della pala e condotto influenza perdite e prestazioni. In assenza della geometria, non assumere un valore o una correzione di punta da condotto; usare un'ipotesi rotorica esplicita e segnare il limite.
- Il flusso statico e quello in avanzamento condividono il solver soltanto se le equazioni e le correlazioni sono valide in entrambi. Definire il trattamento dell'induzione nel caso statico prima di codificarlo.
- Monitorare convergenza dell'iterazione BEMT, carichi locali, Mach e Reynolds alle stazioni, coerenza di segno e bilancio tra spinta/torque e potenza.
- Il modello sarà stazionario e assiale nel primo prototipo; flussi inclinati, interazione non uniforme con il labbro del condotto e scie rotor-statore restano fuori finché non forniti e modellati.

## Ottimizzazione

Per ogni numero intero di pale, SLSQP regola mozzo, nodi di corda e calettamento e giri per caso operativo, minimizzando la somma di potenza all'albero per durata. Vincoli: spinta BEMT almeno pari al minimo in ogni caso; bounds e regolarità geometriche; bounds dei giri; interpolazione dentro le polari disponibili.

Partire con differenze finite per i gradienti del BEMT. Aggiungere l'adjoint solo quando la formulazione differenziabile e il solutore lo rendono disponibile e dopo confronto dei gradienti su perturbazioni indipendenti. Non assumere che nominare un algoritmo adjoint renda il modello automaticamente più accurato.

## Riferimenti

- Stahl, *Aerodynamic Performance Modeling of Ducted Fans and Shrouded Propellers for Preliminary Design*, VFS 2014, [abstract e riferimento](https://saemobilus.sae.org/papers/aerodynamic-performance-modeling-ducted-fans-shrouded-propellers-preliminary-design-f-0070-2014-9427): BEMT adattata a ventole intubate e validazione su dati di galleria del vento.
- Borst, NASA, *A New Blade Element Method for Calculating the Performance of High and Intermediate Solidity Fans*, [NASA Technical Reports Server](https://ntrs.nasa.gov/api/citations/19790004876/downloads/19790004876.pdf): elementi di pala e correzioni tridimensionali per rotori in condotto.
- Drela, MIT, [XFOIL](https://web.mit.edu/drela/Public/web/xfoil/): metodo numerico per profili e polari in regimi a basso Reynolds.
- UIUC, [Airfoil Data Site](https://m-selig.ae.illinois.edu/ads.html): coordinate e dati di profili sperimentali; controllare la copertura del regime d'interesse.
