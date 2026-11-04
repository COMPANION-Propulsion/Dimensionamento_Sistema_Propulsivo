# Polari numeriche del catalogo

Generate con `python -m ventola_designer.generate_polars`, usando le coordinate
analitiche prodotte da `geometry.naca4` (80 pannelli per lato). Ogni JSON conserva
coordinate, hash SHA256, versioni dei pacchetti e ipotesi; il DAT permette di
ispezionare le coordinate fornite al modello. Questi file non sono misure.

Metodo: [NeuralFoil](https://github.com/peterdsharpe/NeuralFoil) 0.3.3 tramite
AeroSandbox 4.2.10, modello xlarge, Ncrit=9, transizione libera, correzioni di
compressibilita e modello post-stallo predefiniti di AeroSandbox.

Griglia per ogni profilo (3504 punti):

- Re: 2000, 3000, 5000, 10000, 20000, 30000, 50000, 75000, 100000, 150000 (2000 e 3000 aggiunti il 2026-11-04; confidenza NeuralFoil >= 0.89 fra 0 e 10 gradi).
- Mach: 0, 0.1, 0.2, 0.3, 0.45, 0.5.
- Alpha: da -12 a 24 gradi, passo 0.5 gradi.

Il BEMT interpola in alpha, log(Re) e Mach; non estrapola. Richiede una confidence
di almeno 0.5 in tutti i nodi con peso positivo. Questo indicatore del modello non
e una probabilita di accuratezza sperimentale. La soglia e una scelta di screening.

## Coerenza geometrica e approssimazione

Il modello riceve le coordinate del profilo usato nella pala, ma AeroSandbox le
normalizza e approssima con 8 pesi Kulfan per lato. Il campo `kulfan_fit_error`
misura lo scarto verticale alle ascisse dei punti normalizzati; non misura errore
aerodinamico e non e una distanza normale alla superficie. Lo scarto massimo
registrato e circa 0.0107% della corda per NACA0012, 0.213% per NACA2412, 0.0267%
per NACA4412 e 0.0387% per NACA4415. Questa approssimazione e esplicita: non si
assume una coincidenza geometrica esatta del modello interno.

Non sono state validate sperimentalmente le previsioni ai bassi Reynolds.
La disponibilita della tabella non certifica l'idoneita del profilo alla ventola.
