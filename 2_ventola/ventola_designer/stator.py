"""
Statore dopo il rotore: raddrizza il flusso e trasforma lo swirl in pressione assiale.

Modello per anello (raggio r), primo ordine, schiera di N pale a solidita costante:

    c1      swirl all'uscita del rotore (2b del BEMT), Va velocita assiale
    W_m     velocita media nello statore = sqrt(Va^2 + (c1/2)^2)
    alpha_m angolo medio del flusso dall'asse = atan(c1 / (2 Va))
    sigma   solidita = c N / (2 pi r)

Quantita di moto tangenziale: per togliere tutto lo swirl serve

    CL = 2 c1 / (sigma W_m)

Il profilo (polari NeuralFoil) da l'incidenza e il CD a quel CL e al Reynolds
locale. La perdita di pressione totale della schiera e

    dp0_perso = sigma CD (rho W_m^2 / 2) W_m / Va

e il recupero e (rho c1^2 / 2) - dp0_perso. Se il CL richiesto supera il
massimo del profilo, la schiera toglie solo la frazione f = CL_max / CL dello
swirl (stallo): il resto esce col getto. Deviazione all'uscita trascurata.

Il calettamento della pala dall'asse e gamma = alpha_m - incidenza.
Coppia: lo statore riceve dal flusso la coppia del rotore per la frazione di
swirl tolta, con verso opposto: la coppia netta sul veicolo scende di tanto.
"""
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from .polars import PolarDomainError, PolarGrid

POLARS = Path(__file__).parent/'airfoils'/'polars_neuralfoil'
ALPHA_SCAN = np.arange(-4.0, 16.01, 0.25)    # incidenze provate [gradi]
DEFAULTS = dict(enabled=False, vanes=None, solidity=1.0, profile='NACA4412',
                axial_gap_m=0.002)


@lru_cache(maxsize=8)
def _polar(profile):
    return PolarGrid.load(POLARS/f'{profile}.json')


def settings(case):
    """Impostazioni dello statore del caso, con i default."""
    s = {**DEFAULTS, **(case.get('stator') or {})}
    if s['enabled'] and not 0.2 <= float(s['solidity']) <= 3.0:
        raise ValueError('Solidita dello statore fuori da 0.2-3.')
    return s


def vane_count(rotor_blades, requested=None):
    """Pale dello statore: la richiesta, oppure il primo numero >= 7 primo con il rotore.

    Numeri primi fra loro evitano che tutte le pale del rotore passino davanti
    alle pale dello statore nello stesso istante (rumore e vibrazioni).
    """
    if requested:
        return int(requested)
    n = 7
    while math.gcd(n, rotor_blades) != 1:
        n += 1
    return n


def ring(r, va, c1, rho, mu, sound, s, n_vanes):
    """Recupero di un anello: dict con perdita, recupero, geometria e stato."""
    w = math.hypot(va, 0.5*c1)
    alpha_m = math.atan2(0.5*c1, va)
    sigma = float(s['solidity'])
    chord = sigma*2*math.pi*r/n_vanes
    q_swirl = 0.5*rho*c1*c1
    if c1 <= 1e-9:
        return dict(recovered_Pa=0.0, loss_Pa=0.0, removed=1.0, cl=0.0, cd=0.0,
                    alpha_deg=0.0, stagger_deg=0.0, chord_m=chord, Re=rho*w*chord/mu, stalled=False)
    cl_need = 2.0*c1/(sigma*w)
    re, mach = rho*w*chord/mu, w/sound
    polar = _polar(s['profile'])
    table = []
    for a in ALPHA_SCAN:
        try:
            cl, cd, _ = polar.coefficients(float(a), re, mach)
            table.append((float(a), cl, cd))
        except PolarDomainError:
            continue
    if not table:
        raise PolarDomainError(f'Statore: Re={re:.0f} fuori dal dominio delle polari.')
    best = max(table, key=lambda t: t[1])
    stalled = cl_need > best[1]
    if stalled:
        a, cl, cd = best
        removed = best[1]/cl_need
    else:
        # primo punto della polare che arriva al CL richiesto, interpolato
        for (a0, cl0, cd0), (a1, cl1, cd1) in zip(table, table[1:]):
            if cl0 <= cl_need <= cl1:
                t = (cl_need - cl0)/(cl1 - cl0) if cl1 > cl0 else 0.0
                a, cl, cd = a0 + t*(a1 - a0), cl_need, cd0 + t*(cd1 - cd0)
                break
        else:
            a, cl, cd = table[0]
        removed = 1.0
    loss = sigma*cd*0.5*rho*w*w*w/va
    residual = (1.0 - removed)*c1
    recovered = q_swirl - 0.5*rho*residual*residual - loss
    return dict(recovered_Pa=recovered, loss_Pa=loss, removed=removed, cl=cl, cd=cd,
                alpha_deg=a, stagger_deg=math.degrees(alpha_m) - a, chord_m=chord, Re=re,
                stalled=stalled, flow_angle_deg=math.degrees(alpha_m))
