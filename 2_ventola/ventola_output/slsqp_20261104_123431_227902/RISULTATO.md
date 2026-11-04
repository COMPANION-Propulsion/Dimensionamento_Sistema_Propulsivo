# Dimensionamento a portata imposta

Candidato accettato nel modello preliminare.
Diametro esterno imposto: 0.0581344 m.
La portata e conservata; la velocita sulle pale e Q / area anulare libera.

| Condizione | Q [m3/s] | Delta p totale minimo [Pa] | V disco senza mozzo [m/s] | Durata [s] |
|---|---:|---:|---:|---:|
| venturi | 0.0213877 | 38.1101 | 8.05765 | 1 |

Sorgente venturi: C:\Users\Niccolò Mozzati\Desktop\Prop_Companion\Dimensionamento_Sistema_Propulsivo\risultati\m10kg_s1m_t10s_n2_bangbang_D70xL150mm_hd4c4bd5\2_venturi\00_sintesi\risultati.json.
Ciclo dp Venturi convergente: True; studio di griglia affidabile: True.
Questi stati descrivono il calcolo a monte e non sono validati dal dimensionatore della ventola.


Profilo NACA4412; pale 4; mozzo 0.024 m.
Energia meccanica del ciclo: 1.21895 J.

| Condizione | Q [m3/s] | Va pale [m/s] | Delta p totale [Pa] | Delta p statica [Pa] | Potenza albero [W] | Coppia [Nm] | rpm |
|---|---:|---:|---:|---:|---:|---:|---:|
| venturi | 0.0213877 | 9.71309 | 38.1908 | 34.3859 | 1.21895 | 0.00139744 | 8329.58 |

| Posizione normalizzata | Corda [m] | Calettamento [gradi] |
|---:|---:|---:|
| 0 | 0.0127896 | 45 |
| 0.35 | 0.0127896 | 45 |
| 0.7 | 0.0127896 | 33.3521 |
| 1 | 0.0127896 | 29.7211 |

| Profilo | Pale | Esito | Dettaglio |
|---|---:|---|---|
| NACA0012 | 2 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA0012 | 3 | not_accepted | Re=4950.04 fuori [5000, 150000] |
| NACA0012 | 4 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA0012 | 5 | not_accepted | Inequality constraints incompatible |
| NACA0012 | 6 | not_accepted | Re=4993.77 fuori [5000, 150000] |
| NACA0012 | 7 | converged_final_verified | Optimization terminated successfully |
| NACA0012 | 8 | not_accepted | Inequality constraints incompatible |
| NACA2412 | 2 | converged_final_verified | Optimization terminated successfully |
| NACA2412 | 3 | not_accepted | Re=4998.92 fuori [5000, 150000] |
| NACA2412 | 4 | not_accepted | Re=4977.27 fuori [5000, 150000] |
| NACA2412 | 5 | converged_final_verified | Optimization terminated successfully |
| NACA2412 | 6 | not_accepted | Inequality constraints incompatible |
| NACA2412 | 7 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA2412 | 8 | not_accepted | Re=4991.42 fuori [5000, 150000] |
| NACA4412 | 2 | converged_final_verified | Optimization terminated successfully |
| NACA4412 | 3 | converged_final_verified | Optimization terminated successfully |
| NACA4412 | 4 | converged_final_verified | Optimization terminated successfully |
| NACA4412 | 5 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4412 | 6 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4412 | 7 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4412 | 8 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4415 | 2 | converged_final_verified | Optimization terminated successfully |
| NACA4415 | 3 | not_accepted | Re=4973.46 fuori [5000, 150000] |
| NACA4415 | 4 | not_accepted | Re=4977.6 fuori [5000, 150000] |
| NACA4415 | 5 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4415 | 6 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4415 | 7 | not_accepted | Carico non positivo nel regime di compressione. |
| NACA4415 | 8 | not_accepted | Re=4991.3 fuori [5000, 150000] |

## Interpretazione

Pressione totale media pesata sulla portata; include energia cinetica dello swirl in uscita.
La potenza all’albero comprende il lavoro sul fluido e le perdite di profilo stimate dalle polari.
Spinta rotorica, potenza nello swirl, perdite e rendimento totale sono nel JSON.
La forza sul rotore non e la spinta complessiva del sistema Venturi.
Portata uniforme nell’anello, ingresso senza swirl, densita costante; interazioni di cascata,
perdite al mozzo/pareti e gioco di punta non modellati. Nessuna verifica accoppiata del condotto con il mozzo.
Il requisito e soddisfatto nel modello; convergenza e screening non costituiscono validazione sperimentale.
La ricerca SLSQP e locale; minimo globale non garantito.
