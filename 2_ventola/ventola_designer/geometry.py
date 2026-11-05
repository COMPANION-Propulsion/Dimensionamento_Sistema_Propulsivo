"""Geometria NACA 4 cifre e sezioni avvolte su cilindri coassiali.

Formule: https://www.pdas.com/naca456thick4.html e naca456mean2.html.
Bordo d'uscita a spessore finito, coefficiente quartico -0.1015.
"""
import math
import re
from .config import number


def naca4(profile, panels_per_side=80):
    if not re.fullmatch(r"NACA\d{4}", profile):
        raise ValueError("Richiesto un profilo NACA a quattro cifre.")
    if type(panels_per_side) is not int or panels_per_side < 8:
        raise ValueError("Servono almeno 8 pannelli per lato.")
    code = profile[4:]
    m, p, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    if t <= 0 or (m > 0 and p == 0):
        raise ValueError("Parametri NACA non validi.")
    upper, lower = [], []
    for i in range(panels_per_side + 1):
        x = (1 - math.cos(math.pi * i / panels_per_side)) / 2
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x*x
                      + 0.2843 * x**3 - 0.1015 * x**4)
        if m == 0:
            yc = slope = 0.0
        elif x <= p:
            yc, slope = m / p**2 * (2*p*x - x*x), 2*m / p**2 * (p-x)
        else:
            yc = m / (1-p)**2 * (1-2*p+2*p*x-x*x)
            slope = 2*m / (1-p)**2 * (p-x)
        theta = math.atan(slope)
        upper.append((x-yt*math.sin(theta), yc+yt*math.cos(theta)))
        lower.append((x+yt*math.sin(theta), yc-yt*math.cos(theta)))
    # Percorso TE superiore -> LE -> TE inferiore, senza duplicare il LE.
    return list(reversed(upper)) + lower[1:]


def interpolate(nodes, values, s):
    """Interpolazione cubica Hermite con derivata nulla ai nodi (C1)."""
    for i in range(len(nodes)-1):
        if s <= nodes[i+1]:
            u = max(0.0, (s-nodes[i]) / (nodes[i+1]-nodes[i]))
            w = u*u*(3-2*u)
            return (1-w)*values[i] + w*values[i+1]
    return values[-1]


def blade_nodes(rotor):
    """Nodi lungo l'apertura per corda e calettamento (interpolazione lineare fra nodi).

    Meno nodi = pala piu regolare: 2 nodi danno corda e calettamento lineari,
    senza salti fra radice e meta pala che il BEMT 2D non vede ma un flusso 3D
    pagherebbe in perdite. Default 4 (i test e il modo storico).
    """
    n = int(rotor.get("blade_nodes", 4))
    if n < 2:
        raise ValueError("Servono almeno 2 nodi lungo la pala.")
    if n == 4:
        return [0.0, 0.35, 0.7, 1.0]
    return [i/(n-1) for i in range(n)]


def initial_design(case, profile, blades):
    """Seme geometrico riproducibile; NON risolve il dimensionamento."""
    rotor = case["rotor"]
    if profile not in rotor["airfoil_candidates"] or blades not in rotor["blade_count_candidates"]:
        raise ValueError("Profilo o numero di pale non ammesso dal caso.")
    diameter = rotor["outer_diameter_m"]
    nodes = blade_nodes(rotor)
    seed_s = [0.0, 0.35, 0.7, 1.0]
    return {
        "status": "initial_geometry_not_optimized", "profile": profile, "blade_count": blades,
        "outer_diameter_m": diameter,
        "hub_diameter_m": sum(rotor["hub_diameter_bounds_m"])/2,
        "span_nodes": nodes,
        "chord_m": [diameter*interpolate(seed_s, [0.10, 0.16, 0.12, 0.06], s) for s in nodes],
        "pitch_deg": [interpolate(seed_s, [40.0, 30.0, 22.0, 15.0], s) for s in nodes],
        "note": "Corde e angoli sono un seme illustrativo modificabile, non derivato dalla spinta."
    }


def blade_sections(design, count=25, panels=80):
    if type(count) is not int or count < 2:
        raise ValueError("Occorrono almeno due stazioni radiali.")
    radius = number(design["outer_diameter_m"], "diametro")/2
    hub = number(design["hub_diameter_m"], "mozzo")/2
    if hub >= radius:
        raise ValueError("Mozzo maggiore del raggio esterno.")
    nodes, chords, angles = (design[k] for k in ("span_nodes", "chord_m", "pitch_deg"))
    if not (len(nodes) == len(chords) == len(angles) >= 2):
        raise ValueError("Nodi, corde e angoli devono avere la stessa lunghezza >= 2.")
    if nodes[0] != 0 or nodes[-1] != 1:
        raise ValueError("I nodi normalizzati devono iniziare a 0 e terminare a 1.")
    if any(not math.isfinite(v) for v in nodes+angles) or any(b <= a for a,b in zip(nodes,nodes[1:])):
        raise ValueError("Nodi non crescenti o angoli non finiti.")
    for c in chords:
        number(c, "corda")
    contour = naca4(design["profile"], panels)
    result = []
    for i in range(count):
        s = i/(count-1)
        r = hub+(radius-hub)*s
        c = interpolate(nodes, chords, s)
        angle = interpolate(nodes, angles, s)
        beta = math.radians(angle)
        xyz = []
        for x,y in contour:
            # Asse Z del rotore; quarto di corda come riferimento di calettamento.
            tangential = c*((x-0.25)*math.cos(beta)-y*math.sin(beta))
            z = c*((x-0.25)*math.sin(beta)+y*math.cos(beta))
            azimuth = tangential/r
            xyz.append((r*math.cos(azimuth), r*math.sin(azimuth), z))
        result.append({"radius_m": r, "chord_m": c, "pitch_deg": angle, "points": xyz})
    return result
