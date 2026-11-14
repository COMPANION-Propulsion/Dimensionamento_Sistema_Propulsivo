"""
alternatives.py
===============
Alternatives of the optimal duct at fixed tube lengths.

The free optimum (size_for_thrust, length free in [L_min, L_max]) is the reference.
For every wanted length L_k the same problem is solved again with the length held
at L_k +/- 0.5 mm, starting from the optimum with L_up, L_down rescaled (or, if that
fails, from the scan shape at that length). Each alternative gives one row of the
comparison table: geometry, dp for the wanted thrust, power, total-pressure losses.
Nothing here raises: a failed alternative becomes a row with `stato` = the reason.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import replace
from typing import Dict, List, Optional, Sequence

import numpy as np

from .scan import case_shape, half_angles_deg
from .shape_opt import L_WINDOW, DuctProblem, inlet_radius_limit, report
from .target_thrust import save_design, size_for_thrust
from ..export.cad import bell_envelope
from ..export.duct import total_pressure_losses
from ..export.fields import duct_fields
from ..geometry.morph import MorphedGeometry, MorphLayout

N_PROFILE = 200
L_CHECK_MM = 1.0           # a result farther than this from the wanted length is flagged
BELL_FRACTION = 0.9        # fallback start: share of the largest diffuser opening used

ROW_KEYS = ("id", "L_tubo_mm", "D_ingresso_mm", "D_ventola_mm", "z_ventola_mm", "D_uscita_mm",
            "rapporto_aree", "semiangolo_imbocco_deg", "semiangolo_diffusore_deg", "dp_Pa",
            "delta_dp_Pa", "delta_dp_pct", "potenza_W", "delta_potenza_pct", "spinta_N",
            "spinta_su_potenza_N_W", "Q_m3_s", "perdita_imbocco_Pa", "perdita_disco_Pa",
            "perdita_valle_Pa", "perdita_totale_Pa", "perdita_totale_pct", "potenza_persa_W",
            "p0_uscita_Pa", "tau_w_min_diffusore_Pa", "area_parete_cm2", "convergito", "stato",
            "design_json", "profilo_csv", "profilo_z_mm", "profilo_R_mm")

FAILURES = (RuntimeError, ValueError, FloatingPointError, np.linalg.LinAlgError)


def alt_id(L: float) -> str:
    return f"L{round(L * 1e3)}"


def failed_row(id: str, L: Optional[float], motivo: str) -> Dict:
    """Row of a failed alternative: every key of the contract, None but the few known."""
    row = {k: None for k in ROW_KEYS}
    row.update(id=id, L_tubo_mm=None if L is None else 1e3 * float(L), convergito=False,
               stato=motivo)
    return row


def _tube_length(layout: MorphLayout, case, d: np.ndarray) -> float:
    g = MorphedGeometry(layout, d)
    return g.L_total + bell_envelope(g.R_inlet, case.spessore_parete, case.raggio_bocca_su_D)[1]


def rescale_length(layout: MorphLayout, case, d: np.ndarray, L_tube: float) -> np.ndarray:
    """Copy of d with L_up and L_down scaled by the same factor so the tube is L_tube long.

    Tube length = L_up + L_section + L_down + bell mouth; the bell length depends on
    the inlet radius only, and the radii stay as they are.
    """
    d = np.array(d, dtype=float)
    g = MorphedGeometry(layout, d)
    l_env = bell_envelope(g.R_inlet, case.spessore_parete, case.raggio_bocca_su_D)[1]
    room = L_tube - l_env - layout.L_section          # what L_up + L_down must add up to
    if room <= 0.0:
        raise ValueError(f"L_tube {1e3 * L_tube:.1f} mm is too short for the bell mouth and the "
                         f"disk section.")
    f = room / (g.L_up + g.L_down)
    d[-2] *= f
    d[-1] *= f
    return d


def _profile(g: MorphedGeometry):
    z, R = g.profile_points(N_PROFILE)
    return 1e3 * z, 1e3 * R


def _wall_area_cm2(g: MorphedGeometry) -> float:
    z = np.linspace(0.0, g.L_total, 4000)
    R, s = g.radius(z), g.radius_derivative(z)
    return float(1e4 * np.trapezoid(2.0 * math.pi * R * np.sqrt(1.0 + s ** 2), z))


def compare_row(problem: DuctProblem, d: np.ndarray, T_target: float,
                ref: Optional[Dict] = None) -> Dict:
    """Comparison row (contract keys) of the shape d solved on `problem`.

    `ref` is the row of the optimum: with it the deltas are computed, without it they are 0.
    The files keys (design_json, profilo_csv) are left None here.
    """
    r = report(problem, d)
    F = duct_fields(problem, d)
    loss = total_pressure_losses(problem.case, F, r["Q"])
    g = problem.geometry(d)
    z_in = np.linspace(0.0, g.z_a, 400)
    w = F["wall"]
    pz, pR = _profile(g)
    dp, P = float(r["dp_disk"]), float(r["power"])
    row = dict(
        id="ottimo", L_tubo_mm=1e3 * r["L_tube"], D_ingresso_mm=1e3 * r["D_inlet"],
        D_ventola_mm=1e3 * r["D_disk"], z_ventola_mm=1e3 * r["z_disk"],
        D_uscita_mm=1e3 * r["D_exit"], rapporto_aree=float(r["area_ratio"]),
        semiangolo_imbocco_deg=float(np.degrees(np.arctan(np.max(np.abs(
            g.radius_derivative(z_in)))))),
        semiangolo_diffusore_deg=half_angles_deg(g)[0],
        dp_Pa=dp, delta_dp_Pa=0.0, delta_dp_pct=0.0, potenza_W=P, delta_potenza_pct=0.0,
        spinta_N=float(r["thrust"]), spinta_su_potenza_N_W=float(r["thrust_per_power"]),
        Q_m3_s=float(r["Q"]), perdita_imbocco_Pa=float(loss["imbocco_Pa"]),
        perdita_disco_Pa=float(loss["disco_Pa"]), perdita_valle_Pa=float(loss["valle_Pa"]),
        perdita_totale_Pa=float(loss["totale_Pa"]),
        perdita_totale_pct=100.0 * float(loss["totale_Pa"]) / dp,
        potenza_persa_W=float(loss["potenza_persa_W"]), p0_uscita_Pa=float(loss["p0_uscita_Pa"]),
        tau_w_min_diffusore_Pa=float(np.min(w["tau_w"][w["z"] > g.z_b])),
        area_parete_cm2=_wall_area_cm2(g), convergito=True, stato="ok",
        design_json=None, profilo_csv=None, profilo_z_mm=pz.tolist(), profilo_R_mm=pR.tolist())
    row = {k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in row.items()}
    if ref is not None:
        row["delta_dp_Pa"] = dp - ref["dp_Pa"]
        row["delta_dp_pct"] = 100.0 * (dp / ref["dp_Pa"] - 1.0)
        row["delta_potenza_pct"] = 100.0 * (P / ref["potenza_W"] - 1.0)
    return row


def _save_files(folder: str, root: str, problem: DuctProblem, layout: MorphLayout,
                d: np.ndarray, row: Dict) -> None:
    """design.json and profilo.csv of one case; the row gets the relative paths."""
    os.makedirs(folder, exist_ok=True)
    save_design(os.path.join(folder, "design.json"), problem.case, layout, d,
                report(problem, d))
    z, R = _profile(problem.geometry(d))
    np.savetxt(os.path.join(folder, "profilo.csv"), np.column_stack((z, R)), delimiter=",",
               header="z_mm,R_mm", comments="", fmt="%.6f")
    sub = os.path.relpath(folder, root).replace(os.sep, "/")
    row["design_json"], row["profilo_csv"] = f"{sub}/design.json", f"{sub}/profilo.csv"


def _fallback_start(case_k, layout: MorphLayout, d_opt: np.ndarray, L: float):
    """Scan-like shape at the length L: minimum intake, diffuser at 0.9 of the largest angle."""
    R_fan = float(d_opt[-3])
    R_in = min(inlet_radius_limit(case_k), case_k.R_int_max)
    l_env = bell_envelope(R_in, case_k.spessore_parete, case_k.raggio_bocca_su_D)[1]
    L_diff = L - l_env - layout.L_section - R_fan
    if L_diff <= 0.0:
        return None
    R_exit = min(case_k.R_int_max, R_fan + (2.0 / math.pi)
                 * math.tan(math.radians(case_k.semiangolo_max_deg)) * L_diff * BELL_FRACTION)
    return case_shape(replace(case_k, L_min=None), layout, R_fan, R_exit, L_diff, R_in)


def _solve_one(case, layout, d_opt, L, grid, max_cycles, max_iter, tol_dp, folder, verbose):
    """Result (SizingResult or None) and the reason of the last failure."""
    case_k = replace(case, L_target=L)
    starts = [("optimum rescaled", lambda: rescale_length(layout, case_k, d_opt, L)),
              ("scan shape", lambda: _fallback_start(case_k, layout, d_opt, L))]
    first, reason = None, "nessuna partenza valida"
    for name, make in starts:
        try:
            d0 = make()
            if d0 is None:
                reason = f"partenza '{name}' fuori ingombro"
                continue
            res = size_for_thrust(case_k, layout, d0, [grid], max_iter=max_iter, tol_dp=tol_dp,
                                  max_cycles=max_cycles, out_dir=folder, verbose=verbose)
        except FAILURES as exc:
            reason = f"partenza '{name}': {exc}"
            if verbose:
                print(f"  {name}: failed ({exc})", flush=True)
            continue
        if res.converged:
            return res, "ok"
        reason = f"partenza '{name}': ciclo su dp non convergito"
        first = first or res
        if verbose:
            print(f"  {name}: dp loop not converged", flush=True)
    return first, reason


def alternative_row(case, layout, d_opt, L, grid, max_cycles, max_iter, tol_dp, out_dir, ref,
                    verbose=True) -> Dict:
    """Row of the alternative at the tube length L (never raises: a failure is a row)."""
    T = float(case.T_target)
    id = alt_id(L)
    folder = os.path.join(out_dir, id)
    try:
        if ref["dp_Pa"] is None:
            raise ValueError("no reference row")
        if L > case.L_max + 1e-9:
            return failed_row(id, L, "fuori ingombro (L > L_max)")
        os.makedirs(folder, exist_ok=True)
        res, reason = _solve_one(case, layout, d_opt, L, grid, max_cycles, max_iter,
                                 tol_dp, folder, verbose)
        if res is None:
            return failed_row(id, L, reason)
        row = compare_row(res.problem, res.design, T, ref)
        row["id"] = id
        row["convergito"] = bool(res.converged)
        row["stato"] = "ok" if res.converged else reason
        dev = abs(row["L_tubo_mm"] - 1e3 * L)
        if dev > L_CHECK_MM:
            row["convergito"] = False
            row["stato"] = f"lunghezza {row['L_tubo_mm']:.1f} mm lontana da quella richiesta"
        _save_files(folder, out_dir, res.problem, layout, res.design, row)
        return row
    except Exception as exc:                   # never raise out of here
        return failed_row(id, L, f"errore: {exc}")


def alternative_worker(payload) -> Dict:
    """Process pool job: one alternative (quiet; the parent prints one line per row)."""
    case, layout, d_opt, L, grid, max_cycles, max_iter, tol_dp, out_dir, ref = payload
    return alternative_row(case, layout, d_opt, L, grid, max_cycles, max_iter, tol_dp, out_dir,
                           ref, verbose=False)


def run_alternatives(case, layout: MorphLayout, d_opt: np.ndarray, ref_problem: DuctProblem,
                     lengths: Sequence[float], grid, max_cycles: int = 2, max_iter: int = 40,
                     tol_dp: float = 0.01, out_dir: str = ".", verbose: bool = True,
                     procs: int = 1) -> Dict:
    """Optimum at fixed lengths and the table that compares them with the free optimum.

    Writes <out_dir>/alternative.json and one folder per case (design.json, profilo.csv).
    procs > 1: the lengths are solved in `procs` processes (each one was already independent).
    """
    os.makedirs(out_dir, exist_ok=True)
    T = float(case.T_target)
    try:
        ref = compare_row(ref_problem, d_opt, T)
        _save_files(os.path.join(out_dir, "ottimo"), out_dir, ref_problem, layout, d_opt, ref)
    except Exception as exc:                       # the table must come out anyway
        ref = failed_row("ottimo", None, f"riferimento non valutabile: {exc}")
        ref["dp_Pa"] = ref["potenza_W"] = None
    rows = [ref]
    lengths = [float(L) for L in lengths]
    if procs > 1 and len(lengths) > 1:
        from ..parallel import map_ordered
        if verbose:
            print(f"  {len(lengths)} alternatives in {min(procs, len(lengths))} processes",
                  flush=True)

        def done(i, row):
            print(f"  Alternative {row['id']}: {row['stato']}", flush=True)

        rows += map_ordered(alternative_worker,
                            [(case, layout, d_opt, L, grid, max_cycles, max_iter, tol_dp,
                              out_dir, ref) for L in lengths],
                            procs, on_done=done if verbose else None)
    else:
        for L in lengths:
            if verbose:
                print(f"\nAlternative {alt_id(L)}: tube {1e3 * L:.1f} mm", flush=True)
            rows.append(alternative_row(case, layout, d_opt, L, grid, max_cycles, max_iter,
                                        tol_dp, out_dir, ref, verbose))
    out = dict(griglia=f"{grid[0]}x{grid[1]}", T_target_N=T, riferimento="ottimo", casi=rows)
    with open(os.path.join(out_dir, "alternative.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out


def lengths_from_input(value, case) -> List[float]:
    """Tube lengths [m] of the input: n equally spaced between L_min and L_max, an explicit
    list, or nothing (None, 0)."""
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (list, tuple, np.ndarray)):
        return [float(v) for v in value]
    if isinstance(value, float) and not float(value).is_integer():
        return [float(value)]                       # a single length in m
    n = int(value)
    if n <= 0:
        return []
    L_lo = case.L_min if case.L_min is not None else 0.6 * case.L_max
    if n == 1:
        return [float(case.L_max)]
    return [float(v) for v in np.linspace(L_lo, case.L_max, n)]


def alternatives_table(alt: Dict) -> str:
    """Compact text table of the comparison, sorted by tube length."""
    head = (f"{'L tube':>8} {'D fan':>8} {'D exit':>8} {'dp':>9} {'dp %':>7} "
            f"{'loss':>9} {'state'}")
    lines = [head, f"{'[mm]':>8} {'[mm]':>8} {'[mm]':>8} {'[Pa]':>9} {'':>7} {'[Pa]':>9}"]
    f = lambda v, fmt: "-" if v is None else format(v, fmt)
    for r in sorted(alt["casi"], key=lambda r: (r["L_tubo_mm"] is None, r["L_tubo_mm"] or 0.0)):
        mark = "*" if r["id"] == alt["riferimento"] else " "
        lines.append(f"{f(r['L_tubo_mm'], '8.1f')} {f(r['D_ventola_mm'], '8.1f')} "
                     f"{f(r['D_uscita_mm'], '8.1f')} {f(r['dp_Pa'], '9.3f')} "
                     f"{f(r['delta_dp_pct'], '+7.2f')} {f(r['perdita_totale_Pa'], '9.3f')} "
                     f"{mark}{r['stato']}")
    return "\n".join(lines)
