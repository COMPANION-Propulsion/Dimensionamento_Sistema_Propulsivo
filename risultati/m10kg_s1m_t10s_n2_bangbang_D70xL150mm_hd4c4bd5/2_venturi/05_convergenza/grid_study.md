# Thrust grid study

| grid | cells | h / h_finest | converged | y+ | thrust [N] | from forces [N] |
|---|---|---|---|---|---|---|
| 180 x 72 | 12960 | 1.000 | yes | 0.31 | 0.19993 | 0.19743 |
| 128 x 51 | 6528 | 1.409 | yes | 0.41 | 0.19993 | 0.19736 |
| 90 x 36 | 3240 | 2.000 | yes | 0.61 | 0.19998 | 0.19711 |

| grids (fine, middle, coarse) | observed order p | extrapolated thrust | GCI on the finest thrust | notes |
|---|---|---|---|---|
| 180x72, 128x51, 90x36 | 6.66 | 0.19993 | 0.000 % | ok |

Thrust: 0.1999 +/- 0.0001 N (0.03 %), extrapolated 0.1999 N, reliable.
