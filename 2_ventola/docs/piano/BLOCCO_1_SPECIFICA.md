# Blocco 1 — Obiettivo e perimetro del dimensionamento della ventola

Data: 31 ottobre 2026.
Stato: obiettivo del blocco 1 approvato dall'utente: minimizzare la potenza meccanica garantendo la spinta richiesta in ogni condizione operativa. Restano da definire nei blocchi successivi aggregazione delle potenze, formulazione dei vincoli e modello fisico.

## Obiettivo

Sviluppare insieme all'utente uno script Python autonomo che parta da una spinta richiesta, inserita da chi utilizza il programma, e determini una geometria aerodinamica preliminare della ventola, comprese le pale. Verificare la configurazione sia da fermo sia in movimento.

La spinta richiesta è un input del dimensionamento; la spinta calcolata è un output con cui verificarne il raggiungimento. Non fissare il requisito nel codice e non sostituirlo con una portata imposta arbitrariamente.

## Requisiti concordati

- La ventola serve a generare spinta.
- Il fluido di lavoro è aria, confermato dall'utente.
- Il diametro esterno è imposto dall'utilizzatore e resta fisso durante il dimensionamento; non è una variabile di ottimizzazione.
- Deve operare da fermo e in movimento.
- È installata all'interno di un condotto.
- Il condotto è esterno al problema di dimensionamento: non progettarne o ottimizzarne la geometria.
- Il programma deve determinare anche la geometria delle pale.
- Il motore sarà scelto successivamente al dimensionamento: lo script deve restituire giri, coppia e potenza meccanica richiesti all'albero per ogni punto operativo, senza assumere limiti o rendimento di un motore non ancora selezionato.
- Il programma è indipendente dal dimensionamento del Venturi: nessuna importazione, lettura di risultati o dipendenza dai suoi parametri e dal suo solutore.
- Il dimensionamento deve usare un algoritmo di ottimizzazione. L'utente indica «sqlp o adjoint»: interpretazione di lavoro di «sqlp» come SQP/SLSQP, da correggere se intende un metodo diverso.
- Il lavoro procede per blocchi condivisi. Il blocco 1 definisce obiettivi e confini, inclusa la strategia di ottimizzazione proposta; le equazioni del modello fisico restano da scegliere.

## Significato della spinta

L'utente richiede la spinta complessiva della ventola, espressa in newton. Registrare questa come grandezza obiettivo, senza restringerla alla sola forza sulle pale. La proposta precedente di usare esclusivamente la forza sul rotore è superata.

Nel blocco fisico definire precisamente il confine del sistema e il bilancio che restituisce la spinta complessiva, chiarendo i contributi dell'installazione. Il condotto resta esterno alle variabili di progetto: eventuali informazioni necessarie sui suoi effetti devono essere fornite come dati esterni o rappresentate da un modello esplicitamente concordato. Non affermare di prevedere la spinta complessiva mediante il solo carico sul rotore senza giustificazione.

Escludere il progetto del condotto non equivale a scegliere un modello di rotore libero: le condizioni esterne necessarie al calcolo saranno individuate nel blocco fisico. Non attribuire al condotto benefici, perdite o contributi di forza non specificati.

## Casi operativi: interfaccia proposta

Ogni caso deve contenere almeno:

| Campo | Significato | Unità |
|---|---|---|
| nome_caso | Identificativo del punto operativo | — |
| spinta_richiesta_n | Requisito scelto dall'utilizzatore | N |
| velocita_avanzamento_m_s | Velocità del sistema rispetto al fluido indisturbato | m/s |

Prevedere almeno un caso statico, con velocità di avanzamento nulla, e un caso in movimento con velocità positiva. Consentire requisiti di spinta uguali o differenti nei diversi casi; non assumere automaticamente spinta costante a ogni velocità.

La velocità di avanzamento non va identificata automaticamente con la velocità locale sul rotore: il loro collegamento appartiene al modello fisico ancora da definire.

Proposta: ottenere una singola geometria a passo fisso che soddisfi i casi assegnati, permettendo regimi di rotazione differenti entro i vincoli disponibili. Passo variabile e strategie di controllo non sono ancora requisiti concordati.

## Risultati attesi

### Geometria della ventola

- Diametro esterno imposto, riportato nei risultati, e diametro del mozzo determinato dall'ottimizzatore entro limiti assegnati.
- Numero di pale scelto confrontando i candidati interi ammessi.
- Distribuzione radiale della corda.
- Distribuzione radiale del calettamento, con convenzione angolare esplicita.
- Identificazione dei profili e relativi spessori lungo la pala.
- Tabella delle sezioni radiali utilizzabile per una successiva ricostruzione CAD.

Nel blocco successivo distinguere quali quantità siano imposte, scelte da un insieme discreto o determinate dal dimensionamento. Il gioco di punta potrà essere un vincolo esterno, senza ricavare o modificare la geometria del condotto.

### Prestazioni per ciascun caso

- Spinta richiesta e spinta calcolata, con scostamento e criterio di accettazione esplicito.
- Regime di rotazione.
- Coppia e potenza meccanica all'albero.
- Distribuzione del carico lungo la pala, nei limiti del modello scelto.
- Stato della soluzione: requisito soddisfatto, non soddisfatto oppure calcolo non valido/non convergente.

Definire nel blocco fisico gli indicatori di prestazione appropriati al caso statico e all'avanzamento. La potenza elettrica richiede dati aggiuntivi sul motore e sull'azionamento e non va equiparata alla potenza all'albero.

## Fuori perimetro

- Dimensionamento del condotto e del Venturi, loro accoppiamento e ottimizzazione dell'intero sistema.
- Certificazione della spinta complessiva installata senza un modello o dati esterni adeguati.
- Verifica strutturale, fatica, vibrazioni, attacchi delle pale e validazione per la costruzione.
- Previsione acustica e dimensionamento elettrico del motore.
- Implementazione del solutore nel blocco 1.

## Ottimizzazione: obiettivo approvato e formulazione da definire

Obiettivo approvato dall'utente: garantire almeno la spinta minima assegnata in ciascun punto operativo, da fermo e in movimento, riducendo il consumo meccanico. L'utente ha scelto di inserire la durata di ogni condizione: la formulazione aggregata è minimizzare l'energia meccanica totale, somma di potenza meccanica [W] per durata [s] dei punti operativi, in joule, sotto vincoli di spinta calcolata >= spinta minima richiesta. Questa scelta non definisce ancora il modello fisico.

Le durate sono i pesi fisici dell'obiettivo e sono input dell'utilizzatore. Il requisito è una spinta minima: ogni punto operativo ha un vincolo di spinta calcolata almeno pari al minimo richiesto, entro la tolleranza numerica esplicitata.

- Variabile continua confermata: diametro del mozzo, da ottimizzare entro limiti assegnati. Altre variabili candidate: parametri della corda e del calettamento lungo il raggio, giri per ciascun punto operativo. Il diametro esterno è imposto dall'utilizzatore ed escluso dall'ottimizzazione. Definire limiti e parametrizzazione prima del calcolo.
- Scelta discreta confermata: numero di pale, da selezionare confrontando i candidati interi ammessi attraverso un ciclo esterno e risolvendo il problema continuo per ciascuno. Non trattare il numero di pale come una variabile continua da arrotondare a posteriori. La scelta dei profili da catalogo resta da definire.
- Vincoli: spinta per ogni caso, ingombri e limiti di ricerca dei giri da definire, ammissibilità geometrica e campo di validità aerodinamico. Eventuali limiti di potenza sono ammessi solo se assegnati come requisiti esterni, non dedotti da un motore non ancora selezionato. Il condotto non è una variabile di ottimizzazione.
- Metodo di partenza proposto: `scipy.optimize.minimize(method="SLSQP")`, con variabili e vincoli opportunamente scalati. SLSQP gestisce limiti e vincoli di uguaglianza e disuguaglianza.
- L'adjoint è una modalità di calcolo dei gradienti, abbinabile a un ottimizzatore come SLSQP. Valutarne l'implementazione in base alle equazioni e alla parametrizzazione scelte; non prometterlo indipendentemente dal modello fisico.
- Verificare i gradienti di obiettivo e vincoli su casi controllati con perturbazioni indipendenti. Definire separatamente convergenza del modello fisico, convergenza dell'ottimizzatore e soddisfacimento dei requisiti.
- Conservare stato finale, scostamenti dai vincoli e storia dell'ottimizzazione; rivalutare la soluzione finale con il modello fisico. Confrontare più inizializzazioni quando necessario e non presentare la soluzione come ottimo globale garantito.

Riferimenti tecnici consultati:

- [SciPy — SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html).
- [SU2 — Execution](https://su2code.github.io/docs_v7/Execution/): distingue metodo di ottimizzazione e metodo di calcolo dei gradienti, inclusa la combinazione SLSQP/adjoint. Riferimento metodologico, non scelta di SU2 come dipendenza.

## Decisioni per i blocchi successivi

1. Tradurre la spinta complessiva richiesta in una definizione fisica con confine del sistema e contributi esterni espliciti.
2. Identificare fluido, condizioni ambientali e punti operativi di progetto.
3. Acquisire il diametro esterno imposto; stabilire intervallo ammesso del diametro del mozzo, limiti di ricerca dei giri, eventuali vincoli esterni di potenza e informazioni sull'installazione disponibili.
4. Distinguere variabili di progetto e parametri imposti; acquisire le durate dei punti operativi e applicare l'obiettivo di energia meccanica totale approvato.
5. Scegliere modello fisico, dati dei profili, correlazioni, fonti e campo di validità.
6. Concordare tolleranze, verifiche indipendenti e formato degli output prima dell'implementazione.

Non inventare valori numerici per chiudere questi punti. Il completamento del blocco 1 riguarda la definizione del problema, non l'esistenza di una soluzione già dimensionata.
