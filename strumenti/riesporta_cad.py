"""
riesporta_cad.py
================
Rigenera la cartella CAD (nomi chiari + versione per SolidWorks) dai risultati GIA calcolati.
Non ricalcola nulla: ne venturi, ne ventola, ne sistema. Legge i STEP/STL che ci sono, i
report.json e CAD_info.json, ricostruisce i solidi semplificati per SolidWorks (qualche
decina di secondi per catena) e scrive:

    <caso>/CAD/<variante>/   01_tubo.step ... 04_assieme.step, speculari/, stl/, solidworks/, LEGGIMI.txt
    <serie>/CAD/INDICE.txt   se la cartella data e una serie di casi

Uso (dalla cartella Dimensionamento_Sistema_Propulsivo):

    python strumenti/riesporta_cad.py risultati/Run_20261114_fine_Ottimizzato
    python strumenti/riesporta_cad.py risultati/Run_20261114_fine_Ottimizzato/massa_6
    python strumenti/riesporta_cad.py risultati/Run_20261114_fine_Ottimizzato/massa_6/Statore
    python strumenti/riesporta_cad.py <cartella> --senza-solidworks     solo copie con nomi chiari

Equivale a `python run_sistema.py --solo cad` ma non legge input.py: va bene anche per
risultati vecchi o copiati altrove. Un processo solo, un caso alla volta: la memoria resta bassa.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for folder in ("2_ventola", "3_sistema"):
    sys.path.insert(0, os.path.join(ROOT, folder))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Rigenera la cartella CAD dai risultati esistenti (nessun calcolo).")
    p.add_argument("cartella", help="serie, caso o catena (Statore / NoStatore) gia calcolati")
    p.add_argument("--senza-solidworks", action="store_true",
                   help="solo le copie con nomi chiari e il LEGGIMI.txt, senza ricostruire i solidi")
    args = p.parse_args(argv)
    path = os.path.abspath(args.cartella)
    if not os.path.isdir(path):
        print(f"Errore: {path} non e una cartella.")
        return 1
    from sistema_designer import cartella_cad
    try:
        kind, states = cartella_cad.rebuild(path, solidworks=not args.senza_solidworks, log=print)
    except ValueError as e:
        print(f"Errore: {e}")
        return 1
    print(f"\nFatto ({kind}). Stato delle catene:")
    bad = 0
    for case, rows in states.items():
        for s in rows:
            ok = s["completa"]
            bad += not ok
            print(f"  {os.path.basename(str(case))}/{s['variante'] or ''}: "
                  f"{'completa' if ok else 'INCOMPLETA: ' + '; '.join(s['problemi'][:2])}")
    return 0 if not bad else 3


if __name__ == "__main__":
    sys.exit(main())
