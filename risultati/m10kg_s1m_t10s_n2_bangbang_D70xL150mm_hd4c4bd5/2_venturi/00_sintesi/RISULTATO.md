# Venturi: dalla spinta al salto di pressione

## Per la ventola

| grandezza | valore |
|---|---|
| **Δp disco** | **38.1101 ± 0.0109 Pa** |
| diametro ventola | 58.13 mm |
| centro ventola da ingresso condotto | 17.50 mm |
| spessore assiale ventola | 10.00 mm |
| portata | 21.3877 L/s (25.7508 g/s) |
| velocità sul disco | 8.058 m/s |
| potenza data al fluido (Δp·Q) | 0.8151 W |

## Spinta

- richiesta per ugello: 0.2 N (da `risultati\m10kg_s1m_t10s_n2_bangbang_D70xL150mm_hd4c4bd5\1_spinta\spinta.json`)
- calcolata sulla griglia fine: 0.2 N, dal bilancio delle forze 0.19749 N
- errore di griglia (GCI): ±5.818e-05 N (0.03 %), estrapolata 0.19993 N
- spinta / potenza: 0.2454 N/W

## Geometria

- condotto: D ingresso 59.60 mm, D ventola 58.13 mm, D uscita 60.00 mm, L 40.73 mm, A_uscita/A_disco 1.065
- tubo: D esterno 70.00 mm (max 70.00), L 50.45 mm (max 150.00), parete 2.00 mm, condotto interno max 60.00 mm
- ingombro rispettato: sì

## Flusso

- Mach massimo 0.0277, y+ massimo 0.31
- salto di pressione totale sul disco (media pesata sulla portata): 37.618 Pa
- getto ideale 7.956 m/s, velocità media d'uscita 7.564 m/s

## Numerica

- griglia del risultato 180x72, studio di griglia su 180x72, 128x51, 90x36, modello `baldwin_lomax`
- esponente T ~ Δp^k: k = 1.0132
- STL chiusi: NO

## Avvertenze

- Flusso invertito in 292 celle, margine di separazione -0.018.

## Cartelle

- `01_grafici/`: geometria, mappe del campo, profili assiali, parete, profili radiali, convergenza
- `02_excel/venturi_risultati.xlsx`: tutti i numeri, foglio per argomento
- `03_cad/`: `tubo`, `fluido`, `zona_disco` in STEP e STL (mm, asse x), patch STL del fluido per la CFD, profilo DXF e CSV
- `04_cfd/`: campi per ParaView (2D e 3D) e nuvola di punti
- `05_convergenza/`: `design.json`, storie SLSQP, ciclo su Δp, studio di griglia

Nota: la spinta è quella interna netta; la resistenza esterna della gondola non è calcolata. Con disco ideale la spinta statica vale 2·Δp·A_uscita: a spinta data il Δp minimo chiede l'uscita più larga possibile. Con diametro e posizione della ventola liberi, l'ottimo tende quindi a un condotto dritto al diametro interno massimo, corto quanto i limiti permettono (meno attrito); i limiti di lunghezza minima e le perdite reali della ventola (mozzo, gioco di estremità) non sono nel modello.
