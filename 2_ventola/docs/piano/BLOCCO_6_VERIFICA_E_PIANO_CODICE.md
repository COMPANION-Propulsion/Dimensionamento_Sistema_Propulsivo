# Blocco 6 — Verifica e passaggio al codice

Stato: primo incremento geometrico implementato ed eseguito. Quattro test superati: simmetria/spessore NACA, linea media camberata, rispetto del diametro e scalatura, rifiuto degli input non validi. BEMT, polari e ottimizzazione ancora da implementare; i test geometrici non costituiscono validazione aerodinamica.

## Decisioni di modellazione raccolte

- Rotore assiale intubato, indipendente dal Venturi; condotto non ottimizzato.
- Primo livello: BEMT rotorica per dimensionamento preliminare; CFD del gruppo con condotto in una fase successiva, quando sarà disponibile la geometria.
- La spinta di 0,6 N è un valore dimostrativo orientato dal riferimento Astrobee, non requisito NASA trasferito né garanzia della spinta del propulsore del progetto.
- La pala viene generata dallo script. Diametro esterno fissato dall'utente; mozzo, distribuzioni di corda e calettamento ottimizzati.
- Candidati iniziali: 2–8 pale e profili NACA dal catalogo interno. Proposta per il prototipo: un solo tipo di profilo lungo tutta la pala, confrontato come scelta discreta; profilo variabile lungo il raggio rimandato.
- Condizioni d'esempio: statico e avanzamento assiale lento; spinta minima, velocità, durata e condizioni dell'aria dichiarate nel file d'input.
- Obiettivo: minimizzare energia meccanica all'albero sul profilo d'uso; vincolo di spinta minima in ogni caso.
- Ottimizzatore candidato: SLSQP. Adjoint solo se supportato dalla formulazione e dal solutore; non è un'alternativa a SLSQP.
- Il prototipo senza geometria o prove del condotto riporta prestazioni rotoriche, non spinta netta installata.

## Verifiche richieste

1. Controllare unità, conversioni, vincoli e proprietà termodinamiche dell'aria.
2. Verificare la generazione geometrica: raggi entro mozzo e punta, corda positiva, angoli finiti e variazioni regolari.
3. Verificare la soluzione BEMT per residuo dell'induzione, convergenza, segni di spinta/coppia e bilancio di potenza.
4. Verificare almeno casi limite statico, piccolo avanzamento, spinta non raggiungibile entro i bounds e input fuori dal campo coperto dalle polari.
5. Confrontare un caso con una fonte o un calcolo indipendente adatto alla stessa configurazione. Documentare la validazione disponibile e l'incertezza; la sola convergenza numerica non convalida il modello.
6. Verificare i gradienti passati a SLSQP con differenze finite. Ricontrollare la soluzione finale con il modello diretto e riferire esplicitamente quali vincoli sono soddisfatti.
7. Separare nel report: successo numerico dell'ottimizzatore, soddisfacimento della spinta rotorica prevista e validità rispetto alla spinta installata. Senza condotto il terzo punto rimane non verificato.

## Ordine di implementazione

1. Consolidare il caso dimostrativo in un file di configurazione, rendendo ogni valore modificabile e marcando le assunzioni.
2. Implementare caricamento e validazione degli input e generazione delle sezioni geometriche da profilo.
3. Aggiungere proprietà dell'aria, BEMT per un singolo punto e confronti di riferimento.
4. Aggiungere più condizioni operative e funzione obiettivo energia con vincoli di spinta.
5. Aggiungere SLSQP per la geometria continua e confronto dei candidati discreti (numero pale/profilo).
6. Esportare tabella geometrica e report dei risultati, delle fonti e dei limiti.
7. Quando arriveranno dati del condotto, aggiungere il ramo CFD e confrontare/correggere il modello BEMT.

Il prototipo può iniziare dopo aver finalizzato il file d'input e chiarito il limite di applicabilità della stima di spinta. Le polari NACA nel catalogo sono ancora da generare o acquisire a Reynolds e Mach pertinenti, dunque l'ottimizzazione fisica non va dichiarata pronta finché non vengono aggiunte e verificate.
