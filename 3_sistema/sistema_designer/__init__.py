"""
Condotto e ventola insieme: tutto quello che richiede entrambi, in risultati/<caso>/4_sistema/.

    data.py           letture dei risultati di spinta, venturi e ventola del caso
    stator_compare.py ventola con e senza statore, allo stesso dp richiesto
    mission_power.py  potenza nel tempo lungo la manovra: quando, quanto, energia
    spanwise.py       grandezze di rotore e statore lungo il raggio (grafici)
    assembly.py       CAD dell'assieme tubo + rotore + statore, viste 3D, file ParaView
    run.py            sequenza completa e RISULTATO.md del sistema
"""

from .run import run

__all__ = ["run"]
