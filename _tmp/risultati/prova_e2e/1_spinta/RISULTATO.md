# Spinta richiesta

## Input

- distanza: 1 m, tempo: 10 s, massa: 10 kg
- profilo: `bang_bang`, frazione di crociera: 0
- ugelli per faccia: 2, fattore di margine: 1

## Risultato

| grandezza | valore |
|---|---|
| accelerazione | 0.04 m/s² |
| tempo di accelerazione (= frenata) | 5 s |
| tempo di crociera | 0 s |
| velocità massima | 0.2 m/s |
| spinta della faccia | 0.4 N |
| **spinta per ugello** | **0.2 N** |
| impulso per ugello (spinta + frenata) | 2 N s |

La frenata usa gli ugelli della faccia opposta con la stessa spinta.
Il venturi legge `T_ugello_N` da `spinta.json`.
