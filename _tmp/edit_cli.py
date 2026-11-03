p = "1_venturi/venturi_designer/cli.py"
s = open(p, encoding="utf-8").read()
Q3 = '"' * 3

rep = [
('''Command line, interactive wizard and the run pipeline:

    inputs -> sizing -> wall profile -> grid -> flow solution -> checks -> files
''', '''Command line, interactive wizard and the two run pipelines:

    --optimize   thrust per nozzle -> dp loop with shape optimisation -> grid
                 study -> dp on the finest grid -> risultati/<caso>/2_venturi/
    (classic)    flowmeter Venturi: inputs -> sizing -> wall profile -> grid ->
                 flow solution -> checks -> risultati/misuratore_<name>/
'''),
('''from .analysis.grid_study import duct_study
from .analysis.validation import print_report, to_dict, validate
from .core.config import VenturiConfig
from .core.fluids import FLUIDS, list_fluids
from .core.propulsion import GRID_LEVELS, PropulsionCase
from .export import export_all
from .geometry import MorphedGeometry, create_venturi_geometry
from .optimization.shape_opt import (DuctProblem, for_grid, initial_design, optimise,
                                     report)
from .optimization.sizing import run_optimization''',
'''from .analysis.grid_study import duct_study
from .analysis.validation import print_report, to_dict, validate
from .core.config import VenturiConfig
from .core.fluids import FLUIDS, list_fluids
from .core.propulsion import GRID_LEVELS, PropulsionCase
from .export import export_all
from .export.duct import export_duct_results, output_dirs
from .geometry import create_venturi_geometry
from .optimization.shape_opt import DuctProblem, for_grid, initial_design, report
from .optimization.sizing import run_optimization
from .optimization.target_thrust import match_thrust, save_design, size_for_thrust'''),
('''RESULTS_DIR = "results"
INPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "input.py")
REQUIRED_INPUTS = ("fluid", "V0", "p_amb", "dp_disk", "D_disk", "L_disk", "D_max", "L_max",
                   "grid")
''', '''# Results folder of the case, shared with the other modules of the project
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
'''),
('''  python run_venturi.py --optimize                 shape for the largest thrust, from input.py''',
'''  python run_venturi.py --optimize                 duct and dp for the thrust of input.py'''),
('''      help="Optimise the duct shape for the largest thrust, with the inputs of input.py.")''',
'''      help="Size the duct and the fan dp for the thrust per nozzle (VENTURI of input.py).")'''),
('''    a("--output-dir", default=None,
      help=f"Output folder (default: {RESULTS_DIR}/<name built from the inputs>).")''',
'''    a("--output-dir", default=None,
      help="Output folder (default: risultati/<caso>/2_venturi with --optimize, "
           "risultati/misuratore_<name> otherwise).")'''),
('''    return os.path.join(RESULTS_DIR, name)''', '''    return os.path.join(RESULTS_DIR, "misuratore_" + name)'''),
]
for a, b in rep:
    assert a in s, a
    s = s.replace(a, b, 1)

i0 = s.index("def load_inputs(path: str) -> dict:")
i1 = s.index("def run(args) -> int:")
new = '''def load_inputs(path: str) -> dict:
    QQQThe VENTURI dictionary of the input file.QQQ
    inputs = caso.load_input(path)["VENTURI"]
    if not inputs:
        raise ValueError(f"{path} does not define the VENTURI dictionary.")
    missing = [k for k in REQUIRED_INPUTS if inputs.get(k) is None]
    if missing:
        raise ValueError(f"Missing in {path}: {', '.join(missing)}.")
    if inputs["grid"] not in GRID_LEVELS:
        raise ValueError(f"grid must be one of {', '.join(GRID_LEVELS)}, got '{inputs['grid']}'.")
    return inputs


def thrust_target(inputs: dict, input_file: str, results_dir: Optional[str] = None):
    QQQThrust per nozzle [N] and where it comes from.

    T_ugello of input.py when it is a number, otherwise spinta.json of the
    case, written by 0_spinta.
    QQQ
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
    QQQThe PropulsionCase of the input file, and the whole VENTURI dictionary.QQQ
    inputs = load_inputs(path)
    fields = {f.name for f in dataclasses.fields(PropulsionCase) if f.init} - {"dp_disk",
                                                                               "T_target"}
    case = PropulsionCase(T_target=T_target,
                          **{k: v for k, v in inputs.items() if k in fields and v is not None})
    return case, inputs


def run_target_thrust(args) -> int:
    QQQDuct and fan dp for the thrust per nozzle, see the module docstring.QQQ
    results_dir = getattr(args, "results_dir", None)
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
    print(f"Tube within D {case.D_ext_max * 1e3:.1f} mm x L {case.L_max * 1e3:.1f} mm, inner duct "
          f"up to D {2e3 * case.R_int_max:.1f} mm, {layout.n_vars} design variables")

    t0 = time.time()
    try:
        res = size_for_thrust(case, layout, design, level["optimise"],
                              max_iter=inputs.get("max_iter", 40),
                              tol_dp=inputs.get("tol_dp", 0.01),
                              max_cycles=inputs.get("max_cicli_dp", 4),
                              out_dir=dirs["convergenza"])
    except RuntimeError as e:
        print(f"Error: {e}")
        return 2
    design, problem = res.design, res.problem
    design_file = save_design(os.path.join(dirs["convergenza"], "design.json"), problem.case,
                              layout, design, report(problem, design))

    print(f"\\nGrid convergence, level '{inputs['grid']}'")
    est = duct_study(design_file, level["verify"], inputs.get("jobs", 3))
    print(f"Thrust = {est['value']:.5f} +/- {est['error']:.5f} N ({est['error_pct']:.2f} %) "
          f"at dp = {problem.case.dp_disk:.4f} Pa")
    if not est["reliable"]:
        print("WARNING, value not reliable: " + "; ".join(est["problems"]))

    # the same thrust on the finest grid: dp scaled with the measured exponent
    Nz, Nr = level["verify"][-1]
    dp = problem.case.dp_disk * (T / est["value"]) ** (1.0 / res.exponent)
    print(f"\\nFinal dp on the {Nz} x {Nr} grid")
    fine = DuctProblem(for_grid(replace(problem.case, dp_disk=dp), Nz, Nr), layout)
    steps = list(res.steps)
    try:
        fine, rows, k = match_thrust(fine, design, T, res.exponent, cycle=0)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 2
    for row in rows:
        row["tipo"] = "finale"
    steps += rows
    with open(os.path.join(dirs["convergenza"], "iterazioni_dp.json"), "w", encoding="utf-8") as fh:
        json.dump(steps, fh, indent=1)
    summary = report(fine, design)
    save_design(design_file, fine.case, layout, design, summary)
    dp_error = fine.case.dp_disk * est["error_pct"] / 100.0 / k

    print("\\nFiles")
    out = export_duct_results(fine, design, summary, dirs, dict(
        source=source, estimate=est, dp_error=dp_error, exponent=k, steps=steps,
        converged=res.converged))
    r = out["results"]
    print(f"  {len(out['files'])} files in {caso.shown(root)}{os.sep}")
    print("\\n" + "=" * 66)
    print(f"dp disk = {fine.case.dp_disk:.4f} +/- {dp_error:.4f} Pa, fan D = "
          f"{r['ventola']['D_ventola_m'] * 1e3:.2f} mm, Q = {r['ventola']['portata_m3_s'] * 1e3:.3f} L/s, "
          f"P = {r['ventola']['potenza_fluido_W']:.4f} W")
    print(f"thrust {summary['thrust']:.5g} N (wanted {T:.5g}), tube {r['geometria']['D_esterno_tubo_mm']:.1f}"
          f" x {r['geometria']['L_tubo_mm']:.1f} mm, {time.time() - t0:.0f} s")
    print("=" * 66)
    ok = est["reliable"] and r["geometria"]["ingombro_rispettato"]
    if not ok:
        print("Some checks failed: see 00_sintesi/RISULTATO.md")
    return 0 if ok else 3


'''.replace("QQQ", Q3)
s = s[:i0] + new + s[i1:]
s = s.replace("        return run_shape_optimisation(args)", "        return run_target_thrust(args)")
s = s.replace("import time\nfrom typing import Callable, Optional",
              "import time\nfrom dataclasses import replace\nfrom typing import Callable, Optional")
open(p, "w", encoding="utf-8").write(s)
print("ok")
