# Esito del dimensionamento

Soluzione accettata nel modello preliminare.

Diametro imposto: 100.000 mm.
Spinta riferita al solo rotore; velocita assiale riferita alla corrente lontano a monte.

## Requisiti e condizioni

| Punto | Spinta minima [N] | Velocita [m/s] | Durata [s] | T [K] | p statica [Pa] |
|---|---:|---:|---:|---:|---:|
| static | 0.6 | 0 | 600 | 295.15 | 101325 |
| slow_forward_flight | 0.6 | 0.5 | 600 | 295.15 | 101325 |

## Risultato

Profilo: NACA4412. Pale: 2. Mozzo: 20.000 mm.
Energia meccanica del ciclo: 6694.151 J.
Ottimo locale fra i tentativi accettati; minimo globale non garantito.

| Punto | Spinta [N] | Margine sul requisito [N] | Potenza albero [W] | Coppia [Nm] | rpm |
|---|---:|---:|---:|---:|---:|
| static | 0.601311 | 0.001311 | 5.4981 | 0.005628 | 9328.34 |
| slow_forward_flight | 0.601305 | 0.001305 | 5.6588 | 0.005723 | 9442.34 |

Il margine tabulato e rispetto al requisito utente, non al requisito maggiorato dal margine numerico.

| Posizione radiale normalizzata | Corda [mm] | Calettamento [gradi] |
|---:|---:|---:|
| 0.000 | 22.000 | 28.518 |
| 0.350 | 22.000 | 20.832 |
| 0.700 | 22.000 | 13.114 |
| 1.000 | 22.000 | 11.207 |

Minimo vincolo normalizzato alla verifica: 0.00017493694936820958.
I dettagli di convergenza, griglia e polari sono in optimization.json.

## Screening geometrico

Stazioni controllate: 129.
Minimo spazio circonferenziale fra inviluppi: 11.9913 mm; richiesto 0.0000 mm.
Minimo degli spessori massimi delle sezioni: 2.6400 mm; richiesto 0.0000 mm.
Controllo su sezioni campionate; non distanza minima 3D, controllo dei bordi sottili o verifica strutturale.

## Tentativi

| Profilo | Pale | Esito | Diagnostica |
|---|---:|---|---|
| NACA4412 | 2 | Accettato | Verifiche del dimensionatore superate |

## Limiti

Polari numeriche, assenza di validazione sperimentale e verifica strutturale.
Modello perdite: none.
none esclude le perdite; prandtl_free_rotor e una correzione per rotore libero, non per ventola intubata. Il condotto non e modellato.
La convergenza numerica non certifica la prestazione reale o la costruibilita della pala.
