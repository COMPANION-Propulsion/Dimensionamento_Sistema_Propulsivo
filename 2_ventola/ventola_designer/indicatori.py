"""
Indicatori a posteriori per confrontare ventole (3 contro 4 pale): rumore, carichi centrifughi,
squilibrio. Sono STIME in forma chiusa su un progetto gia dimensionato, non risultati del BEMT
ne di una verifica strutturale o acustica.

Modello (pala piena, densita uniforme, raggio r dal mozzo Rh alla punta R):

    A(r)    area della sezione = a_naca c(r)^2, con a_naca = area del contorno NACA a corda 1
    m       massa pala = rho integrale A dr
    r_cg    raggio del baricentro = integrale(A r dr) / integrale(A dr)
    F       forza centrifuga alla radice = integrale(rho A omega^2 r dr)
    sigma   sforzo medio alla radice = F / A(Rh)
    U       squilibrio statico caso peggiore = (m_max - m_min) r_cg max_j sin(j pi/Z)/sin(pi/Z)
    I       inerzia delle pale = Z integrale(rho A r^2 dr);  H = I omega

Rumore: solo l'indice di confronto differenza_rumore_dB, da U_punta.
"""
import argparse
import json
import math
import sys

import numpy as np

from .geometry import interpolate, naca4

T_ARIA_K = 293.0
GAMMA_ARIA, R_ARIA = 1.4, 287.05
IPOTESI = ("Pala piena, densita uniforme, nessuna flessione, niente concentrazione di sforzo "
           "al raccordo, squilibrio solo da densita; stime in forma chiusa, non una verifica.")


def area_naca(profilo, pannelli=200):
    """Area del profilo a corda 1 (formula dei lacci sul contorno)."""
    pts = naca4(profilo, pannelli)
    x = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    return 0.5 * abs(float(np.sum(x*np.roll(y, -1) - np.roll(x, -1)*y)))


def differenza_rumore_dB(U_a, U_b, esponente=5.5):
    """Differenza d'indice di rumore passando dalla ventola A alla B [dB].

    La potenza sonora di ventole assiali a bassa velocita scala circa con U_punta^5..6, quindi
    dL = 10 esponente log10(U_b / U_a). E solo un indice di confronto fra due ventole dello
    stesso tipo (stesso profilo, stessa installazione): non e un livello sonoro. Negativo se
    B e piu lenta di A.
    """
    if U_a <= 0 or U_b <= 0:
        raise ValueError("Le velocita di punta devono essere positive.")
    return 10.0 * esponente * math.log10(U_b / U_a)


def fattore_squilibrio(Z):
    """Caso peggiore: max_j sin(j pi/Z) / sin(pi/Z), j = 1..Z-1 (1 per Z=2,3; sqrt(2) per Z=4)."""
    if Z < 2:
        raise ValueError("Servono almeno 2 pale.")
    return max(math.sin(j*math.pi/Z) for j in range(1, Z)) / math.sin(math.pi/Z)


def indicatori(design, caso, densita_kg_m3=1240.0, tolleranza_densita=0.04, stazioni=401):
    Z = int(design["blade_count"])
    R = design["outer_diameter_m"] / 2
    Rh = design["hub_diameter_m"] / 2
    if not 0 < Rh < R:
        raise ValueError("Mozzo non valido rispetto al raggio esterno.")
    rpm = float(caso["rpm"])
    omega = rpm * 2*math.pi/60
    rho = densita_kg_m3
    a_naca = area_naca(design["profile"])

    r = np.linspace(Rh, R, stazioni)
    s = (r - Rh) / (R - Rh)
    corda = np.array([interpolate(design["span_nodes"], design["chord_m"], float(v)) for v in s])
    A = a_naca * corda**2                                   # [m^2]

    def integra(f):                                         # trapezi lungo r
        return float(np.sum((f[1:] + f[:-1]) * np.diff(r)) / 2)

    massa = rho * integra(A)                                # [kg]
    r_cg = integra(A*r) / integra(A)
    F = rho * omega**2 * integra(A*r)                       # [N]
    sigma = F / A[0]                                        # [Pa]
    d_massa = 2 * tolleranza_densita * massa
    squilibrio = d_massa * r_cg * fattore_squilibrio(Z)     # [kg m]
    inerzia = Z * rho * integra(A*r**2)                     # [kg m^2]

    U = omega * R
    a_suono = math.sqrt(GAMMA_ARIA * R_ARIA * T_ARIA_K)
    return {
        "pale": Z,
        "rpm": rpm,
        "velocita_punta_m_s": U,
        "mach_punta": U / a_suono,
        "frequenza_rotazione_Hz": rpm / 60,
        "frequenza_passaggio_pale_Hz": Z * rpm / 60,
        "massa_pala_g": massa * 1e3,
        "raggio_baricentro_mm": r_cg * 1e3,
        "forza_centrifuga_radice_N": F,
        "area_radice_mm2": A[0] * 1e6,
        "sforzo_centrifugo_radice_MPa": sigma / 1e6,
        "squilibrio_caso_peggiore_g_mm": squilibrio * 1e6,
        "forza_rotante_squilibrio_N": squilibrio * omega**2,
        "inerzia_pale_kg_m2": inerzia,
        "momento_angolare_pale_kg_m2_s": inerzia * omega,
        "ipotesi": IPOTESI,
    }


def _caso(run):
    """Punto di funzionamento di riferimento: quello a giri massimi (carichi peggiori)."""
    return max(run["cases"], key=lambda c: c["rpm"])


def confronta(run_a, run_b, **kw):
    """Differenze percentuali (B rispetto ad A) delle grandezze principali e rumore in dB."""
    a = indicatori(run_a["design"], _caso(run_a), **kw)
    b = indicatori(run_b["design"], _caso(run_b), **kw)
    chiavi = ["velocita_punta_m_s", "frequenza_passaggio_pale_Hz", "massa_pala_g",
              "forza_centrifuga_radice_N", "sforzo_centrifugo_radice_MPa",
              "squilibrio_caso_peggiore_g_mm", "forza_rotante_squilibrio_N",
              "inerzia_pale_kg_m2", "momento_angolare_pale_kg_m2_s"]
    out = {k + "_diff_pct": 100 * (b[k] / a[k] - 1) for k in chiavi}
    out["rumore_diff_dB"] = differenza_rumore_dB(a["velocita_punta_m_s"], b["velocita_punta_m_s"])
    return out


def _migliori(report, pale=None):
    best = {}
    for run in report["runs"] + [report["best"]]:
        if not run.get("accepted") or "design" not in run:
            continue
        z = run["design"]["blade_count"]
        if pale and z not in pale:
            continue
        if z not in best or run["energy_J"] < best[z]["energy_J"]:
            best[z] = run
    return dict(sorted(best.items()))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ventola_designer.indicatori",
                                 description="Indicatori a posteriori (stime) per numero di pale.")
    ap.add_argument("report")
    ap.add_argument("--pale", type=int, nargs="+")
    args = ap.parse_args(argv)
    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)
    best = _migliori(report, args.pale)
    if not best:
        print("Nessun progetto accettato per i numeri di pale richiesti.", file=sys.stderr)
        return 1
    ind = {z: indicatori(run["design"], _caso(run)) for z, run in best.items()}
    righe = [("energia/potenza albero [W]", lambda z: best[z]["energy_J"], "{:.3f}"),
             ("giri [rpm]", lambda z: ind[z]["rpm"], "{:.0f}"),
             ("velocita punta [m/s]", lambda z: ind[z]["velocita_punta_m_s"], "{:.2f}"),
             ("Mach punta", lambda z: ind[z]["mach_punta"], "{:.4f}"),
             ("freq. passaggio pale [Hz]", lambda z: ind[z]["frequenza_passaggio_pale_Hz"], "{:.0f}"),
             ("massa pala [g]", lambda z: ind[z]["massa_pala_g"], "{:.3f}"),
             ("raggio baricentro [mm]", lambda z: ind[z]["raggio_baricentro_mm"], "{:.2f}"),
             ("forza centrifuga radice [N]", lambda z: ind[z]["forza_centrifuga_radice_N"], "{:.2f}"),
             ("sforzo radice [MPa]", lambda z: ind[z]["sforzo_centrifugo_radice_MPa"], "{:.3f}"),
             ("squilibrio peggiore [g mm]", lambda z: ind[z]["squilibrio_caso_peggiore_g_mm"], "{:.3f}"),
             ("forza rotante squilibrio [N]", lambda z: ind[z]["forza_rotante_squilibrio_N"], "{:.4f}"),
             ("inerzia pale [kg m^2]", lambda z: ind[z]["inerzia_pale_kg_m2"], "{:.3e}"),
             ("momento angolare [kg m^2/s]", lambda z: ind[z]["momento_angolare_pale_kg_m2_s"], "{:.3e}")]
    zs = list(best)
    print(f"{'':32}" + "".join(f"{z:>10} pale" for z in zs))
    for nome, f, fmt in righe:
        print(f"{nome:32}" + "".join(f"{fmt.format(f(z)):>15}" for z in zs))
    if len(zs) >= 2:
        d = differenza_rumore_dB(ind[zs[0]]["velocita_punta_m_s"], ind[zs[1]]["velocita_punta_m_s"])
        print(f"\nIndice rumore {zs[1]} vs {zs[0]} pale: {d:+.1f} dB (solo confronto, non un livello)")
    print("\nIpotesi:", IPOTESI)
    return 0


if __name__ == "__main__":
    sys.exit(main())
