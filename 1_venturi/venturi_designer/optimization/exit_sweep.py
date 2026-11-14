"""
exit_sweep.py
=============
Sweep of the exit opening on the optimal duct, and the path of the optimiser.

Intake, fan and lengths stay those of the optimum; only the diffuser control points
move, scaled about the disk radius:

    R_down_k = R_disk + s (R_down_k_opt - R_disk)

s = 1 is the optimum, s = 0 a straight tube, s < 0 a converging exit (nozzle), s > 1 a
wider diffuser. Each s is solved again for the wanted thrust (secant on dp), so the rows
show how dp and the losses change from a converging to a diverging exit and why the
optimum stops where it does. Points beyond the angle limits or separated are solved
all the same. Nothing here raises: a failed point becomes a row with `stato` = reason.

`optimisation_history` only re-orders data already on disk (scan choice, SLSQP
iterations, secant steps on dp) into one series from the start to the final choice.
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
from dataclasses import replace
from typing import Dict, List, Optional

import numpy as np

from .alternatives import FAILURES, ROW_KEYS, compare_row, failed_row
from .scan import MAX_CONV_HALF_ANGLE, half_angles_deg
from .shape_opt import DuctProblem, for_grid, report
from .target_thrust import match_thrust
from ..export.cad import bell_envelope
from ..geometry.morph import MorphedGeometry, MorphLayout

MIN_OPENING = 5e-4          # [m] below this the optimum diffuser is taken as degenerate
DEGENERATE_OPENING = 5e-4   # [m] opening of the reference shape used in that case (s = 1)
FAN_SHARE_MIN = 0.85        # smallest exit diameter, share of the fan diameter
STRAIGHT_TOL_MM = 0.1       # exit within this of the fan diameter counts as "dritto"
ANGLE_TOL_DEG = 0.05
THRUST_OK = 0.01            # relative thrust error above which the point is flagged

SWEEP_KEYS = ROW_KEYS + ("s", "tipo", "semiangolo_convergente_deg", "V_uscita_m_s",
                         "entro_limite_angolo", "separato")


def _opening(d_opt: np.ndarray) -> float:
    """R_exit_opt - R_disk [m]: the exit radius is the last free diffuser point, d[-4]."""
    return float(d_opt[-4] - d_opt[-3])


def _reference_opening(d_opt: np.ndarray) -> float:
    """Opening that s = 1 stands for: the optimum one, or DEGENERATE_OPENING when the
    optimum diffuser is (nearly) straight."""
    op = _opening(d_opt)
    return op if op >= MIN_OPENING else DEGENERATE_OPENING


def exit_family(layout: MorphLayout, d_opt: np.ndarray, s: float) -> np.ndarray:
    """Design of the family at the scale s; d_opt itself for s = 1.

    Only the n_down free diffuser control points change (the last one is the exit
    radius). Degenerate optimum (R_exit - R_disk < 0.5 mm, so a straight tube whose
    shape cannot be scaled): the diffuser becomes a normalised half cosine of opening
    s * DEGENERATE_OPENING, i.e. the exit radius stays linear in s. There s = 1 gives an
    opening of 0.5 mm, close to but not exactly the optimum.
    """
    d = np.array(d_opt, dtype=float)
    n_up, n_down = layout.n_up, layout.n_down
    R_disk = float(d[-3])
    down = d[n_up:n_up + n_down]
    if _opening(d_opt) >= MIN_OPENING:
        if s == 1.0:
            return d
        d[n_up:n_up + n_down] = R_disk + s * (down - R_disk)
    else:
        k = np.arange(1, n_down + 1)
        shape = 0.5 * (1.0 - np.cos(np.pi * k / n_down))          # 0..1, last point = 1
        d[n_up:n_up + n_down] = R_disk + s * DEGENERATE_OPENING * shape
    return d


def s_range(case, d_opt: np.ndarray, n: int) -> List[float]:
    """n equally spaced values of s between the smallest exit (D = 0.85 D_fan) and the
    largest (D = 2 R_int_max), plus s = 1 if missing, sorted.
    """
    R_disk = float(d_opt[-3])
    A = _reference_opening(d_opt)
    s_lo = (FAN_SHARE_MIN * R_disk - R_disk) / A
    s_hi = (case.R_int_max - R_disk) / A
    vals = [1.0] if n <= 1 else [float(v) for v in np.linspace(s_lo, s_hi, int(n))]
    vals = [1.0 if abs(v - 1.0) < 1e-6 else v for v in vals]   # an end at the optimum is the optimum
    if not any(v == 1.0 for v in vals):
        vals.append(1.0)
    return sorted(vals)


def sweep_id(s: float) -> str:
    return f"s{s:+.2f}"


def _kind(D_exit_mm: float, D_fan_mm: float) -> str:
    if D_exit_mm < D_fan_mm - STRAIGHT_TOL_MM:
        return "convergente"
    if D_exit_mm <= D_fan_mm + STRAIGHT_TOL_MM:
        return "dritto"
    return "divergente"


def _failed(s: float, motivo: str) -> Dict:
    row = failed_row(sweep_id(s), None, motivo)
    row.update({k: None for k in SWEEP_KEYS if k not in row})
    row["s"] = float(s)
    return row


def _solve_point(case_g, layout, d, T, prev_sol, exponent, verbose):
    """match_thrust from a warm start; once more from cold if that fails."""
    last = None
    for warm in (prev_sol, None) if prev_sol is not None else (None,):
        problem = DuctProblem(case_g, layout)
        if warm is not None:
            problem.warm_start(warm)
        try:
            return match_thrust(problem, d, T, exponent, cycle=0, verbose=verbose)
        except FAILURES as exc:
            last = exc
    raise last


def sweep_point(s, case_g, layout, d_opt, T, ref, max_half_angle, prev_sol, verbose):
    """Row of the point s and the flow to start the next one from (never raises)."""
    try:
        d = d_opt if abs(s - 1.0) < 1e-9 else exit_family(layout, d_opt, s)
        problem, _, _ = _solve_point(case_g, layout, d, T, prev_sol, 1.0, verbose)
        row = compare_row(problem, d, T, ref)
        g = problem.geometry(d)
        div, conv = half_angles_deg(g)
        err = problem.values(d)["thrust"] / T - 1.0
        row.update(
            id=sweep_id(s), s=float(s),
            tipo=_kind(row["D_uscita_mm"], row["D_ventola_mm"]),
            semiangolo_convergente_deg=float(conv),
            V_uscita_m_s=float(report(problem, d)["V_exit"]),
            entro_limite_angolo=bool(div <= max_half_angle + ANGLE_TOL_DEG
                                     and conv <= MAX_CONV_HALF_ANGLE),
            separato=bool(row["tau_w_min_diffusore_Pa"] < 0.0))
        row["convergito"] = bool(abs(err) <= THRUST_OK)
        row["stato"] = "ok" if row["convergito"] else \
            f"spinta {100 * err:+.2f} % dal valore richiesto"
        return row, (problem.sol or prev_sol)
    except Exception as exc:               # never raise out of here
        if verbose:
            print(f"  failed: {exc}", flush=True)
        return _failed(s, f"errore: {exc}"), prev_sol


def sweep_worker(payload) -> Dict:
    """Process pool job: one point of the sweep from a cold start (quiet)."""
    s, case_g, layout, d_opt, T, ref, max_half_angle = payload
    return sweep_point(s, case_g, layout, d_opt, T, ref, max_half_angle, None, False)[0]


def run_exit_sweep(case, layout: MorphLayout, d_opt: np.ndarray, ref_problem: DuctProblem,
                   n: int, grid, out_dir: str, max_half_angle: float,
                   verbose: bool = True, procs: int = 1) -> Dict:
    """Rows of the sweep over s (see the module docstring); writes <out_dir>/uscita.json.

    procs = 1: one process, outwards from the optimum, each point warm from the nearest solved
    flow. procs > 1: the points are solved in `procs` processes, each one from a cold start.
    """
    os.makedirs(out_dir, exist_ok=True)
    T = float(case.T_target)
    try:
        ref = compare_row(ref_problem, d_opt, T)
        ref["id"] = sweep_id(1.0)
    except Exception as exc:
        ref = None
        ref_error = f"riferimento non valutabile: {exc}"
    values = s_range(case, d_opt, n)
    rows: Dict[float, Dict] = {}
    if ref is None:
        rows = {s: _failed(s, ref_error) for s in values}
    elif procs > 1 and len(values) > 1:
        from ..parallel import map_ordered
        case_g = for_grid(replace(case, dp_disk=ref_problem.case.dp_disk), *grid)
        if verbose:
            print(f"  {len(values)} points in {min(procs, len(values))} processes, each from a "
                  "cold start", flush=True)

        def done(i, row):
            print(f"  Exit sweep s = {values[i]:+.3f}: {row['stato']}", flush=True)

        solved = map_ordered(sweep_worker,
                             [(s, case_g, layout, d_opt, T, ref, max_half_angle) for s in values],
                             procs, on_done=done if verbose else None)
        rows = dict(zip(values, solved))
    else:
        case_g = for_grid(replace(case, dp_disk=ref_problem.case.dp_disk), *grid)
        start_sol = ref_problem.sol
        # outwards from the optimum, both ways, so each warm start is the nearest solved flow
        chains = [[s for s in values if s >= 1.0 - 1e-9],
                  [s for s in reversed(values) if s < 1.0 - 1e-9]]
        for chain in chains:
            prev_sol = start_sol
            for s in chain:
                if verbose:
                    print(f"\nExit sweep s = {s:+.3f}", flush=True)
                rows[s], prev_sol = sweep_point(s, case_g, layout, d_opt, T, ref, max_half_angle,
                                                prev_sol, verbose)
    out = dict(griglia=f"{grid[0]}x{grid[1]}", T_target_N=T,
               limite_semiangolo_deg=float(max_half_angle),
               limite_convergente_deg=float(MAX_CONV_HALF_ANGLE), riferimento=sweep_id(1.0),
               punti=[rows[s] for s in sorted(rows)])
    with open(os.path.join(out_dir, "uscita.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out


def exit_sweep_table(sweep: Dict) -> str:
    """Compact text table of the sweep, ordered by s."""
    f = lambda v, fmt: "-" if v is None else format(v, fmt)
    lines = [f"{'s':>7} {'D exit':>8} {'type':>11} {'angle':>6} {'dp':>9} {'dp %':>7} "
             f"{'loss':>9} {'tau_w min':>10} {'state'}",
             f"{'':>7} {'[mm]':>8} {'':>11} {'[deg]':>6} {'[Pa]':>9} {'':>7} {'[Pa]':>9} "
             f"{'[Pa]':>10}"]
    for r in sweep["punti"]:
        mark = "*" if r["id"] == sweep["riferimento"] else " "
        ang = r["semiangolo_diffusore_deg"] if r["tipo"] != "convergente" else \
            r["semiangolo_convergente_deg"]
        flags = ("" if r["entro_limite_angolo"] in (None, True) else " [oltre angolo]") + \
            (" [separato]" if r["separato"] else "")
        lines.append(f"{r['s']:+7.2f} {f(r['D_uscita_mm'], '8.1f')} {f(r['tipo'], '>11')} "
                     f"{f(ang, '6.2f')} {f(r['dp_Pa'], '9.3f')} {f(r['delta_dp_pct'], '+7.2f')} "
                     f"{f(r['perdita_totale_Pa'], '9.3f')} "
                     f"{f(r['tau_w_min_diffusore_Pa'], '10.4f')} {mark}{r['stato']}{flags}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path of the optimiser
# ---------------------------------------------------------------------------
_HISTORY_RE = re.compile(r"history_c(\d+)_(\d+)x(\d+)\.json$")
SECANT_KINDS = ("secante", "secante_migliore", "finale")
STEP_KEYS = ("n", "fase", "ciclo", "griglia", "iterazione", "D_uscita_mm", "D_ventola_mm",
             "L_condotto_mm", "spinta_N", "dp_Pa", "violazione")


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def optimisation_history(convergenza_dir: str, scan: Optional[Dict], case=None) -> Dict:
    """One series from the starting point to the choice; writes
    <convergenza_dir>/storico_ottimizzazione.json.

    Phases: "scansione" (the case chosen by the scan, if any), "ottimizzazione" (SLSQP
    iterations of history_c{cycle}_{Nz}x{Nr}.json, per cycle and grid) and "secante"
    (steps on dp of iterazioni_dp.json: the shape does not change, so the geometry of
    the step before is carried on). dp of an SLSQP iteration is the fixed dp of that
    cycle (from the 'ottimizzazione' step of iterazioni_dp.json, None if missing).
    L_condotto_mm is the tube length when `case` is given (bell mouth included), else
    the length of the two splines and the disk section only (SLSQP) / the scan value.
    """
    steps_in = _load(os.path.join(convergenza_dir, "iterazioni_dp.json")) or []
    out: List[Dict] = []

    def add(fase, ciclo, griglia, it, **kw):
        row = {k: None for k in STEP_KEYS}
        row.update(n=len(out) + 1, fase=fase, ciclo=ciclo, griglia=griglia, iterazione=it, **kw)
        out.append(row)

    best = (scan or {}).get("migliore")
    if best:
        add("scansione", 0, (scan or {}).get("griglia"), 0, D_uscita_mm=best.get("D_uscita_mm"),
            D_ventola_mm=(scan or {}).get("D_ventola_mm"), L_condotto_mm=best.get("L_tubo_mm"),
            spinta_N=best.get("spinta_N"), dp_Pa=best.get("dp_Pa"))

    dp_of = {(r.get("ciclo"), r.get("griglia")): r.get("dp_disk")
             for r in steps_in if r.get("tipo") == "ottimizzazione"}
    files = {}
    for f in glob.glob(os.path.join(convergenza_dir, "history_c*_*x*.json")):
        m = _HISTORY_RE.search(os.path.basename(f))
        if m:
            files[(int(m.group(1)), int(m.group(2)), int(m.group(3)))] = f
    secant: Dict[int, List[dict]] = {}
    for r in steps_in:
        if r.get("tipo") in SECANT_KINDS:
            secant.setdefault(int(r.get("ciclo") or 0), []).append(r)
    cycles = sorted({c for c, _, _ in files} | {c for c in secant if c > 0})

    def bell(D_inlet):
        if case is None or D_inlet is None:
            return 0.0
        return 1e3 * bell_envelope(0.5 * D_inlet, case.spessore_parete,
                                   case.raggio_bocca_su_D)[1]

    def secant_steps(c):
        for i, r in enumerate(secant.get(c, []), 1):
            last = out[-1] if out else {k: None for k in STEP_KEYS}
            add("secante", c, r.get("griglia"), i, D_uscita_mm=last["D_uscita_mm"],
                D_ventola_mm=last["D_ventola_mm"], L_condotto_mm=last["L_condotto_mm"],
                spinta_N=r.get("spinta"), dp_Pa=r.get("dp_disk"))

    for c in cycles:
        for key in sorted(k for k in files if k[0] == c):
            data = _load(files[key])
            grid = f"{key[1]}x{key[2]}"
            for h in (data or {}).get("history", []):
                to_mm = lambda v: None if v is None else 1e3 * v
                add("ottimizzazione", c, grid, h.get("iteration"),
                    D_uscita_mm=to_mm(h.get("D_exit")), D_ventola_mm=to_mm(h.get("D_disk")),
                    L_condotto_mm=(None if h.get("L_total") is None
                                   else 1e3 * h["L_total"] + bell(h.get("D_inlet"))),
                    spinta_N=h.get("thrust"), dp_Pa=dp_of.get((c, grid)),
                    violazione=h.get("violation"))
        secant_steps(c)
    secant_steps(0)
    res = dict(passi=out, scelta=out[-1] if out else None)
    with open(os.path.join(convergenza_dir, "storico_ottimizzazione.json"), "w",
              encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    return res
