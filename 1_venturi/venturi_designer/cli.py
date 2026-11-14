"""
cli.py
======
Command line, interactive wizard and the two run pipelines:

    --optimize   thrust per nozzle -> dp loop with shape optimisation -> grid
                 study -> dp on the finest grid -> risultati/<caso>/2_venturi/
    (classic)    flowmeter Venturi: inputs -> sizing -> wall profile -> grid ->
                 flow solution -> checks -> risultati/misuratore_<name>/
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import os
import sys
import time
from dataclasses import replace
from typing import Callable, Optional

from .analysis.grid_study import duct_study
from .analysis.validation import print_report, to_dict, validate
from .core.config import VenturiConfig
from .core.fluids import FLUIDS, list_fluids
from .core.propulsion import GRID_LEVELS, PropulsionCase
from .export import export_all
from .export.duct import export_duct_results, output_dirs
from .geometry import create_venturi_geometry
from .optimization.shape_opt import DuctProblem, for_grid, initial_design, report
from .optimization.sizing import run_optimization
from .optimization.fan_curve import FanCurve, operating_point
from .optimization.alternatives import alternatives_table, lengths_from_input, run_alternatives
from .optimization.exit_sweep import exit_sweep_table, optimisation_history, run_exit_sweep
from .optimization.scan import plot_scan, run_scan
from .optimization.target_thrust import (SizingResult, initial_dp, match_thrust, save_design,
                                         size_for_thrust)
from .solver import solve_fv
from .solver.fvmesh import build_fvmesh
from .solver.turbulence import SUPPORTED as TURBULENCE_MODELS

# Results folder of the case, shared with the other modules of the project
CASO_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "0_spinta", "spinta_designer",
                         "caso.py")


def _load_caso():
    spec = importlib.util.spec_from_file_location("progetto_caso", CASO_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


caso = _load_caso()
RESULTS_DIR = caso.RESULTS_DIR
INPUT_FILE = caso.INPUT_FILE
REQUIRED_INPUTS = ("fluid", "V0", "p_amb", "D_ext_max", "L_max", "L_disk", "grid")
OPTIMISERS = ("griglia", "griglia+forma", "slsqp")

EPILOG = """\
examples:
  python run_venturi.py --D 0.1 --beta 0.5 --fluid water_20C --p-inlet 101325 --p-throat 95000
  python run_venturi.py --fluid custom --rho 1.2 --mu 1.8e-5 --p-inlet 200000 --p-throat 180000
  python run_venturi.py --list-fluids
  python run_venturi.py --optimize                 duct and dp for the thrust of input.py

run time (single CPU core):
  90 x 36 grid (default)   about 10 s
  128 x 51 grid            about 35 s, see "Speed" in the README
"""


def _refine(text: str):
    """--throat-refine accepts 'auto' or a number."""
    if text.strip().lower() == "auto":
        return "auto"
    try:
        return float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected 'auto' or a number, got '{text}'")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="venturi", description="Design a Venturi tube and check it with a flow simulation.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG)
    a = p.add_argument

    a("--list-fluids", action="store_true", help="Print the preset fluids and exit.")
    a("--optimize", action="store_true",
      help="Size the duct and the fan dp for the thrust per nozzle (VENTURI of input.py).")
    a("--input", default=INPUT_FILE, help="Input file of --optimize.")
    a("--fluid", default="water_20C", choices=list(FLUIDS) + ["custom"],
      help="Preset fluid (default: water_20C).")
    a("--rho", type=float, default=None, help="Density [kg/m3], needed with --fluid custom.")
    a("--mu", type=float, default=None, help="Dynamic viscosity [Pa s], needed with --fluid custom.")
    a("--p-vap", type=float, default=None,
      help="Vapour pressure [Pa] for --fluid custom (default 0: no cavitation check).")

    a("--D", type=float, default=0.100, help="Pipe diameter [m] (default 0.1).")
    a("--beta", type=float, default=0.50, help="Throat diameter / pipe diameter (default 0.5).")
    a("--alpha-conv", type=float, default=21.0, help="Total angle of the converging cone [deg].")
    a("--alpha-div", type=float, default=8.0, help="Total angle of the diverging cone [deg].")
    a("--no-blend", action="store_true", help="Sharp corners instead of rounded ones.")
    a("--wall", type=float, default=0.003, help="Tube wall thickness of the CAD files [m].")

    a("--p-inlet", type=float, default=101325.0, help="Upstream pressure [Pa].")
    a("--p-throat", type=float, default=95000.0, help="Wanted throat pressure [Pa].")
    a("--cd-design", type=float, default=1.0,
      help="Discharge coefficient assumed when sizing (1 = no friction).")

    a("--Nz", type=int, default=90, help="Cells along the axis (default 90).")
    a("--Nr", type=int, default=36, help="Cells along the radius (default 36).")
    a("--clustering", type=float, default=2.7,
      help="Wall clustering: 0 = even cells, larger = thinner cells at the wall.")
    a("--throat-refine", type=_refine, default="auto",
      help="How many times shorter the throat cells are: 'auto' (default) "
           "= 1/beta^2, capped at 6, or a number >= 1 (1 = even spacing).")
    a("--turbulence", default="baldwin_lomax", choices=list(TURBULENCE_MODELS),
      help="Turbulence model (default baldwin_lomax).")
    a("--max-iter", type=int, default=400000, help="Iteration limit.")
    a("--tol", type=float, default=1e-3, help="Steady-state target for the residual.")
    a("--cfl", type=float, default=0.6, help="CFL number, the time step safety factor.")
    a("--time-step", default="local", choices=["local", "global"],
      help="local: each cell takes its own largest stable step (default); "
           "global: all cells take the smallest one (slower, same result).")

    a("--cd-ref", type=float, default=None,
      help="Reference C_d to compare with (for example from a datasheet).")
    a("--cd-tol", type=float, default=3.0, help="Allowed deviation from --cd-ref [%%].")

    a("--output-dir", default=None,
      help="Output folder (default: risultati/<caso>/2_venturi with --optimize, "
           "risultati/misuratore_<name> otherwise).")
    a("--no-export", action="store_true", help="Compute only, write no files.")
    return p


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------
def _ask(prompt: str, default, cast: Callable = float, check: Optional[Callable] = None):
    """Ask until the answer can be converted and passes the check."""
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = cast(raw)
        except ValueError:
            print("  Not a valid value, try again.")
            continue
        if check is not None and not check(value):
            print("  Value out of range, try again.")
            continue
        return value


def interactive_wizard() -> argparse.Namespace:
    args = build_parser().parse_args([])
    print("=" * 66)
    print("  VENTURI DESIGN - INTERACTIVE MODE")
    print("=" * 66)
    print("\n  [1] I choose D and beta")
    print("  [2] choose them for me from a flow rate")
    mode = _ask("Mode", 1, int, lambda v: v in (1, 2))

    print("\nFluids: " + ", ".join(FLUIDS))
    args.fluid = _ask("Fluid", "water_20C", str, lambda v: v in FLUIDS)
    args.p_inlet = _ask("Upstream pressure [Pa]", 101325.0, float, lambda v: v > 0)
    args.p_throat = _ask("Throat pressure [Pa]", 95000.0, float,
                         lambda v: 0 < v < args.p_inlet)

    if mode == 2:
        Q = _ask("Flow rate [m3/s]", 0.05, float, lambda v: v > 0)
        print("\n  [1] smallest pressure loss\n  [2] shortest tube\n  [3] balanced")
        obj = _ask("Goal", 3, int, lambda v: v in (1, 2, 3))
        rho = FLUIDS[args.fluid].density_at(args.p_inlet)
        res = run_optimization(Q, args.p_inlet, args.p_throat, rho, obj)
        if not res["success"]:
            print(f"  Warning: the optimiser did not fully converge ({res['message']}).")
        print(f"  Chosen: D = {res['D_inlet']*1000:.1f} mm, beta = {res['beta']:.3f}, "
              f"alpha_div = {res['alpha_div_deg']:.1f} deg")
        args.D, args.beta, args.alpha_div = res["D_inlet"], res["beta"], res["alpha_div_deg"]
    else:
        args.D = _ask("Pipe diameter D [m]", 0.1, float, lambda v: v > 0)
        args.beta = _ask("beta = d/D", 0.5, float, lambda v: 0 < v < 1)
    return args


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def default_output_dir(args) -> str:
    name = (f"{args.fluid}_D{args.D*1000:.0f}_beta{args.beta:.2f}"
            f"_Pin{int(args.p_inlet)}_Pth{int(args.p_throat)}")
    return os.path.join(RESULTS_DIR, "misuratore_" + name)


def config_from_args(args) -> VenturiConfig:
    return VenturiConfig(
        D=args.D, beta=args.beta,
        alpha_conv_deg=args.alpha_conv, alpha_div_deg=args.alpha_div,
        use_blend_radii=not args.no_blend, wall_thickness=args.wall,
        p_inlet=args.p_inlet, p_throat_target=args.p_throat, cd_design=args.cd_design,
        fluid=args.fluid, rho=args.rho, mu=args.mu, p_vap=args.p_vap,
        Nz=args.Nz, Nr=args.Nr, wall_clustering=args.clustering,
        throat_refine=args.throat_refine,
        turbulence_model=args.turbulence, cfl=args.cfl, time_step=args.time_step,
        max_iter=args.max_iter, tol=args.tol,
        output_dir=args.output_dir or default_output_dir(args))


def load_inputs(path: str) -> dict:
    """The VENTURI dictionary of the input file."""
    inputs = caso.load_input(path)["VENTURI"]
    if not inputs:
        raise ValueError(f"{path} does not define the VENTURI dictionary.")
    missing = [k for k in REQUIRED_INPUTS if inputs.get(k) is None]
    if missing:
        raise ValueError(f"Missing in {path}: {', '.join(missing)}.")
    if inputs["grid"] not in GRID_LEVELS:
        raise ValueError(f"grid must be one of {', '.join(GRID_LEVELS)}, got '{inputs['grid']}'.")
    mode = inputs.get("ottimizzatore", "griglia")
    if mode not in OPTIMISERS:
        raise ValueError(f"ottimizzatore must be one of {', '.join(OPTIMISERS)}, got '{mode}'.")
    return inputs


def thrust_target(inputs: dict, input_file: str, results_dir: Optional[str] = None):
    """Thrust per nozzle [N] and where it comes from.

    T_ugello of input.py when it is a number, otherwise spinta.json of the
    case, written by 0_spinta.
    """
    if inputs.get("T_ugello") is not None:
        return float(inputs["T_ugello"]), "input.py (T_ugello)"
    path = caso.thrust_file(input_file, results_dir)
    if not os.path.isfile(path):
        raise ValueError(f"{caso.shown(path)} not found: run the thrust step first "
                         f"(python 0_spinta/run_spinta.py or python run_sistema.py), "
                         f"or set T_ugello in VENTURI.")
    with open(path, encoding="utf-8") as fh:
        return float(json.load(fh)["T_ugello_N"]), caso.shown(path)


def load_case(path: str, T_target: Optional[float] = None):
    """The PropulsionCase of the input file, and the whole VENTURI dictionary."""
    inputs = load_inputs(path)
    fields = {f.name for f in dataclasses.fields(PropulsionCase) if f.init} - {"dp_disk",
                                                                               "T_target"}
    case = PropulsionCase(T_target=T_target,
                          **{k: v for k, v in inputs.items() if k in fields and v is not None})
    return case, inputs


def scan_sizing(case, layout, inputs, level, curve, T, dirs, match=True, procs=1):
    """Grid scan of the duct (scan.py), then the dp for the thrust when there is no curve
    (match=False: the scan only, the shape optimisation follows). procs > 1: the cases of the
    scan in that many processes, each from a cold start."""
    grid = level["optimise"][-1]
    _, d0 = initial_design(case, inputs.get("n_up", 5), inputs.get("n_down", 8))
    case = replace(case, dp_disk=initial_dp(case, layout, d0))
    print(f"\nGrid scan on {grid[0]} x {grid[1]}: "
          f"{inputs.get('scansione_D_uscita', 5)} exit diameters x "
          f"{inputs.get('scansione_L_diffusore', 4)} diffuser lengths, "
          f"half angle <= {case.semiangolo_max_deg:g} deg, separated cases (tau_w < 0) discarded")
    if case.semiangolo_max_deg > 5.0:
        print(f"WARNING: semiangolo_max_deg = {case.semiangolo_max_deg:g} deg in the input; "
              "diffusers above ~4-5 deg tend to separate")
    scan = run_scan(case, layout, grid, curve, inputs.get("D_ventola"),
                    inputs.get("scansione_D_uscita", 5), inputs.get("scansione_L_diffusore", 4),
                    case.semiangolo_max_deg, case.P_max, dirs["convergenza"], procs=procs)
    problem, design = scan.pop("problem"), scan.pop("design")
    b = scan["migliore"]
    print(f"Chosen: D_exit {b['D_uscita_mm']:.1f} mm, diffuser {b['L_diffusore_mm']:.1f} mm, "
          f"T {b['spinta_N']:.5f} N at dp {b['dp_Pa']:.3f} Pa")
    steps = [dict(ciclo=1, tipo="scansione", griglia=scan["griglia"], dp_disk=b["dp_Pa"],
                  spinta=b["spinta_N"])]
    exponent = 1.0
    if curve is None and match:
        print(" Secant on dp for the wanted thrust")
        problem, rows, exponent = match_thrust(problem, design, T, cycle=1)
        steps += rows
    return SizingResult(problem=problem, design=design, steps=steps, exponent=exponent,
                        converged=True), scan


GRID_STUDY_SKIPPED = "studio di griglia solo nella passata finale"


def run_target_thrust(args) -> int:
    """Duct and fan dp for the thrust per nozzle, see the module docstring.

    args.procs = processes this run may use in all (the budget of run_sistema.py, see
    parallel.py): scan, alternatives and exit scan split it, the grid study takes
    min(jobs, procs). Missing (None, e.g. run_venturi.py alone) = as always: sequential, the
    grid study with VENTURI["jobs"] processes.
    args.skip_extras = intermediate pass of the fan band: no alternatives, no exit scan, no
    grid study (the error band is only needed in the final pass); the dp on the finest grid is
    still computed, with the secant starting from the dp of the optimisation grid.
    """
    results_dir = getattr(args, "results_dir", None)
    procs = getattr(args, "procs", None)
    inner = max(1, int(procs or 1))
    try:
        inputs = load_inputs(args.input)
        T, source = thrust_target(inputs, args.input, results_dir)
        case, inputs = load_case(args.input, T)
        layout, design = initial_design(case, inputs.get("n_up", 5), inputs.get("n_down", 8))
        root = args.output_dir or caso.step_dir("venturi", args.input, results_dir)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    dirs = output_dirs(root)
    level = GRID_LEVELS[inputs["grid"]]
    print(f"Thrust per nozzle {T:.5g} N (from {source})")
    mode = inputs.get("ottimizzatore", "griglia")
    scan_mode = mode in ("griglia", "griglia+forma")
    print(f"Tube within D {case.D_ext_max * 1e3:.1f} mm x L {case.L_max * 1e3:.1f} mm, inner duct "
          f"up to D {2e3 * case.R_int_max:.1f} mm, "
          + ("scan variables: exit diameter x diffuser length" if scan_mode
             else f"{layout.n_vars} design variables"))

    t0 = time.time()
    try:
        curve = FanCurve.from_input(inputs.get("curva_ventola"))
        if curve is not None:
            print("Fan curve " + ("(FICTITIOUS EXAMPLE)" if curve.fictitious else "")
                  + f": {len(curve.Q)} points, operating point on the curve")
        if mode == "griglia":
            res, scan = scan_sizing(case, layout, inputs, level, curve, T, dirs, procs=inner)
        elif mode == "griglia+forma":
            if curve is not None:
                raise ValueError("the fan curve works with ottimizzatore = 'griglia' only "
                                 "(the shape optimisation does not support it).")
            res0, scan = scan_sizing(case, layout, inputs, level, curve, T, dirs, match=False,
                                     procs=inner)
            print("\nShape optimisation from the scan design")
            res = size_for_thrust(case, layout, res0.design, level["optimise"],
                                  max_iter=inputs.get("max_iter", 40),
                                  tol_dp=inputs.get("tol_dp", 0.01),
                                  max_cycles=inputs.get("max_cicli_dp", 4),
                                  out_dir=dirs["convergenza"])
            res.steps = res0.steps + res.steps
        else:
            if curve is not None:
                raise ValueError("the fan curve works with ottimizzatore = 'griglia' only.")
            scan = None
            res = size_for_thrust(case, layout, design, level["optimise"],
                                  max_iter=inputs.get("max_iter", 40),
                                  tol_dp=inputs.get("tol_dp", 0.01),
                                  max_cycles=inputs.get("max_cicli_dp", 4),
                                  out_dir=dirs["convergenza"])
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        return 2
    design, problem = res.design, res.problem
    alternatives = None
    skip_extras = bool(getattr(args, "skip_extras", False))
    extras = mode == "griglia+forma" and not skip_extras
    lengths = lengths_from_input(inputs.get("alternative_L_tubo"), case) if extras else []
    if lengths:
        print(f"\nAlternatives at fixed tube length: {', '.join(f'{1e3 * L:.1f}' for L in lengths)} mm")
        alt_dir = os.path.join(dirs["convergenza"], "alternative")
        os.makedirs(alt_dir, exist_ok=True)
        alternatives = run_alternatives(case, layout, design, problem, lengths,
                                        level["optimise"][-1],
                                        max_cycles=inputs.get("alternative_max_cicli_dp", 2),
                                        max_iter=inputs.get("max_iter", 40),
                                        tol_dp=inputs.get("tol_dp", 0.01), out_dir=alt_dir,
                                        procs=inner)
        print("\n" + alternatives_table(alternatives))
    exit_sweep = None
    n_exit = int(inputs.get("scansione_uscita", 7) or 0) if extras else 0
    if n_exit > 0:
        print(f"\nExit scan, converging to diverging: {n_exit} points around the optimum")
        exit_sweep = run_exit_sweep(case, layout, design, problem, n_exit, level["optimise"][-1],
                                    os.path.join(dirs["convergenza"], "uscita"),
                                    case.semiangolo_max_deg, procs=inner)
        print("\n" + exit_sweep_table(exit_sweep))
    design_file = save_design(os.path.join(dirs["convergenza"], "design.json"), problem.case,
                              layout, design, report(problem, design))

    est = None
    if skip_extras:
        print(f"\nGrid convergence skipped ({GRID_STUDY_SKIPPED})")
    else:
        print(f"\nGrid convergence, level '{inputs['grid']}'")
        jobs = inputs.get("jobs", 3)
        if procs is not None:                   # the grid study counts in the cap of processes
            jobs = max(1, min(int(jobs), inner))
        est = duct_study(design_file, level["verify"], jobs)
        print(f"Thrust = {est['value']:.5f} +/- {est['error']:.5f} N ({est['error_pct']:.2f} %) "
              f"at dp = {problem.case.dp_disk:.4f} Pa")
        if not est["reliable"]:
            print("WARNING, value not reliable: " + "; ".join(est["problems"]))
        for note in est.get("notes", []):
            print("Note on the grid band: " + note)

    Nz, Nr = level["verify"][-1]
    steps = list(res.steps)
    try:
        if curve is not None:
            # with a fan curve the thrust is a result: operating point on the finest grid
            print(f"\nOperating point on the {Nz} x {Nr} grid")
            fine = DuctProblem(for_grid(problem.case, Nz, Nr), layout)
            fine, op = operating_point(fine, design, curve, problem.case.dp_disk, verbose=True)
            rows, k = [dict(tipo="punto di lavoro", **{a: b for a, b in op.items() if a != "passi"})], 1.0
        else:
            # the same thrust on the finest grid: dp scaled with the measured exponent
            # (without the grid study: from the dp of the optimisation grid, the secant on the
            # finest grid converges to the same thrust)
            dp = problem.case.dp_disk
            if est is not None:
                dp *= (T / est["value"]) ** (1.0 / res.exponent)
            print(f"\nFinal dp on the {Nz} x {Nr} grid")
            fine = DuctProblem(for_grid(replace(problem.case, dp_disk=dp), Nz, Nr), layout)
            fine, rows, k = match_thrust(fine, design, T, res.exponent, cycle=0)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 2
    for row in rows:
        row["tipo"] = "finale"
    steps += rows
    with open(os.path.join(dirs["convergenza"], "iterazioni_dp.json"), "w", encoding="utf-8") as fh:
        json.dump(steps, fh, indent=1)
    history = None
    try:
        history = optimisation_history(dirs["convergenza"], scan, case)
    except Exception as e:                      # the path of the optimiser is a nicety
        print(f"Warning: optimiser history not written ({e})")
    summary = report(fine, design)
    save_design(design_file, fine.case, layout, design, summary)
    if est is None:                              # no error band in this pass
        dp_error = float("nan")
        est_info = dict(method="assente", notes=[GRID_STUDY_SKIPPED], problems=[],
                        reliable=False, saltato=True)
    else:
        dp_error = fine.case.dp_disk * est["error_pct"] / 100.0 / k
        est_info = est

    print("\nFiles")
    out = export_duct_results(fine, design, summary, dirs, dict(
        source=source, estimate=est_info, dp_error=dp_error, exponent=k, steps=steps,
        converged=res.converged, scan=scan, curve=curve.to_dict() if curve else None,
        alternatives=alternatives, exit_sweep=exit_sweep, history=history))
    if scan:
        plot_scan(scan, os.path.join(dirs["grafici"], "scansione.svg"))
    r = out["results"]
    print(f"  {len(out['files'])} files in {caso.shown(root)}{os.sep}")
    print("\n" + "=" * 66)
    band = "(error band: final pass only)" if est is None else f"+/- {dp_error:.4f} Pa"
    print(f"dp disk = {fine.case.dp_disk:.4f} {band}, fan D = "
          f"{r['ventola']['D_ventola_m'] * 1e3:.2f} mm, Q = {r['ventola']['portata_m3_s'] * 1e3:.3f} L/s, "
          f"P = {r['ventola']['potenza_fluido_W']:.4f} W")
    print(f"thrust {summary['thrust']:.5g} N (wanted {T:.5g}), tube {r['geometria']['D_esterno_tubo_mm']:.1f}"
          f" x {r['geometria']['L_tubo_mm']:.1f} mm, {time.time() - t0:.0f} s")
    print("=" * 66)
    ok = (est is None or est["reliable"]) and r["geometria"]["ingombro_rispettato"]
    if not ok:
        print("Some checks failed: see 00_sintesi/RISULTATO.md")
    return 0 if ok else 3


def run(args) -> int:
    if args.list_fluids:
        print(list_fluids())
        print("\nOwn fluid: --fluid custom --rho <value> --mu <value> [--p-vap <value>]")
        return 0
    if args.optimize:
        return run_target_thrust(args)

    print("\n[1/6] Sizing from the inputs")
    try:
        config = config_from_args(args)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    print(config.summary())
    for w in config.warnings():
        print(f"  [WARNING] {w}")

    print("\n[2/6] Wall profile")
    geom = create_venturi_geometry(config)
    print(f"      total length {geom.L_total*1000:.1f} mm  "
          f"(inlet {geom.L_inlet*1000:.1f}, converging {geom.L_conv*1000:.1f}, "
          f"throat {geom.L_throat*1000:.1f}, diverging {geom.L_div*1000:.1f}, "
          f"outlet {geom.L_outlet*1000:.1f})")

    print(f"\n[3/6] Grid {config.Nz} x {config.Nr}")
    mesh = build_fvmesh(geom, config.Nz, config.Nr, config.wall_clustering,
                        config.throat_refine)
    print(f"      {mesh.n_cells} cells, volume {mesh.vol.sum()*1e6:.2f} cm3, "
          f"smallest cell {mesh.vol.min()*1e9:.3f} mm3")

    print(f"\n[4/6] Flow solution, turbulence model '{config.turbulence_model}'")
    t0 = time.time()
    result = solve_fv(mesh, config, verbose=True)
    print(f"      {'CONVERGED' if result.converged else 'NOT CONVERGED'} - "
          f"{result.n_iter} iterations in {time.time()-t0:.1f} s, "
          f"residual {result.final_residual:.2e}")

    print("\n[5/6] Checks")
    rep = validate(result, mesh, geom, config, cd_ref=args.cd_ref, cd_tol_pct=args.cd_tol)
    print_report(rep)

    if args.no_export:
        print("\n[6/6] Files: skipped (--no-export)")
    else:
        print("\n[6/6] Files")
        files = export_all(mesh, result.uz, result.ur, result.p, geom, config, to_dict(rep))
        print(f"      {len(files)} files in {config.output_dir}{os.sep}")

    print("\n" + "=" * 66)
    print("RESULT: " + ("ALL CHECKS PASSED" if rep.all_passed else "SOME CHECKS FAILED"))
    print("=" * 66 + "\n")
    return 0 if rep.all_passed else 2


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = interactive_wizard() if not argv else build_parser().parse_args(argv)
    return run(args)

