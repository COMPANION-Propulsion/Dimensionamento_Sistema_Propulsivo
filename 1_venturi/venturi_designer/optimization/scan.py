"""
scan.py
=======
Grid scan of the duct shape instead of SLSQP: few clear parameters, every case
solved for real, non-converged cases thrown away (never scored with a penalty).

Shape of every case, along the axis:

    bell mouth (CAD) -> intake, half cosine R_in -> R_fan -> straight fan section
    (2 L_disk) -> diffuser, half cosine R_fan -> R_exit over L_diff

    R_fan    fixed: VENTURI["D_ventola"] (None = the largest the bell mouth allows)
    R_exit   n_D values from R_fan to the inner limit (a nozzle when below R_fan)
    L_diff   n_L values; the intake takes the rest down to L_min overall

Each case is fitted with the morphing splines, so the rest of the chain (grid
study, export) works on it unchanged. A case is scored by

    without fan curve   thrust at a fixed dp (largest thrust = smallest dp for the
                        wanted thrust, the dp is set afterwards by the secant)
    with fan curve      thrust at the operating point on the curve (fan_curve.py)

Cases are not solved if they leave the size limits or if the wall downstream of the
disk is too steep. The two directions have separate limits: a diverging wall
(diffuser, may separate) is held to max_half_angle, a converging one (nozzle, no
separation) to MAX_CONV_HALF_ANGLE, the intake limit of the SLSQP problem. The row
holds both angles (semiangolo_deg = diverging, semiangolo_conv_deg = converging).
The wall shear in the diffuser is recorded for each, and
a case with negative wall shear in the diffuser (separated) is never chosen.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import replace
from typing import Dict, List, Optional

import numpy as np

from .fan_curve import FanCurve, operating_point
from .shape_opt import SLOPE_INTAKE, DuctProblem, for_grid, inlet_radius_limit, report
from ..core.propulsion import PropulsionCase
from ..export.cad import bell_envelope
from ..geometry.morph import MorphedGeometry, MorphLayout, fit_design

N_POINTS = 1500


def case_shape(case: PropulsionCase, layout: MorphLayout, R_fan: float, R_exit: float,
               L_diff: float, R_in: float) -> Optional[np.ndarray]:
    """Design vector of one case, or None if it does not fit."""
    l_env = bell_envelope(R_in, case.spessore_parete, case.raggio_bocca_su_D)[1]
    L_sec = layout.L_section
    L_in = max(1.0 * R_fan, (case.L_min or 0.0) - l_env - L_sec - L_diff)
    if L_in + L_sec + L_diff + l_env > case.L_max:
        return None
    zi = np.linspace(0.0, L_in, N_POINTS // 3)
    zd = np.linspace(0.0, L_diff, 2 * N_POINTS // 3)
    z = np.concatenate((zi, L_in + L_sec + zd))
    R = np.concatenate((R_fan + (R_in - R_fan) * 0.5 * (1 + np.cos(np.pi * zi / L_in)),
                        R_fan + (R_exit - R_fan) * 0.5 * (1 - np.cos(np.pi * zd / L_diff))))
    return fit_design(layout, z, R, L_in, L_in + L_sec, R_fan)


# A converging exit wall (nozzle) accelerates the flow and does not separate, so it
# gets the same limit as the intake wall in the SLSQP problem, not the diffuser one.
MAX_CONV_HALF_ANGLE = math.degrees(math.atan(SLOPE_INTAKE))


def half_angles_deg(geom: MorphedGeometry) -> tuple:
    """(diverging, converging) steepest wall half angles downstream of the disk [deg],
    both >= 0: the largest positive slope and the largest closing slope."""
    z = np.linspace(geom.z_b, geom.L_total, 400)
    s = geom.radius_derivative(z)
    return (float(np.degrees(np.arctan(max(np.max(s), 0.0)))),
            float(np.degrees(np.arctan(max(np.max(-s), 0.0)))))


def run_scan(case: PropulsionCase, layout: MorphLayout, grid, curve: Optional[FanCurve],
             D_fan: Optional[float], n_D: int = 5, n_L: int = 4, max_half_angle: float = 4.0,
             P_max: Optional[float] = None, out_dir: Optional[str] = None,
             verbose: bool = True) -> Dict:
    """Solve all the cases; return the table and the best one (problem solved, design)."""
    from ..export.fields import duct_fields
    case = for_grid(case, *grid)
    R_in = min(inlet_radius_limit(case), case.R_int_max)
    R_fan = 0.5 * D_fan if D_fan else R_in
    if R_fan > R_in + 1e-9:
        raise ValueError(f"D_ventola {2e3*R_fan:.1f} mm is larger than the inlet allows "
                         f"({2e3*R_in:.1f} mm).")
    R_exits = np.linspace(0.92 * R_fan, case.R_int_max, n_D)
    L_room = case.L_max - bell_envelope(R_in, case.spessore_parete, case.raggio_bocca_su_D)[1] - layout.L_section - R_fan
    L_diffs = np.linspace(0.15, 0.6, n_L) * L_room
    rows: List[Dict] = []
    best = None
    prev_sol = None
    t0 = time.time()
    for L_diff in L_diffs:
        for R_exit in R_exits:
            row = dict(D_uscita_mm=2e3 * R_exit, L_diffusore_mm=1e3 * L_diff)
            d = case_shape(case, layout, R_fan, R_exit, L_diff, R_in)
            if d is None:
                rows.append(dict(row, stato="fuori ingombro"))
                continue
            g = MorphedGeometry(layout, d)
            # semiangolo_deg: diverging (diffuser) wall, the one read by export/duct.py;
            # semiangolo_conv_deg: converging (nozzle) wall
            row["semiangolo_deg"], row["semiangolo_conv_deg"] = half_angles_deg(g)
            if row["semiangolo_deg"] > max_half_angle + 1e-6:
                rows.append(dict(row, stato=f"semiangolo divergente {row['semiangolo_deg']:.1f} > "
                                            f"{max_half_angle:g} gradi (diffusore)"))
                continue
            if row["semiangolo_conv_deg"] > MAX_CONV_HALF_ANGLE + 1e-6:
                rows.append(dict(row, stato=f"semiangolo convergente {row['semiangolo_conv_deg']:.1f} > "
                                            f"{MAX_CONV_HALF_ANGLE:g} gradi (ugello)"))
                continue
            problem = DuctProblem(case, layout)
            if prev_sol is not None:
                problem.warm_start(prev_sol)
            try:
                if curve is not None:
                    problem, op = operating_point(problem, d, curve, dp0=None)
                    row.update(dp_Pa=op["dp_Pa"], Q_m3_s=op["Q_m3_s"], potenza_W=op["potenza_W"])
                sol = problem.solve(d)
                if not sol.converged:
                    raise RuntimeError("flusso non convergente")
            except (RuntimeError, ValueError) as exc:
                rows.append(dict(row, stato=f"scartato: {exc}"))
                continue
            prev_sol = sol
            r = report(problem, d)
            w = duct_fields(problem, d)["wall"]
            row.update(stato="ok", spinta_N=r["thrust"], dp_Pa=problem.case.dp_disk, Q_m3_s=r["Q"],
                       potenza_W=r["Q"] * problem.case.dp_disk, L_tubo_mm=1e3 * r["L_tube"],
                       tau_w_min_diffusore_Pa=float(np.min(w["tau_w"][w["z"] > g.z_b])),
                       celle_invertite=r["reversed_cells"])
            if row["tau_w_min_diffusore_Pa"] < 0.0:
                # parete del diffusore con flusso di ritorno: la spinta di una forma separata
                # non è affidabile (e il modello 2D non la segue bene), il caso non si sceglie
                row["stato"] = "separato (tau_w < 0 nel diffusore)"
            elif P_max is not None and row["potenza_W"] > P_max:
                row["stato"] = f"potenza > {P_max:g} W"
            rows.append(row)
            if verbose:
                print(f"  D_exit {row['D_uscita_mm']:5.1f} mm, L_diff {row['L_diffusore_mm']:5.1f} mm, "
                      f"{row['semiangolo_deg']:.2f} deg div / {row['semiangolo_conv_deg']:.2f} deg conv -> T {row['spinta_N']:.5f} N, dp {row['dp_Pa']:.2f} Pa, "
                      f"tau_w min {row['tau_w_min_diffusore_Pa']:+.4f} Pa [{time.time()-t0:.0f} s]"
                      + ("" if row["stato"] == "ok" else f"  -> {row['stato']}"), flush=True)
            if row["stato"] == "ok" and (best is None or row["spinta_N"] > best[0]["spinta_N"]):
                best = (row, problem, d)
    out = dict(griglia=f"{grid[0]}x{grid[1]}", D_ventola_mm=2e3 * R_fan,
               curva_ventola=curve.to_dict() if curve else None,
               criterio=("spinta al punto di lavoro sulla curva della ventola" if curve
                         else f"spinta a dp fisso = {case.dp_disk:.3f} Pa"),
               casi=rows, migliore=best[0] if best else None)
    if out_dir:
        with open(os.path.join(out_dir, "scansione.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
    if best is None:
        raise RuntimeError("no case of the scan converged within the limits without separation")
    out["problem"], out["design"] = best[1], best[2]
    return out


def plot_scan(scan: Dict, path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ok = [r for r in scan["casi"] if r.get("stato") == "ok" or "spinta_N" in r]
    Ls = sorted({round(r["L_diffusore_mm"], 3) for r in scan["casi"]})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
    for L in Ls:
        rr = sorted([r for r in ok if round(r["L_diffusore_mm"], 3) == L], key=lambda r: r["D_uscita_mm"])
        if rr:
            a1.plot([r["D_uscita_mm"] for r in rr], [r["spinta_N"] for r in rr], "o-", label=f"L diffusore {L:.0f} mm")
            a2.plot([r["D_uscita_mm"] for r in rr], [r["tau_w_min_diffusore_Pa"] for r in rr], "s--",
                    label=f"L diffusore {L:.0f} mm")
    b = scan.get("migliore")
    if b:
        a1.plot([b["D_uscita_mm"]], [b["spinta_N"]], "r*", ms=14, label="scelto")
    a2.axhline(0, color="r", lw=0.8)
    a1.set_xlabel("D uscita [mm]")
    a1.set_ylabel("spinta [N]")
    a1.set_title("Scansione: " + scan["criterio"])
    a2.set_xlabel("D uscita [mm]")
    a2.set_ylabel("τ_w minimo nel diffusore [Pa] (< 0 = separazione)")
    for a in (a1, a2):
        a.grid(True, ls=":", alpha=0.6)
        a.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path
