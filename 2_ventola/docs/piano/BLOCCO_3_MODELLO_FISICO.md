# Blocco 3 — Definizione del problema fisico

Stato: architettura concordata: rotore assiale intubato del progetto COMPANION; Astrobee è usato solo per fissare un ordine di grandezza esemplificativo della spinta. Fedeltà mista scelta, con CFD futura.

## Sistema e obiettivo

Il sistema di interesse è il propulsore intubato: rotore più condotto. La prestazione richiesta è la spinta assiale complessiva, non soltanto la forza esercitata dal rotore sull'aria. Un bilancio di quantità di moto del flusso va definito su un volume di controllo che includa i flussi in ingresso e uscita e i contributi di pressione; se si ricava la forza dal carico aerodinamico delle superfici, va inclusa anche la forza sul condotto.

Il condotto rimane fuori dalle variabili di progetto: non si ottimizzano la sua forma o dimensione. L'utente non ha una geometria CAD o misurata. Quindi il primo prototipo non potrà predire in modo affidabile la spinta netta reale rotore-condotto. Procedere con un modello rotorico BEMT, riportando la spinta del rotore come stima preliminare e tenendo distinto il contributo del condotto, che resta non quantificato. Non chiamare la stima rotorica «spinta complessiva del propulsore» né introdurre un fattore di incremento del condotto senza dati o fonte validata.

Prevedere che più avanti una geometria o dati sperimentali del condotto possano essere aggiunti come input opzionali per la verifica CFD. Nel frattempo, i risultati vanno presentati con questa limitazione esplicita; l'ottimizzazione soddisferà il requisito di spinta solo rispetto al modello effettivamente implementato.

## Dati fisici per ciascun punto operativo

- Spinta assiale minima richiesta [N] e durata [s].
- Convenzione d'ingresso proposta: velocità assiale media [m/s], pressione statica assoluta [Pa] e temperatura statica [K], assegnate dall'utilizzatore per ciascun punto operativo. Chiedere inoltre l'umidità relativa se rilevante; altrimenti dichiarare aria secca.
- La velocità all'ingresso della ventola non va confusa con la velocità indisturbata lontano dal propulsore. Se entrambe servono, la seconda va inserita separatamente o ricavata tramite un modello esplicitato.
- Proposta termodinamica iniziale: aria secca come gas perfetto con proprietà dipendenti dalla temperatura, salvo diverso dato scelto in seguito. Il modello dovrà controllare Mach e variazione di densità e avvisare se le ipotesi adottate non sono valide. Non imporre incomprimibilità senza verifica.
- Geometria rotorica: diametro esterno imposto; diametro mozzo ottimizzato entro limiti; distribuzione della corda e del calettamento; numero di pale candidato.
- Regime di rotazione da ottimizzare entro limiti numerici assegnati. Restituire per ogni caso giri, coppia e potenza meccanica all'albero.
- Informazioni esterne sull'installazione necessarie a calcolare la spinta netta del gruppo. Le condizioni all'ingresso appena elencate sono input espliciti dell'utente; geometria del condotto e condizioni all'uscita/restanti condizioni al contorno sono ancora da definire, come dati fissi o attraverso un modello concordato, mai come variabili di progetto del condotto.
- Intervallo o catalogo di profili e vincoli geometrici delle sezioni, se il modello scelto usa profili aerodinamici.

Specificare se velocità di avanzamento e assetto siano assiali. Se si vogliono condizioni inclinate, considerare angolo d'incidenza e forze laterali come requisiti aggiuntivi.

## Livelli di modello da valutare

1. **Disco attuatore / teoria della quantità di moto.** Rappresenta il rotore come salto di pressione, senza pale reali. È molto rapido per stimare l'ordine di grandezza di spinta e potenza ideale in condizioni assiali; non restituisce corda, calettamento o carichi delle singole pale. Se il disco non è accoppiato a un modello del condotto, non predice la spinta netta installata.
2. **Elementi di pala (BET).** Divide ogni pala in sezioni e usa coefficienti aerodinamici dei profili per stimare spinta e coppia. Può progettare la distribuzione radiale della pala, ma da solo tratta in modo semplificato l'induzione del flusso e le interazioni tridimensionali.
3. **BEMT adattata alla ventola intubata.** Accoppia elementi di pala e bilancio di quantità di moto, aggiungendo un modello del condotto, delle correzioni di punta e, se presenti, delle palette statoriche. È una buona candidata per dimensionamento preliminare: letteratura tecnica documenta applicazioni a volo statico e assiale, ma accuratezza e calibrazioni dipendono dal caso. La geometria fissa del condotto e dati aerodinamici affidabili sono necessari per la spinta netta.
4. **CFD del rotore e del condotto.** Risolve il campo di flusso tridimensionale attorno alle pale e al condotto fornito. È la candidata più completa per calcolare separatamente e sommare contributi di pressione e parete, ma richiede geometria, mesh, condizioni al contorno, modelli di turbolenza e controlli di convergenza; i costi sono maggiori. L'adjoint può fornire gradienti rispetto alla geometria per SLSQP, se il solutore e la formulazione lo supportano. Non è applicabile al propulsore reale senza geometria del condotto.
5. **Modello a fedeltà mista.** Usa BEMT per esplorare rapidamente le geometrie e CFD su un numero ristretto di soluzioni per verificare e correggere i risultati. È un percorso pratico se sono disponibili geometria e risorse CFD, ma richiede correlazione fra i due modelli.

Percorso scelto: fedeltà mista a fasi. Primo prototipo con BEMT e ottimizzazione preliminare della ventola, verificato per coerenza e con limiti dichiarati; il risultato iniziale riguarda il rotore e non la spinta netta installata. In una fase successiva, quando sarà disponibile la geometria del condotto, CFD del gruppo completo e confronto BEMT-CFD per correggere/raffinare il progetto. Nessun coefficiente di guadagno del condotto va presunto nel prototipo.

## Ottimizzazione e calcolo dei gradienti

- Requisito per ogni condizione: spinta complessiva calcolata >= spinta minima assegnata, entro tolleranza numerica da definire.
- Obiettivo: minimizzare l'energia meccanica totale, somma della potenza all'albero per durata di ogni condizione.
- Confrontare candidati discreti di numero di pale (2–8 inclusi, intervallo iniziale concordato); per ciascuno risolvere il problema continuo.
- Variabili continue iniziali candidate: diametro del mozzo, parametri che descrivono corda e calettamento, regime per ciascun punto. Diametro esterno e geometria del condotto restano fissi.
- SLSQP è l'ottimizzatore vincolato candidato. Adjoint è un possibile metodo per ottenere i gradienti di obiettivo e vincoli, non un ottimizzatore alternativo. La sua fattibilità dipende dal solutore e dal modello effettivi.
- Verificare i gradienti adjoint con differenze finite su casi rappresentativi; verificare separatamente convergenza del flusso, convergenza dell'ottimizzazione e soddisfacimento dei requisiti.

## Riferimenti tecnici

- NASA, [Ducted-Fan Force and Moment Control via Steady and Synthetic Jets](https://fun3d.larc.nasa.gov/papers/AIAA-2009-3622.pdf): spiega che l'aspirazione indotta dalla ventola crea contributi di pressione sulla bocca del condotto e quindi alla forza netta del gruppo.
- NASA, [Investigation of Pneumatic Inlet and Diffuser Blowing on a Ducted Fan Propulsor](https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/20040001424.pdf): analizza la dipendenza delle prestazioni dal condotto e dal regime operativo.
- SU2, [Shape Optimization with the Discrete Adjoint](https://su2code.github.io/docs_v7/Setup-Guide-Shape-Optimization/): descrive sensibilità adjoint, workflow di ottimizzazione e confronto dei gradienti con differenze finite. Riferimento metodologico, non scelta già approvata del software.

## Riferimento Astrobee per l'ordine di grandezza della spinta

Documentazione NASA descrive Astrobee come due moduli propulsivi, ciascuno con una girante centrifuga che pressurizza un plenum; sei ugelli per modulo generano le forze nei diversi assi. Un requisito pubblicato è 0,6 N massimi su almeno un asse, per il sistema propulsivo del robot. Fonte: NASA, [Astrobee Free-Flyer Nozzle Mechanism](https://ntrs.nasa.gov/api/citations/20200010327/downloads/20200010327.pdf?attachment=true).

Il requisito pubblicato da NASA di 0,6 N massimi su almeno un asse riguarda il sistema propulsivo Astrobee, costituito da moduli multipli con giranti centrifughe, plenum e ugelli. Nel progetto COMPANION si mantiene invece il rotore assiale intubato stabilito dall'utente. Perciò 0,6 N è adottato soltanto come riferimento d'ordine di grandezza per un caso dimostrativo di spinta assiale del nostro modello; non è una specifica trasferita da Astrobee né una prestazione garantita.

## Decisioni necessarie prima della formulazione quantitativa

1. Specificare nel report che il contributo del condotto è indeterminato finché mancano geometria o dati di prova.
2. Definire intervallo e precisione richiesti per la prima stima rotorica BEMT.
3. La ventola e il condotto sono allineati all'asse del moto, oppure vanno previsti angoli di incidenza?

Senza informazioni sul condotto o un modello installato validato, il programma può stimare le prestazioni rotoriche, ma non la spinta complessiva reale del gruppo intubato. Questo limite va riportato accanto ai risultati e nella specifica degli input.
