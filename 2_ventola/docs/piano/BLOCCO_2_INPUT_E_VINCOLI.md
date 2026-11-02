# Blocco 2 — Input e vincoli

Stato: decisioni e caso dimostrativo provvisorio raccolti. I valori marcati «esempio» servono a iniziare il prototipo e non sono requisiti reali dell'utente.

## Dati confermati

- Fluido: aria.
- Diametro esterno della ventola: input obbligatorio assegnato dall'utilizzatore, fisso durante l'ottimizzazione e comune ai punti operativi. Non è una variabile di progetto libera.
- Diametro del mozzo: variabile continua determinata dall'ottimizzatore entro un intervallo assegnato; i limiti numerici restano da definire.
- Geometria della pala: generata automaticamente dallo script; l'utilizzatore non inserisce corda, svergolamento o coordinate delle sezioni. Queste sono variabili/risultati dell'ottimizzazione, soggetti ai vincoli concordati.
- Motore da scegliere dopo il dimensionamento: giri, coppia e potenza meccanica per ciascun punto operativo sono risultati destinati alla successiva selezione.
- Numero di pale: scelto dal programma come migliore soluzione fra un insieme di numeri interi ammessi; per ogni candidato si ottimizzano le variabili continue e si confrontano solo soluzioni che soddisfano i requisiti.
- Intervallo discreto iniziale di confronto: interi da 2 a 8 pale inclusi. È una scelta pratica per lo studio preliminare; modello aerodinamico e vincoli potranno rendere non ammissibili alcuni candidati.
- Durata di ogni punto operativo: input dell'utilizzatore, usato per confrontare il consumo nelle condizioni statiche e in avanzamento. L'obiettivo diventa minimizzare l'energia meccanica totale sul profilo operativo assegnato.
- Spinta complessiva richiesta inserita dall'utilizzatore.
- La spinta richiesta è una soglia minima da garantire in ogni punto operativo: il modello deve imporre spinta calcolata >= spinta richiesta, con tolleranza numerica esplicita da definire.
- Funzionamento da fermo e in avanzamento.
- Obiettivo approvato: minimizzare l'energia meccanica totale sul profilo d'uso, garantendo almeno la spinta richiesta in ogni caso.
- Dimensionamento delle pale; condotto esterno al dimensionamento; indipendenza dal Venturi.

## Caso dimostrativo provvisorio

Il requisito NASA Astrobee di 0,6 N è usato solo come ordine di grandezza orientativo; l'architettura del progetto rimane un rotore assiale intubato. Tutti gli altri valori seguenti sono assunzioni didattiche inventate e sostituibili dall'utente.

| Caso | Spinta minima | Velocità assiale in ingresso | Durata |
|---|---:|---:|---:|
| Statico | 0,6 N | 0 m/s | 600 s |
| Avanzamento lento | 0,6 N | 0,5 m/s | 600 s |

Condizioni aria d'esempio condivise: 22 °C, 101325 Pa assoluti, aria secca. Geometria e bounds d'esempio: diametro esterno 0,10 m; diametro mozzo fra 0,02 e 0,04 m; regime fra 5000 e 30000 rpm; candidati 2–8 pale. I valori sono provvisori, non derivati dai dati dimensionali di Astrobee e non certificano la fattibilità aerodinamica.

Questo caso basta a esercitare la struttura input e il solutore dopo averne definite le equazioni, ma prima di presentare un dimensionamento come valido serviranno profili/polari adeguati, correlazioni BEMT validate e la gestione del contributo del condotto. In assenza della geometria del condotto, la spinta prodotta dal prototipo resta una stima rotorica, non la spinta netta installata.

## Input proposti

| Gruppo | Dati | Trattamento proposto |
|---|---|---|
| Punti operativi | Spinta minima richiesta [N], velocità di avanzamento [m/s], durata [s] | Un record per condizione; includere un caso statico e uno in movimento; durate positive |
| Ambiente | Temperatura dell'aria [K o °C con conversione], pressione assoluta [Pa] | Condizioni esplicite condivise o per caso; valore standard solo se scelto e dichiarato dall'utente |
| Ingombro | Diametro esterno della ventola [m] | Input obbligatorio positivo, imposto dall'utilizzatore e invariato durante l'ottimizzazione |
| Mozzo | Diametro minimo e massimo ammessi [m] | Limiti di input; il diametro effettivo è determinato dall'ottimizzatore, con 0 < minimo < massimo < diametro esterno |
| Regime di rotazione | Limiti di ricerca dei giri [rpm] | Da definire come limiti progettuali e del modello, senza riferirli a un motore già scelto |
| Motore | Nessun dato di catalogo richiesto in questa fase | Scelta successiva; giri, coppia [N m] e potenza meccanica [W] richiesti sono output. Eventuali vincoli esterni di potenza devono essere assegnati esplicitamente |
| Pale | Numeri interi di pale ammessi inizialmente da 2 a 8; limiti geometrici e catalogo interno dei profili | Lo script genera la geometria parametrica della pala e confronta i numeri ammessi; l'utente fornisce i vincoli, non la pala già progettata |
| Installazione | Informazioni esterne necessarie a rappresentare l'ambiente del rotore | Da definire con il modello fisico; non introdurre geometria del condotto come variabile da ottimizzare |
| Più punti operativi | Durata di ogni condizione [s] | Obiettivo: somma di potenza meccanica del caso [W] × durata [s], espressa in joule; nessun peso arbitrario |

Densità, viscosità e altre proprietà necessarie saranno ricavate con relazioni dichiarate nel blocco fisico oppure fornite esplicitamente, con gestione della coerenza dei dati. La scelta dell'aria non implica già una scelta di incomprimibilità, regime o modello di turbolenza.

## Variabili di ottimizzazione candidate

- Parametri di una distribuzione continua e regolare di corda e calettamento lungo il raggio; lo script ricostruisce da questi parametri le sezioni della pala.
- Diametro del mozzo: ottimizzazione confermata entro limiti assegnati; il diametro esterno è escluso dalle variabili di ottimizzazione.
- Regime di rotazione per ogni punto operativo, entro i limiti concordati.
- Profilo della sezione scelto dal programma fra quelli inclusi nel catalogo interno ammesso e con dati aerodinamici utilizzabili; l'insieme dei profili e le polari vanno definiti e documentati nello sviluppo, senza richiedere all'utente di fornire una pala già disegnata.

Il numero di pale è una scelta discreta confermata, da gestire con un confronto esterno alle ottimizzazioni continue. La selezione dei profili da catalogo resta da definire. La geometria comune a tutti i casi e il passo fisso sono ancora proposte della specifica del blocco 1.

## Decisione ancora necessaria

L'intervallo iniziale di candidati è da 2 a 8 pale inclusi. L'obiettivo è minimizzare l'energia meccanica totale, sommando la potenza meccanica all'albero per la durata di ciascun punto operativo, sotto il vincolo che la spinta complessiva calcolata sia almeno pari al minimo richiesto in ogni caso. Le durate devono rappresentare il profilo d'uso; punti identici si possono aggregare sommando le durate.

Il motore sarà scelto dopo il dimensionamento. Restano da definire limiti di ricerca del regime di rotazione: non lasciare la ricerca illimitata per l'assenza di un motore selezionato. Riportare per ogni caso la terna simultanea giri-coppia-potenza, senza trattare massimi provenienti da casi diversi come un unico punto operativo. Non stimare la potenza elettrica senza dati di rendimento.

Per il mozzo acquisire successivamente un intervallo ammissibile che tenga conto degli ingombri e dei vincoli meccanici forniti. Il valore ottimizzato è un risultato aerodinamico preliminare: non costituisce verifica strutturale o dimensionamento degli attacchi delle pale.

Se la spinta richiesta non è raggiungibile entro il diametro esterno imposto e gli altri vincoli, il programma deve segnalarlo senza aumentare automaticamente il diametro. Distinguere un requisito verificato come non soddisfatto da una ricerca numerica non convergente: il fallimento dell'ottimizzatore non dimostra da solo l'assenza di soluzioni.

I limiti numerici del mozzo, dei giri e della geometria delle pale andranno definiti prima di implementare l'ottimizzatore. Anche spinta complessiva e contributi dell'installazione dovranno avere una definizione fisica nel blocco successivo. Questo documento definisce gli input del progetto, non contiene ancora valori di un caso di calcolo.
