# Confronto SLSQP del catalogo

Coppie esaminate: 28. Accettate: 9.
Un solo avvio locale per coppia; nessuna garanzia di minimo globale.
I casi scartati non dimostrano impossibilita fisica. Dettagli in comparison.csv.

| Profilo | Pale | Energia [J] | Esito |
|---|---:|---:|---|
| NACA2412 | 3 | 6261.61 | Accettato |
| NACA2412 | 4 | 6577.64 | Accettato |
| NACA4412 | 2 | 6693.78 | Accettato |
| NACA2412 | 6 | 7055.71 | Accettato |
| NACA4412 | 3 | 7060.80 | Accettato |
| NACA2412 | 7 | 7319.20 | Accettato |
| NACA4412 | 4 | 7320.81 | Accettato |
| NACA4412 | 6 | 7885.10 | Accettato |
| NACA4415 | 3 | 7898.36 | Accettato |
| NACA0012 | 2 | 5748.29 | Vincolo violato nella verifica a 64 anelli |
| NACA2412 | 2 | 5888.68 | Iteration limit reached |
| NACA0012 | 3 | 5932.98 | Vincolo violato nella verifica a 64 anelli |
| NACA0012 | 4 | 6035.77 | Vincolo violato nella verifica a 64 anelli |
| NACA0012 | 6 | 6381.90 | Iteration limit reached |
| NACA4415 | 5 | 7716.45 | Inequality constraints incompatible; Vincolo violato nella verifica a 64 anelli |
| NACA4415 | 7 | 9809.53 | Iteration limit reached; Vincolo violato nella verifica a 64 anelli |
| NACA0012 | 5 | — | Iteration limit reached; Re=4996.67 fuori [5000, 150000] |
| NACA0012 | 7 | — | Nessun seme ammissibile trovato; fattibilita non determinata |
| NACA0012 | 8 | — | Nessun seme ammissibile trovato; fattibilita non determinata |
| NACA2412 | 5 | — | Inequality constraints incompatible; Re=4985.9 fuori [5000, 150000] |
| NACA2412 | 8 | — | Nessun seme ammissibile trovato; fattibilita non determinata |
| NACA4412 | 5 | — | Iteration limit reached; Re=4958.3 fuori [5000, 150000] |
| NACA4412 | 7 | — | Iteration limit reached; Re=4991.73 fuori [5000, 150000] |
| NACA4412 | 8 | — | Nessun seme ammissibile trovato; fattibilita non determinata |
| NACA4415 | 2 | — | alpha=24.027 fuori [-12, 24] |
| NACA4415 | 4 | — | Iteration limit reached; alpha=25.3491 fuori [-12, 24] |
| NACA4415 | 6 | — | Inequality constraints incompatible; alpha=24.0018 fuori [-12, 24] |
| NACA4415 | 8 | — | Nessun seme ammissibile trovato; fattibilita non determinata |

Migliore accettato: NACA2412, 3 pale.
Verifica aggiuntiva a 128 anelli: SUPERATA.
Limiti geometrici raggiunti: Mozzo al limite inferiore; Corda nodo 1 al limite superiore; Corda nodo 2 al limite superiore; Corda nodo 3 al limite superiore

Modello preliminare del solo rotore. Perdite di punta/mozzo e condotto non modellati;
polari numeriche, nessuna validazione sperimentale o verifica strutturale.
