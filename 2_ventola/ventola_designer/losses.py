"""Fattori Prandtl, NREL/TP-5000-63217 eq. 11-15; rotore libero.

Non descrivono il gioco di estremita o le pareti di una ventola intubata.
"""
import math


def prandtl_factors(blades, radius, hub, tip, phi):
    if type(blades) is not int or blades < 2:
        raise ValueError('Numero di pale intero >= 2 richiesto.')
    if not all(math.isfinite(v) for v in (radius,hub,tip,phi)) or not 0 < hub <= radius <= tip or hub >= tip:
        raise ValueError('Geometria o angolo non validi per Prandtl.')
    # Agli estremi F=0: il BEMT integra nei punti medi, senza dividere per zero.
    sine = abs(math.sin(phi))
    def factor(distance, scale):
        if distance == 0:
            return 0.0
        if sine == 0:
            return 1.0
        f = blades*distance/(2*scale*sine)
        # Forma stabile equivalente a 2/pi * acos(exp(-f)).
        return 2/math.pi*math.atan2(math.sqrt(-math.expm1(-2*f)),math.exp(-f))
    ft = factor(tip-radius,radius)
    fh = factor(radius-hub,hub)
    return ft, fh
