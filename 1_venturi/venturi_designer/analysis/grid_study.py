"""
grid_study.py
=============
Grid refinement study: how much does the answer still change with the grid?

The same case is solved on several grids, each finer than the last by a
roughly constant factor, with the SAME shape of spacing (same wall
clustering, same throat refinement, same ramp width). Then:

    observed order p   how fast the result changes as cells shrink
    extrapolated value what the result would be with infinitely small cells
    GCI                an error band on the finest-grid result

The formulas follow Celik et al., "Procedure for estimation and reporting of
uncertainty due to discretization in CFD applications", J. Fluids Eng. 130
(2008) 078001. Index 1 is the finest grid, 3 the coarsest of a triplet.

    h_i   = N_i^(-1/2)                      (representative cell size, 2D)
    r21   = h2 / h1,   r32 = h3 / h2
    e21   = phi2 - phi1,   e32 = phi3 - phi2,   s = sign(e32 / e21)
    p     = | ln|e32 / e21| + q(p) | / ln r21
    q(p)  = ln( (r21^p - s) / (r32^p - s) )      (solved by fixed point)
    phi_ext = (r21^p phi1 - phi2) / (r21^p - 1)
    GCI21 = 1.25 * |(phi1 - phi2) / phi1| / (r21^p - 1)

s < 0 means the result goes up and down as the grid is refined
(oscillatory convergence): p and the GCI are then not meaningful and are
reported as such.

Usage
-----
    python -m venturi_designer.analysis.grid_study                         # default case
    python -m venturi_designer.analysis.grid_study --beta 0.6 --jobs 2     # any run_venturi.py option
    python -m venturi_designer.analysis.grid_study --levels 90x36,128x51,180x72
    python -m venturi_designer.analysis.grid_study --duct <...>/2_venturi/05_convergenza/design.json

With --duct the study runs on an optimised duct and the result under test is
the thrust instead of C_d. The conditions, dp included, come from design.json.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_LEVELS = "64x26,90x36,128x51"
P_RANGE = (0.5, 3.0)      # plausible observed order of a second-order scheme
ASYMPTOTIC_TOL = 0.15     # allowed distance of the asymptotic ratio from 1
FLAT_TOL = 1e-3           # results closer than this (relative) are grid independent
DEFAULT_TOL = 1e-4   # tighter than a normal run, so the iteration error is
                     # small next to the grid error being measured


# ---------------------------------------------------------------------------
# Richardson / GCI
# ---------------------------------------------------------------------------
@dataclass
class GCIResult:
    p: float                 # observed order
    phi_ext: float           # extrapolated value
    e_a21: float             # relative change finest -> middle grid
    e_ext21: float           # relative distance finest -> extrapolated
    gci21: float             # error band on the finest result (relative)
    oscillatory: bool        # s < 0: result goes up and down


def gci(h: Sequence[float], phi: Sequence[float], safety: float = 1.25,
        max_iter: int = 200) -> GCIResult:
    """Richardson extrapolation and GCI for three grids.

    Args:
        h:   cell sizes (h1 < h2 < h3), finest first.
        phi: results on those grids, finest first.
    """
    h1, h2, h3 = h
    f1, f2, f3 = phi
    if not (h1 < h2 < h3):
        raise ValueError("cell sizes must be given finest first, strictly increasing")
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0.0 or e32 == 0.0:
        # no change between two grids: already grid independent to round-off
        return GCIResult(p=float("inf"), phi_ext=f1, e_a21=abs(e21 / f1),
                         e_ext21=0.0, gci21=0.0, oscillatory=False)
    s = math.copysign(1.0, e32 / e21)
    p = abs(math.log(abs(e32 / e21))) / math.log(r21)     # first guess (q = 0)
    for _ in range(max_iter):
        num = r21 ** p - s
        den = r32 ** p - s
        q = math.log(num / den) if num > 0.0 and den > 0.0 else 0.0
        p_new = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-12:
            p = p_new
            break
        p = p_new
    rp = r21 ** p
    phi_ext = (rp * f1 - f2) / (rp - 1.0)
    e_a21 = abs((f1 - f2) / f1)
    e_ext21 = abs((phi_ext - f1) / phi_ext)
    return GCIResult(p=p, phi_ext=phi_ext, e_a21=e_a21, e_ext21=e_ext21,
                     gci21=safety * e_a21 / (rp - 1.0), oscillatory=s < 0.0)


# ---------------------------------------------------------------------------
# Running the grids
# ---------------------------------------------------------------------------
def parse_levels(text: str) -> List[Tuple[int, int]]:
    """'64x26,90x36' -> [(64, 26), (90, 36)], coarsest first."""
    levels = []
    for item in text.split(","):
        nz, nr = item.lower().split("x")
        levels.append((int(nz), int(nr)))
    levels.sort(key=lambda t: t[0] * t[1])
    return levels


def run_level(args_dict: Dict, Nz: int, Nr: int, ramp: float) -> Dict:
    """Solve one grid level and return the numbers of interest."""
    from ..cli import config_from_args
    from ..solver.fvmesh import build_fvmesh
    from ..geometry import create_venturi_geometry
    from ..solver import solve_fv
    from .validation import validate

    args = argparse.Namespace(**args_dict)
    args.Nz, args.Nr = Nz, Nr
    config = config_from_args(args)
    geom = create_venturi_geometry(config)
    mesh = build_fvmesh(geom, Nz, Nr, config.wall_clustering,
                        config.throat_refine, throat_ramp=ramp)
    t0 = time.time()
    res = solve_fv(mesh, config, verbose=False)
    rep = validate(res, mesh, geom, config)
    return dict(Nz=Nz, Nr=Nr, cells=Nz * Nr, iters=res.n_iter,
                converged=bool(res.converged), residual=float(res.final_residual),
                time_s=time.time() - t0, Cd=rep.Cd, dp=rep.dp_measured,
                recovery=rep.pressure_recovery, y_plus=float(res.y_plus_max))


def build_parser() -> argparse.ArgumentParser:
    from ..cli import build_parser as case_parser
    p = case_parser()
    p.prog = "python -m venturi_designer.analysis.grid_study"
    p.description = ("Solve one case on several grids and estimate how far the "
                     "finest result still is from the grid-independent value.")
    p.add_argument("--levels", default=DEFAULT_LEVELS,
                   help=f"grids as NzxNr, comma separated (default {DEFAULT_LEVELS}).")
    p.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1),
                   help="grids solved at the same time (default: up to 4).")
    p.add_argument("--duct", default=None,
                   help="design.json of an optimised duct: study its thrust instead of C_d.")
    p.set_defaults(tol=DEFAULT_TOL, max_iter=400_000)
    return p


def _fmt_gci(name: str, g: GCIResult, notes: str) -> str:
    if g.oscillatory:
        return f"| {name} | oscillatory (goes up and down) | - | - | {notes} |"
    return f"| {name} | {g.p:.2f} | {g.phi_ext:.5f} | {100 * g.gci21:.3f} % | {notes} |"


def _notes(triplet: List[Dict]) -> str:
    """What makes a triplet's estimate less reliable."""
    out = []
    for r in triplet:
        if not r["converged"]:
            out.append(f"{r['Nz']}x{r['Nr']} not converged")
        if not r.get("settled", True):
            out.append(f"{r['Nz']}x{r['Nr']} thrust still moving with nu_t")
        if r["y_plus"] >= 5.0:
            out.append(f"{r['Nz']}x{r['Nr']} y+ = {r['y_plus']:.1f} (> 5)")
    return "; ".join(out) if out else "ok"


def error_estimate(h: Sequence[float], phi: Sequence[float], safety: float = 1.25) -> Dict:
    """Value of the finest of three grids, with its grid error [same units].

    h and phi are finest first. Normally the error is the GCI. If the result
    goes up and down, the GCI means nothing, and the band falls back on the
    spread of the three results. The asymptotic ratio should be close to 1:
    far from it, the grids are not yet fine enough for Richardson to hold.
    """
    g = gci(h, phi, safety)
    f1, f2, f3 = phi
    problems: List[str] = []
    spread = max(phi) - min(phi)
    if spread <= FLAT_TOL * abs(f1):
        # the differences are at the level of the iteration error: the order
        # means nothing, and the spread itself is the band
        return dict(value=f1, extrapolated=f1, error=safety * spread,
                    error_pct=100.0 * safety * spread / abs(f1), order=float("nan"),
                    asymptotic_ratio=float("nan"), problems=problems)
    if g.oscillatory:
        error = safety * (max(phi) - min(phi))
        ratio = float("nan")
        problems.append("the result goes up and down with the grid")
    else:
        error = g.gci21 * abs(f1)
        ratio = 1.0
        if g.gci21 > 0.0:
            r21, r32 = h[1] / h[0], h[2] / h[1]
            gci32 = safety * abs((f2 - f3) / f2) / (r32 ** g.p - 1.0)
            ratio = gci32 / (r21 ** g.p * g.gci21)
        if not P_RANGE[0] <= g.p <= P_RANGE[1]:
            problems.append(f"observed order {g.p:.2f} outside {P_RANGE[0]}..{P_RANGE[1]}")
        if abs(ratio - 1.0) > ASYMPTOTIC_TOL:
            problems.append(f"not in the asymptotic range (ratio {ratio:.3f})")
    return dict(value=f1, extrapolated=f1 if g.oscillatory else g.phi_ext, error=error,
                error_pct=100.0 * error / abs(f1), order=g.p, asymptotic_ratio=ratio,
                problems=problems)


def run_duct_level(design_file: str, Nz: int, Nr: int) -> Dict:
    """Solve an optimised duct on one grid and return its thrust."""
    from ..optimization.shape_opt import DuctProblem, for_grid, report
    from ..optimization.target_thrust import load_design
    from ..solver.turbulence import wall_y_plus

    case, layout, design = load_design(design_file)
    problem = DuctProblem(for_grid(case, Nz, Nr), layout)
    t0 = time.time()
    sol = problem.solve(design)
    summary = report(problem, design)
    uz, ur = sol.system.velocities(sol.x)
    return dict(Nz=Nz, Nr=Nr, cells=Nz * Nr, converged=bool(sol.converged),
                settled=bool(sol.settled), residual=float(sol.residual),
                time_s=time.time() - t0, thrust=summary["thrust"], thrust_from_forces=summary["thrust_from_forces"],
                y_plus=float(wall_y_plus(uz, ur, sol.system.mesh, case.nu).max()))


def duct_study(design_file: str, levels: Sequence[Tuple[int, int]], jobs: int) -> Dict:
    """Grid study of the thrust of an optimised duct.

    Returns the estimate on the finest three grids: value, extrapolated
    value, error band, and the reasons not to trust it, if any.
    """
    out_dir = os.path.dirname(os.path.abspath(design_file))
    print(f"Thrust grid study: {', '.join(f'{nz}x{nr}' for nz, nr in levels)}, "
          f"{jobs} at a time.", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(run_duct_level, design_file, nz, nr)
                   for nz, nr in levels]
        rows = [f.result() for f in as_completed(futures)]

    rows.sort(key=lambda r: -r["cells"])          # finest first
    h = [r["cells"] ** -0.5 for r in rows]
    lines = ["# Thrust grid study", "",
             "| grid | cells | h / h_finest | converged | y+ | thrust [N] | from forces [N] |",
             "|---|---|---|---|---|---|---|"]
    for r, hi in zip(rows, h):
        lines.append(f"| {r['Nz']} x {r['Nr']} | {r['cells']} | {hi / h[0]:.3f} | "
                     f"{'yes' if r['converged'] else 'NO'} | {r['y_plus']:.2f} | "
                     f"{r['thrust']:.5f} | {r['thrust_from_forces']:.5f} |")
    lines += ["", "| grids (fine, middle, coarse) | observed order p | extrapolated thrust "
              "| GCI on the finest thrust | notes |", "|---|---|---|---|---|"]
    for k in range(len(rows) - 2):
        g = gci(h[k:k + 3], [rows[k + i]["thrust"] for i in range(3)])
        name = ", ".join(f"{rows[k + i]['Nz']}x{rows[k + i]['Nr']}" for i in range(3))
        lines.append(_fmt_gci(name, g, _notes(rows[k:k + 3])))

    estimate = error_estimate(h[:3], [r["thrust"] for r in rows[:3]])
    notes = _notes(rows[:3])
    if notes != "ok":
        estimate["problems"].append(notes)
    estimate.update(reliable=not estimate["problems"],
                    grids=[f"{r['Nz']}x{r['Nr']}" for r in rows[:3]])
    lines += ["", f"Thrust: {estimate['value']:.4f} +/- {estimate['error']:.4f} N "
              f"({estimate['error_pct']:.2f} %), extrapolated {estimate['extrapolated']:.4f} N, "
              + ("reliable." if estimate["reliable"]
                 else "NOT reliable: " + "; ".join(estimate["problems"]) + ".")]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "grid_study.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(out_dir, "thrust_estimate.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(estimate=estimate, grids=rows), fh, indent=1)
    print("\n" + text)
    return estimate


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    levels = parse_levels(args.levels)
    if len(levels) < 3:
        print("Error: at least three grids are needed.")
        return 1
    if args.duct:
        duct_study(args.duct, levels, args.jobs)
        return 0

    # Same ramp width on every grid: taken from the coarsest one, which
    # needs the widest ramp to keep its cells within 20 % of each other.
    from ..cli import config_from_args
    from ..solver.fvmesh import throat_ramp_width
    from ..geometry import create_venturi_geometry
    a0 = argparse.Namespace(**vars(args))
    a0.Nz, a0.Nr = levels[0]
    cfg0 = config_from_args(a0)
    geom0 = create_venturi_geometry(cfg0)
    zs = geom0.z_stations
    ramp = (throat_ramp_width(geom0.L_total, levels[0][0], zs[2], zs[3], cfg0.throat_refine)
            if cfg0.throat_refine > 1.0 else 0.5)
    from ..cli import RESULTS_DIR
    out_dir = os.path.join(RESULTS_DIR, "misuratore_grid_study_" + os.path.basename(cfg0.output_dir))
    os.makedirs(out_dir, exist_ok=True)

    print(f"Grid study: {', '.join(f'{nz}x{nr}' for nz, nr in levels)}; "
          f"tol {args.tol:g}, throat refinement {cfg0.throat_refine:.2f}, "
          f"ramp {ramp:.3f} throat lengths, {args.jobs} at a time.", flush=True)
    arg_dict = {k: v for k, v in vars(args).items() if k not in ("levels", "jobs")}
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_level, arg_dict, nz, nr, ramp) for nz, nr in levels]
        rows = []
        for f in as_completed(futures):
            r = f.result()
            rows.append(r)
            print(f"  {r['Nz']:4d} x {r['Nr']:3d}: {r['iters']:7d} iterations, "
                  f"{'converged' if r['converged'] else 'NOT converged'}, "
                  f"{r['time_s']:6.1f} s, residual {r['residual']:.2e}, "
                  f"C_d {r['Cd']:.5f}, y+ {r['y_plus']:.2f}", flush=True)

    rows.sort(key=lambda r: -r["cells"])          # finest first
    h = [r["cells"] ** -0.5 for r in rows]
    lines = ["# Grid study", "",
             f"Case: `{os.path.basename(cfg0.output_dir)}`, time step `{cfg0.time_step}`, "
             f"residual target {args.tol:g}, throat refinement {cfg0.throat_refine:.2f}, "
             f"ramp {ramp:.3f} throat lengths.", "",
             "| grid | cells | h / h_finest | iterations | converged | y+ | C_d | dp [Pa] | recovery [%] |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r, hi in zip(rows, h):
        lines.append(f"| {r['Nz']} x {r['Nr']} | {r['cells']} | {hi / h[0]:.3f} | {r['iters']} | "
                     f"{'yes' if r['converged'] else 'NO'} | {r['y_plus']:.2f} | "
                     f"{r['Cd']:.5f} | {r['dp']:.1f} | {100 * r['recovery']:.2f} |")
    lines += ["", "Richardson extrapolation and GCI (Celik et al. 2008), "
              "each row uses three consecutive grids:", "",
              "| grids (fine, middle, coarse) | observed order p | extrapolated C_d | GCI on the finest C_d | notes |",
              "|---|---|---|---|---|"]
    for k in range(len(rows) - 2):
        g = gci(h[k:k + 3], [rows[k + i]["Cd"] for i in range(3)])
        name = ", ".join(f"{rows[k + i]['Nz']}x{rows[k + i]['Nr']}" for i in range(3))
        lines.append(_fmt_gci(name, g, _notes(rows[k:k + 3])))
    lines += ["", "Read the GCI as: the grid-independent C_d is expected within "
              "+/- GCI of the finest-grid value. A row is only as reliable as its "
              "notes say: a grid that did not converge carries iteration error "
              "too, and y+ above 5 is outside what the wall models need."]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "grid_study.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(out_dir, "grid_study.csv"), "w", encoding="utf-8") as fh:
        keys = list(rows[0].keys())
        fh.write(",".join(keys) + "\n")
        for r in rows:
            fh.write(",".join(str(r[k]) for k in keys) + "\n")
    print("\n" + text)
    print(f"Written to {out_dir}{os.sep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
