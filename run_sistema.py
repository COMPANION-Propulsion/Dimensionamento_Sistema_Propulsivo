"""
run_sistema.py
==============
Whole chain of the propulsion sizing, from input.py to risultati/<caso>/.

    1. 0_spinta    mission -> thrust per nozzle             -> 1_spinta/
    2. 1_venturi   thrust, size -> duct, fan dp and size    -> 2_venturi/   (duct, uniform disk)
    3. 2_ventola   dp, diameter, flow -> rotor, stator, rpm -> 3_ventola/   (fan alone)
    4. 3_sistema   duct + fan together: power in the manoeuvre, power curve, stator yes/no,
                   duct with the real fan, assembly CAD, 3D views, ParaView -> 4_sistema/
    5. summary of the case                                  -> RIEPILOGO.md

    python run_sistema.py                 the whole chain
    python run_sistema.py --solo sistema  one step only (spinta | venturi | ventola | sistema)
    python run_sistema.py --solo confronto   rewrite 5_confronto_statore/ only (no calculation
                                             of the chains)
    python run_sistema.py --solo riepilogo   rewrite RIEPILOGO.md only (no calculation)

Each step writes only what is its own: what needs both duct and fan is in 4_sistema/.
The fan input is written from VENTOLA of input.py into <chain>/input_ventola.json,
with the explicit path of the venturi of THIS chain (never "the latest one").

Fan band. VENTURI["L_disk"] of input.py is only the starting value: venturi and fan are run,
the real length of rotor (+ stator) is read from the fan CAD, L_disk is reset to
max(upstream, downstream) + VENTOLA["margine_fascia_m"] (at least VENTOLA["fascia_min_m"]) and
the pair is repeated, at most SISTEMA["iterazioni_fascia"] times, until it changes by less than
0.5 mm. The alternatives and the exit scan of the venturi run in the last pass only. History in
<chain>/fascia.json.

Chains. SISTEMA["confronto_statore"] = True: after 1_spinta/ (shared) the chain
venturi -> fan (+ band loop) -> sistema runs twice, in risultati/<caso>/Statore/ and
risultati/<caso>/NoStatore/ (each with 2_venturi, 3_ventola, 4_sistema, input_usato.py,
fascia.json and a copy of 1_spinta/spinta.json), then confronto_varianti writes
risultati/<caso>/5_confronto_statore/. False: one chain in risultati/<caso>/ as before.
Each chain gets its own input_usato.py: input.py + the overridden L_disk, T_ugello (from
spinta.json, so the venturi needs no spinta folder next to it) and stator flag.

--solo venturi | ventola | sistema runs that one step in every chain (no band loop), with the
L_disk of the last pass of fascia.json (input.py if there is none).

Series of cases. A value of input.py written as a string with ";" ("massa": "4; 6") makes a
series: every combination (SISTEMA["combinazioni"]: "tutte" or "accoppiate") is a complete chain
in risultati/<nome>/<etichetta>/ with its own input_usato.py, RIEPILOGO.md and masses; the series
has RIEPILOGO.md and confronto_casi.xlsx in risultati/<nome>/. A failing case does not stop the
others. --solo applies to every case; --solo masse rewrites the mass workbooks only; --elenca
prints the cases and their labels without running anything.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(ROOT, "input.py")
for folder in ("0_spinta", "1_venturi", "2_ventola", "3_sistema"):
    sys.path.insert(0, os.path.join(ROOT, folder))

STEPS = ("spinta", "venturi", "ventola", "sistema")
SOLO = STEPS + ("confronto", "riepilogo", "masse")
SECTIONS = ("SPINTA", "VENTURI", "VENTOLA", "SISTEMA")     # sections where "a; b" makes a series
FAN_DEFAULTS = {
    "temperatura_K": 293.15, "mozzo_su_D": [0.15, 0.25],
    "statore": {"presente": True, "pale": None, "solidita": 1.0, "profilo": "NACA4412",
                "gioco_assiale_m": 0.002},
    "giri_min_max_rpm": [5000.0, 30000.0], "calettamento_min_max_deg": [0.0, 75.0],
    "corda_su_D_min_max": [0.04, 0.22],
    "pale_candidate": [2, 3, 4, 5, 6, 7, 8], "nodi_pala": 2,
    "profili_candidati": ["NACA0012", "NACA2412", "NACA4412", "NACA4415"],
    "durata_s": 1.0, "gioco_punta_m": 0.0005, "potenza_max_W": None, "jobs": None, "sizing": {},
    "margine_fascia_m": 0.001, "fascia_min_m": None,     # band loop: read by run_sistema.py only
}
SISTEMA_DEFAULTS = {"confronto_statore": False, "iterazioni_fascia": 3, "combinazioni": "tutte",
                    "densita_kg_m3": 1240.0, "riempimento": 1.0}
COMBINATIONS = ("tutte", "accoppiate")
VARIANTS = (("Statore", True), ("NoStatore", False))


def run_spinta(input_file: str, results_dir=None) -> int:
    from spinta_designer import run
    return run(input_file, results_dir)


def _load_module(input_file: str, name: str = "project_input_raw"):
    spec = importlib.util.spec_from_file_location(name, input_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_sistema(input_file: str) -> dict:
    """SISTEMA of the input file (defaults for a missing dictionary or key)."""
    module = _load_module(input_file, "project_input_sistema")
    given = dict(getattr(module, "SISTEMA", None) or {})
    unknown = sorted(set(given) - set(SISTEMA_DEFAULTS))
    if unknown:
        raise ValueError(f"Unknown keys in SISTEMA: {', '.join(unknown)}.")
    return {**SISTEMA_DEFAULTS, **given}


# ---------------------------------------------------------------------------
# series of cases: "4; 6" in any value of input.py
# ---------------------------------------------------------------------------

def parse_multi(value):
    """List of values of a string "a; b; c", None when `value` is not a series.

    Each part goes through ast.literal_eval (numbers, None, True, lists...) and stays a string
    when that fails. A string without ";" is a plain value.
    """
    if not isinstance(value, str) or ";" not in value:
        return None
    parts = [p.strip() for p in value.split(";")]
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError(f"{value!r}: no value between the ';'.")
    out = []
    for p in parts:
        try:
            out.append(ast.literal_eval(p))
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            out.append(p)
    return out


def load_raw(input_file: str) -> dict:
    """CASO + SECTIONS of the input file as plain dictionaries (the strings left as written)."""
    module = _load_module(input_file)
    return {name: copy.deepcopy(dict(getattr(module, name, None) or {}))
            for name in ("CASO",) + SECTIONS}


def find_axes(raw: dict):
    """[(section, path, values)] of the keys with several values, in file order."""
    axes = []

    def walk(section, d, path):
        for key, val in d.items():
            if isinstance(val, dict):
                walk(section, val, path + (key,))
                continue
            values = parse_multi(val)
            if values is not None:
                axes.append((section, path + (key,), values))

    for section in SECTIONS:
        walk(section, raw.get(section, {}), ())
    return axes


def combine(axes, mode: str):
    """[[value of each axis]] of every case: "tutte" = product, "accoppiate" = i-th with i-th."""
    if mode not in COMBINATIONS:
        raise ValueError(f"SISTEMA['combinazioni'] = {mode!r}: use one of {', '.join(COMBINATIONS)}.")
    if not axes:
        return [[]]
    if mode == "tutte":
        return [list(c) for c in itertools.product(*[a[2] for a in axes])]
    sizes = {len(a[2]) for a in axes}
    if len(sizes) > 1:
        detail = ", ".join(f"{a[0]}.{'.'.join(a[1])}: {len(a[2])}" for a in axes)
        raise ValueError("SISTEMA['combinazioni'] = 'accoppiate' needs lists of the same length "
                         f"({detail}).")
    return [list(c) for c in zip(*[a[2] for a in axes])]


def _safe(text) -> str:
    s = re.sub(r"[^A-Za-z0-9._+-]+", "-", str(text)).strip("-.")
    return s or "x"


def make_labels(axes, combos):
    """One folder-safe, unique label per case: massa_4, massa_4__D_ext_max_0.07, statore.presente_False."""
    names = [".".join(a[1]) for a in axes]
    names = [f"{a[0].lower()}.{n}" if names.count(n) > 1 else n for a, n in zip(axes, names)]
    labels, seen = [], {}
    for combo in combos:
        label = "__".join(f"{_safe(n)}_{_safe(v)}" for n, v in zip(names, combo)) or "caso"
        if len(label) > 80:
            label = label[:70].rstrip("-._") + "_" + hashlib.sha1(label.encode()).hexdigest()[:6]
        n = seen.get(label.lower(), 0) + 1
        seen[label.lower()] = n
        labels.append(label if n == 1 else f"{label}_{n}")
    return labels


class _Multi(float):
    """Stand-in of a key with several values when the readable part of the name is built."""
    def __format__(self, spec):
        return "V"

    __str__ = __repr__ = lambda self: "V"

    def __mul__(self, other):
        return self
    __rmul__ = __mul__


def series_name(raw: dict, axes, mode: str) -> str:
    """Name of the series folder: CASO["nome"], else the automatic name of caso.py with the
    key with several values shown as V, and a hash of the input with the strings as written."""
    from spinta_designer import caso
    inputs = {k: copy.deepcopy(raw.get(k, {})) for k in ("CASO", "SPINTA", "VENTURI", "VENTOLA")}
    if inputs["CASO"].get("nome") is not None:
        return caso.case_name(inputs)
    sub = copy.deepcopy(inputs)
    for section, path, values in axes:
        if section not in ("SPINTA", "VENTURI"):
            continue
        d = sub[section]
        for k in path[:-1]:
            d = d[k]
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
        d[path[-1]] = _Multi(1.0) if numeric else "V"
    base = caso.automatic_name(sub).rsplit("_h", 1)[0]
    payload = json.dumps({"input": caso.input_hash(inputs), "combinazioni": mode,
                          "assi": [[s, list(p), v] for s, p, v in axes]}, sort_keys=True, default=str)
    return f"{base}_serie_h{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:7]}"


def _override_expr(base: str, path, value) -> str:
    key = path[0]
    if len(path) == 1:
        return f"{{**{base}, {key!r}: {value!r}}}"
    return f"{{**{base}, {key!r}: {_override_expr(f'{base}.get({key!r}, {{}})', path[1:], value)}}}"


def write_case_input(input_file: str, folder: str, label: str, axes, combo) -> str:
    """folder/input_caso.py: input.py + the override block of the case. Returns its path.

    (The chain copies it to folder/input_usato.py and then writes its own overrides there.)
    """
    with open(input_file, encoding="utf-8") as fh:
        text = fh.read()
    lines = ["", "", f"# ---- run_sistema.py: values of the case {label} ----",
             f'CASO = {{**globals().get("CASO", {{}}), "nome": {label!r}}}']
    for (section, path, _), value in zip(axes, combo):
        lines.append(f"{section} = {_override_expr(f'globals().get({section!r}, {{}})', path, value)}")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "input_caso.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n".join(lines) + "\n")
    return path


def plan_series(input_file: str, results_dir=None) -> dict:
    """The series of input_file: name, folder, axes, and the cases (label, folder, assignment)."""
    from spinta_designer import caso
    raw = load_raw(input_file)
    sis = {**SISTEMA_DEFAULTS, **raw.get("SISTEMA", {})}
    axes = find_axes(raw)
    for section, path, _ in axes:
        if section == "SISTEMA" and path[0] == "combinazioni":
            raise ValueError("SISTEMA['combinazioni'] cannot have several values.")
    mode = sis["combinazioni"]
    combos = combine(axes, mode)
    if not axes:                    # a plain input: the caso.py flow, no series
        return dict(name=None, root=None, axes=[], mode=mode, cases=[], raw=raw)
    name = series_name(raw, axes, mode)
    base = os.path.join(results_dir or caso.RESULTS_DIR, name)
    labels = make_labels(axes, combos)
    cases = [dict(label=lab, folder=os.path.join(base, lab), combo=c) for lab, c in zip(labels, combos)]
    return dict(name=name, root=base, axes=axes, mode=mode, cases=cases, raw=raw)


def describe_series(plan: dict) -> list:
    lines = [f"Series {plan['name']}: {len(plan['cases'])} cases, combinations '{plan['mode']}'",
             f"Folder: {plan['root']}", "Keys with several values:"]
    for section, path, values in plan["axes"]:
        lines.append(f"  {section}.{'.'.join(path)} = {values!r}")
    for c in plan["cases"]:
        lines.append(f"  {c['label']}")
    return lines


def write_masses(case_root: str, sis: dict) -> None:
    """masses.xlsx of one case (sistema_designer.masse); a warning, never an error, if it fails."""
    try:
        from sistema_designer.masse import write_mass_summary
        write_mass_summary(case_root, sis["densita_kg_m3"], sis["riempimento"])
    except ImportError as e:
        print(f"WARNING: masses not written (sistema_designer.masse not available: {e}).")
    except Exception as e:
        print(f"WARNING: masses of {case_root} not written: {e}")


def write_series_masses(plan: dict, rows: list, sis: dict) -> None:
    """confronto_casi.xlsx of the series from the cases that finished."""
    done = [(r["label"], r["folder"]) for r in rows if r["rc"] in (0, 3)]
    if not done:
        return
    try:
        from sistema_designer.masse import write_series_summary
        path = os.path.join(plan["root"], "confronto_casi.xlsx")
        write_series_summary([f for _, f in done], path, [l for l, _ in done],
                             sis["densita_kg_m3"], sis["riempimento"])
        print(f"Series comparison: {path}")
    except ImportError as e:
        print(f"WARNING: confronto_casi.xlsx not written (sistema_designer.masse not available: {e}).")
    except Exception as e:
        print(f"WARNING: confronto_casi.xlsx not written: {e}")


def status_text(rc) -> str:
    if rc is None:
        return "non eseguito"
    return {0: "ok", 3: "ok con avvisi"}.get(rc, f"errore (codice {rc})")


def write_series_summary_md(plan: dict, rows: list) -> str:
    """RIEPILOGO.md of the series: one row per case."""
    lines = [f"# Riepilogo della serie `{plan['name']}`", "",
             f"Combinazioni: `{plan['mode']}`, {len(plan['cases'])} casi.", "",
             "Chiavi con più valori:", ""]
    lines += [f"- `{s}.{'.'.join(p)}`: {', '.join(str(x) for x in v)}" for s, p, v in plan["axes"]]
    lines += ["", "| etichetta | stato | cartella |", "|---|---|---|"]
    lines += [f"| {r['label']} | {status_text(r['rc'])} | `{r['label']}/` |" for r in rows]
    lines += ["", "Ogni cartella ha il proprio `RIEPILOGO.md`. Confronto delle masse: "
              "`confronto_casi.xlsx`.", ""]
    os.makedirs(plan["root"], exist_ok=True)
    path = os.path.join(plan["root"], "RIEPILOGO.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def run_venturi(input_file: str, output_dir=None, skip_extras: bool = False) -> int:
    """Venturi on `input_file`; output_dir = the 2_venturi folder of the chain.

    skip_extras (True: no alternatives and no exit scan) is read by cli with getattr.
    """
    from venturi_designer.cli import run_target_thrust
    return run_target_thrust(argparse.Namespace(input=input_file, output_dir=output_dir,
                                                no_export=False, skip_extras=skip_extras))


def fan_input(input_file: str, root: str = None) -> str:
    """Write the fan input of the chain (root = its folder) and return its path."""
    from spinta_designer import caso
    inputs = caso.load_input(input_file)
    v = {**FAN_DEFAULTS, **inputs["VENTOLA"]}
    unknown = sorted(set(inputs["VENTOLA"]) - set(FAN_DEFAULTS))
    if unknown:
        raise ValueError(f"Unknown keys in VENTOLA: {', '.join(unknown)}.")
    root = root or caso.case_dir(input_file)
    venturi = os.path.join(root, caso.STEP_DIRS["venturi"], "00_sintesi", "risultati.json")
    if not os.path.isfile(venturi):
        raise ValueError(f"{caso.shown(venturi)} not found: run the venturi step first.")
    with open(venturi, encoding="utf-8") as fh:
        D = json.load(fh)["ventola"]["D_ventola_m"]
    lo, hi = v["mozzo_su_D"]
    if not 0.0 < lo < hi < 1.0:
        raise ValueError(f"VENTOLA['mozzo_su_D'] = {v['mozzo_su_D']}: need 0 < min < max < 1.")
    st = {**FAN_DEFAULTS["statore"], **v["statore"]}
    unknown = sorted(set(st) - set(FAN_DEFAULTS["statore"]))
    if unknown:
        raise ValueError(f"Unknown keys in VENTOLA['statore']: {', '.join(unknown)}.")
    data = {
        "description": "Written by run_sistema.py from VENTOLA of input.py.",
        "design_mode": "pressure_flow",
        "velocity_reference": "full_disk_flow",
        "air": {"temperature_K": v["temperatura_K"],
                "static_pressure_Pa": inputs["VENTURI"].get("p_amb", 101325.0),
                "relative_humidity": None},
        "rotor": {"hub_diameter_bounds_m": [lo * D, hi * D],
                  "blade_count_candidates": list(v["pale_candidate"]),
                  "airfoil_candidates": list(v["profili_candidati"]),
                  "profile_constant_along_span": True,
                  "blade_nodes": int(v["nodi_pala"]),
                  "shaft_speed_bounds_rpm": list(v["giri_min_max_rpm"])},
        "operating_points": [{"name": "venturi", "venturi_result": venturi,
                              "duration_s": v["durata_s"]}],
        "sizing": {"loss_model": "none",
                   "pitch_deg_bounds": list(v["calettamento_min_max_deg"]),
                   "chord_over_D_bounds": list(v["corda_su_D_min_max"]), **v["sizing"]},
        "cad": {"tip_clearance_m": v["gioco_punta_m"]},
        "stator": {"enabled": bool(st["presente"]), "vanes": st["pale"],
                   "solidity": st["solidita"], "profile": st["profilo"],
                   "axial_gap_m": st["gioco_assiale_m"]},
    }
    path = os.path.join(root, "input_ventola.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def run_ventola(input_file: str, root: str = None) -> int:
    """Fan sizing (rotor + stator + CAD) of the chain in `root`; the extras are in ventola_extras."""
    from spinta_designer import caso
    from ventola_designer.optimizer import main as size_main
    try:
        path = fan_input(input_file, root)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    jobs = caso.load_input(input_file)["VENTOLA"].get("jobs")
    print(f"Fan input: {caso.shown(path)}")
    try:
        return int(size_main(["--input", path] + (["--jobs", str(jobs)] if jobs else [])))
    except SystemExit as e:            # argparse errors of the fan command line
        return int(e.code or 1)


def ventola_extras(root: str) -> None:
    """Blade-count comparison and boundary layer of the sections: analysis only, run once."""
    from spinta_designer import caso
    fan_dir = os.path.join(root, caso.STEP_DIRS["ventola"])
    try:                               # best accepted fan per blade count, written next to the report
        from ventola_designer.indicatori import scrivi_confronto
        tab = scrivi_confronto(os.path.join(fan_dir, "00_sintesi", "report.json"))
        if tab is not None:
            print("Blade-count comparison: "
                  f"{caso.shown(os.path.join(fan_dir, '00_sintesi', 'CONFRONTO_PALE.md'))}")
    except (OSError, ValueError, KeyError) as e:
        print(f"  blade-count comparison skipped: {e}")
    print("\nBoundary layer of rotor and stator sections (XFOIL)")
    try:                               # analysis only: the sizing results stay valid
        from ventola_designer.cp_map import export_cp
        export_cp(os.path.join(fan_dir, "00_sintesi", "report.json"),
                  os.path.join(ROOT, "2_ventola", "tools", "xfoil", "dist", "xfoil.exe"), 17)
    except (OSError, ValueError) as e:
        print(f"  skipped: {e}")


def run_sistema_step(input_file: str, root: str = None) -> int:
    """Duct and fan together: everything that needs both, in <chain>/4_sistema/."""
    from spinta_designer import caso
    from sistema_designer import run
    root = root or caso.case_dir(input_file)
    fan_report = os.path.join(root, caso.STEP_DIRS["ventola"], "00_sintesi", "report.json")
    if not os.path.isfile(fan_report):
        print("Error: no fan in this case: run the fan step first.")
        return 1
    with open(fan_report, encoding="utf-8") as fh:
        if not json.load(fh).get("best"):
            print("Error: the fan step found no accepted design: nothing to put together.")
            return 2
    inputs = caso.load_input(input_file)
    log = run(root, inputs["VENTOLA"].get("potenza_max_W"), p_cabin=inputs["VENTURI"].get("p_cabina"))
    return 0 if not log.get("errori") else 3


# ---------------------------------------------------------------------------
# chains: one folder with 2_venturi, 3_ventola, 4_sistema and its own input_usato.py
# ---------------------------------------------------------------------------

def _read_json(*parts):
    path = os.path.join(*parts)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def thrust_value(inputs: dict, case_root: str) -> float:
    """Thrust per nozzle [N]: T_ugello of input.py, else 1_spinta/spinta.json of the case."""
    if inputs["VENTURI"].get("T_ugello") is not None:
        return float(inputs["VENTURI"]["T_ugello"])
    data = _read_json(case_root, "1_spinta", "spinta.json")
    if data is None:
        raise ValueError("1_spinta/spinta.json not found: run the thrust step first "
                         "(or set VENTURI['T_ugello']).")
    return float(data["T_ugello_N"])


def write_chain_input(input_file: str, folder: str, label: str, L_disk: float, T_ugello: float,
                      stator=None) -> str:
    """folder/input_usato.py: input.py plus the keys this chain overrides. Returns its path."""
    with open(input_file, encoding="utf-8") as fh:
        text = fh.read()
    lines = ["", "", f"# ---- run_sistema.py: values overridden for this chain ({label}) ----",
             f'VENTURI = {{**VENTURI, "L_disk": {float(L_disk)!r}, "T_ugello": {float(T_ugello)!r}}}']
    if stator is not None:
        lines.append('VENTOLA = {**VENTOLA, "statore": {**VENTOLA.get("statore", {}), '
                     f'"presente": {bool(stator)!r}}}}}')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "input_usato.py")
    if os.path.abspath(path) == os.path.abspath(input_file):
        raise ValueError("the chain input must not overwrite its own source")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n".join(lines) + "\n")
    return path


def chains(root: str, sis: dict):
    """[(label, folder, stator flag or None)] of this run."""
    if sis["confronto_statore"]:
        return [(name, os.path.join(root, name), flag) for name, flag in VARIANTS]
    return [(None, root, None)]


def prepare_chain(case_root: str, folder: str) -> None:
    """The spinta of the case is shared: a copy of spinta.json where sistema/ looks for it."""
    src = os.path.join(case_root, "1_spinta", "spinta.json")
    dst = os.path.join(folder, "1_spinta", "spinta.json")
    if folder != case_root and os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def fascia_pass(derived: str, folder: str, stator_on: bool, skip_extras: bool, prev=None):
    """One venturi + fan pass; returns (row without the update, risultati dict, report dict).

    prev = (dp, D) of the previous venturi: when the venturi gives the same duct again (the
    final pass with the extras) the fan is not repeated.
    """
    from sistema_designer.fascia import band_need
    venturi_dir = os.path.join(folder, "2_venturi")
    rc = run_venturi(derived, venturi_dir, skip_extras)
    if rc != 0:
        raise RuntimeError(f"venturi failed (code {rc})")
    res = _read_json(venturi_dir, "00_sintesi", "risultati.json")
    dp, D = res["ventola"]["dp_disk_Pa"], res["ventola"]["D_ventola_m"]
    reused = bool(prev) and abs(dp - prev[0]) <= 1e-6 * abs(prev[0]) and abs(D - prev[1]) <= 1e-9
    if not reused:
        rc = run_ventola(derived, folder)
        if rc != 0:
            raise RuntimeError(f"fan failed (code {rc})")
    rep = _read_json(folder, "3_ventola", "00_sintesi", "report.json")
    if not rep or not rep.get("best"):
        raise RuntimeError("the fan step found no accepted design")
    need = band_need(rep, res, stator_on, os.path.join(folder, "3_ventola", "03_cad"))
    return dict(skip_extras=skip_extras, ventola_riusata=reused, dp_Pa=dp,
                L_tubo_mm=res["geometria"]["L_tubo_mm"], D_ventola_mm=1e3 * D,
                monte_m=need["monte_m"], valle_m=need["valle_m"],
                fonte_ingombro=need["fonte"]), res, rep


def fascia_loop(input_file: str, case_root: str, folder: str, label, stator, sis: dict) -> int:
    """Venturi + fan repeated until L_disk fits the real fan. 0 = done, else failing code."""
    from sistema_designer.fascia import update_band, write_json
    from spinta_designer import caso
    inputs = caso.load_input(input_file)
    V, F = inputs["VENTURI"], {**FAN_DEFAULTS, **inputs["VENTOLA"]}
    stator_on = bool(stator) if stator is not None else bool(
        {**FAN_DEFAULTS["statore"], **F["statore"]}["presente"])
    T = thrust_value(inputs, case_root)
    L, L_max = float(V["L_disk"]), float(V["L_max"])
    n_max = max(1, int(sis["iterazioni_fascia"]))
    name = label or "case"
    rows, prev, it = [], None, 0
    path = os.path.join(folder, "fascia.json")
    prepare_chain(case_root, folder)

    def record(row, upd, n, L_used):
        row.update(iterazione=n, L_disk_m=L_used, L_disk_nuovo_m=upd["L_disk_nuovo_m"],
                   convergito=upd["convergito"], tagliato=upd["tagliato"])
        rows.append(row)
        write_json(path, rows)

    def fail(e, n, L_used):
        print(f"Error in chain {name}: {e}")
        rows.append(dict(iterazione=n, L_disk_m=L_used, errore=str(e)))
        write_json(path, rows)
        return 1

    while True:
        it += 1
        last = it >= n_max
        print(f"\n--- {name}: band pass {it}/{n_max}, L_disk = {1e3 * L:.2f} mm"
              f"{'' if last else ' (venturi without alternatives/exit scan)'} ---")
        derived = write_chain_input(input_file, folder, name, L, T, stator)
        try:
            row, res, _ = fascia_pass(derived, folder, stator_on, not last)
        except (RuntimeError, ValueError, KeyError) as e:
            return fail(e, it, L)
        upd = update_band(L, row, F["margine_fascia_m"], F["fascia_min_m"], L_max)
        record(row, upd, it, L)
        prev = (row["dp_Pa"], row["D_ventola_mm"] * 1e-3)
        print(f"  need upstream {1e3 * row['monte_m']:.2f} mm, downstream {1e3 * row['valle_m']:.2f} mm "
              f"-> L_disk {1e3 * upd['L_disk_nuovo_m']:.2f} mm"
              f"{' (cut to L_max/4)' if upd['tagliato'] else ''}")
        if upd["convergito"] and row["skip_extras"]:
            # converged on a pass without alternatives/exit scan: venturi again, with them
            print("  band converged: final venturi pass with alternatives and exit scan")
            derived = write_chain_input(input_file, folder, name, L, T, stator)
            try:
                row, res, _ = fascia_pass(derived, folder, stator_on, False, prev)
            except (RuntimeError, ValueError, KeyError) as e:
                return fail(e, it + 1, L)
            upd = update_band(L, row, F["margine_fascia_m"], F["fascia_min_m"], L_max)
            record(row, upd, it + 1, L)
            last = True
        if last or upd["convergito"]:
            if not upd["convergito"]:
                print(f"WARNING chain {name}: band NOT converged after {it} passes "
                      f"(L_disk {1e3 * L:.2f} mm, would be {1e3 * upd['L_disk_nuovo_m']:.2f} mm); "
                      "results kept.")
            return 0
        L = upd["L_disk_nuovo_m"]


def run_chain(input_file: str, case_root: str, folder: str, label, stator, sis: dict, only=None) -> int:
    """One chain: band loop (venturi + fan) and sistema; `only` = a single step, no loop."""
    from spinta_designer import caso
    name = label or "case"
    if only is None:
        rc = fascia_loop(input_file, case_root, folder, label, stator, sis)
        if rc != 0:
            return rc
        ventola_extras(folder)
        print(f"\n--- {name}: sistema ---")
        return run_sistema_step(os.path.join(folder, "input_usato.py"), folder)
    inputs = caso.load_input(input_file)
    rows = _read_json(folder, "fascia.json") or []
    ok = [r for r in rows if "errore" not in r]
    L = ok[-1]["L_disk_m"] if ok else float(inputs["VENTURI"]["L_disk"])
    prepare_chain(case_root, folder)
    derived = write_chain_input(input_file, folder, name, L, thrust_value(inputs, case_root), stator)
    if only == "venturi":
        return run_venturi(derived, os.path.join(folder, "2_venturi"))
    if only == "ventola":
        rc = run_ventola(derived, folder)
        if rc == 0:
            ventola_extras(folder)
        return rc
    return run_sistema_step(derived, folder)


def write_summary(input_file: str, results_dir=None) -> None:
    """RIEPILOGO.md of the case: the key numbers of the four steps on one page."""
    from spinta_designer import caso
    root = caso.case_dir(input_file, results_dir)
    # with the stator comparison the chains live in Statore/ and NoStatore/: the summary
    # follows Statore/ (the design with the stator) and points to the comparison
    sub = "Statore" if (load_sistema(input_file)["confronto_statore"]
                         and os.path.isdir(os.path.join(root, "Statore"))) else ""
    base = os.path.join(root, sub)
    pre = sub + "/" if sub else ""

    def load(*parts):
        path = os.path.join(root if parts[0] == "1_spinta" else base, *parts)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    s = load("1_spinta", "spinta.json")
    v = load("2_venturi", "00_sintesi", "risultati.json")
    f = load("3_ventola", "00_sintesi", "report.json")
    m = load("4_sistema", "00_sintesi", "potenza_manovra.json")
    cmp = load("4_sistema", "00_sintesi", "confronto_statore.json")
    curve = load("4_sistema", "00_sintesi", "curva_potenza.json")
    cpl = load("4_sistema", "04_cfd", "condotto_con_ventola.json")
    lines = [f"# Riepilogo del caso `{os.path.basename(root)}`", ""]
    if sub:
        lines += ["Il confronto statore sì/no ha due catene complete: questo riepilogo descrive "
                  "quella **con statore** (`Statore/`); quella senza è in `NoStatore/`.", ""]
    fascia = [r for r in (load("fascia.json") or []) if "errore" not in r]
    if fascia:
        last = fascia[-1]
        lines += [f"- fascia della ventola: L_disk {last['L_disk_m'] * 1e3:.2f} mm dopo "
                  f"{len(fascia)} passate, "
                  f"{'convergita' if last['convergito'] else '**NON convergita**'} "
                  f"(`{pre}fascia.json`)", ""]
    if m:
        lines += ["## In breve", "",
                  f"- **picco di potenza {m['picco_W']:.3f} W** all'albero per faccia "
                  f"({m['ugelli_per_faccia']} ugelli × {m['potenza_ugello_W']:.3f} W, {m['rpm']:.0f} rpm), "
                  f"durante accelerazione e frenata",
                  f"- energia della manovra {m['energia_manovra_J']:.2f} J, "
                  f"spinta per ugello {m['spinta_ugello_N']:.4g} N", ""]
    if s:
        lines += ["## 1. Spinta (`1_spinta/`)", "",
                  f"- {s['input']['distanza']:g} m in {s['input']['tempo']:g} s, "
                  f"{s['input']['massa']:g} kg, profilo `{s['input']['profilo']}`, "
                  f"disturbo residuo {s['input'].get('disturbo_residuo_g', 0.0):g} g",
                  f"- spinta della faccia {s['T_totale_N']:.4g} N, "
                  f"**per ugello {s['T_ugello_N']:.4g} N** ({s['input']['n_ugelli']} ugelli)", ""]
    if v:
        g, ve = v["geometria"], v["ventola"]
        lines += ["## 2. Condotto (`2_venturi/`, disco uniforme)", "",
                  f"- **Δp disco {ve['dp_disk_Pa']:.3f} ± {ve['dp_errore_Pa']:.3f} Pa**, "
                  f"portata {ve['portata_m3_s'] * 1e3:.3f} L/s, potenza all'aria "
                  f"{ve['potenza_fluido_W']:.4f} W",
                  f"- ventola Ø{ve['D_ventola_m'] * 1e3:.2f} mm; tubo "
                  f"{g['D_esterno_tubo_mm']:.1f} × {g['L_tubo_mm']:.1f} mm "
                  f"(ingombro {'rispettato' if g['ingombro_rispettato'] else 'NON rispettato'})",
                  f"- spinta {v['spinta']['calcolata_N']:.4g} N, di cui sul rotore "
                  f"{ve.get('spinta_rotore_N', float('nan')):.4g} N; studio di griglia "
                  f"{'affidabile' if v['spinta']['affidabile'] else 'NON affidabile'}", ""]
    if f:
        best = f.get("best")
        lines += ["## 3. Ventola (`3_ventola/`)", ""]
        if best:
            d, c = best["design"], best["cases"][0]
            lines += [f"- rotore {d['profile']}, {d['blade_count']} pale, mozzo "
                      f"{d['hub_diameter_m'] * 1e3:.1f} mm, {c['rpm']:.0f} rpm; corda "
                      f"{' → '.join(f'{x * 1e3:.1f}' for x in d['chord_m'])} mm, calettamento "
                      f"{' → '.join(f'{x:.0f}' for x in d['pitch_deg'])}° dalla radice alla punta",
                      f"- Δp assiale {c.get('axial_total_pressure_rise_Pa', float('nan')):.3f} Pa, "
                      f"**potenza all'albero {c['shaft_power_W']:.4f} W** per ugello, "
                      f"coppia {c['torque_Nm'] * 1e3:.3f} mN·m"]
            if c.get("stator_enabled"):
                lines += [f"- statore {c['stator_vanes']} pale: coppia netta {c['net_torque_Nm'] * 1e3:.3f} "
                          f"mN·m su {c['torque_Nm'] * 1e3:.3f} del rotore"]
            cad = f.get("cad") or {}
            if (cad.get("stator") or {}).get("avviso"):
                lines += [f"- **avviso CAD:** {cad['stator']['avviso']}"]
            if cad.get("errore"):
                lines += [f"- **CAD non scritto:** {cad['errore']}"]
            bl = load("3_ventola", "04_cfd", "strato_limite", "cp_manifest.json")
            if bl:
                for name, key in (("rotore", "sections"), ("statore", "stator_sections")):
                    sec = [x for x in bl["points"][0].get(key, []) if x.get("separation")]
                    if sec:
                        worst = min(x["separation"]["dorso"]["x_sep"] or 1.0 for x in sec)
                        lines += [f"- strato limite {name} (XFOIL): distacco sul dorso da x/c = "
                                  f"{worst:.2f} nella sezione peggiore"]
            tab = None
            try:                       # also for cases computed before the comparison existed
                from ventola_designer.indicatori import markdown_confronto, scrivi_confronto
                tab = scrivi_confronto(os.path.join(root, "3_ventola", "00_sintesi", "report.json"))
            except (OSError, ValueError, KeyError):
                pass
            if tab is not None:
                lines += [""] + markdown_confronto(tab, titolo="### Confronto per numero di pale")
                lines += ["Dettagli: `3_ventola/00_sintesi/CONFRONTO_PALE.md`."]
        else:
            lines += ["- nessun candidato accettato: vedi `3_ventola/00_sintesi/RISULTATO.md`"]
        lines += [""]
    if m or cmp or curve or cpl:
        lines += ["## 4. Sistema (`4_sistema/`)", ""]
        if curve:
            last = curve["righe"][-1]
            lines += [f"- curva di potenza: fino a {last['potenza_albero_W']:.3f} W per ugello la "
                      f"spinta arriva a {last['spinta_ugello_N']:.4g} N"]
        if cmp and "differenza_potenza_pct" in cmp:
            con, senza = [r for r in cmp["varianti"] if "errore" not in r]
            lines += [f"- con lo statore: {con['potenza_albero_W']:.3f} W e coppia netta "
                      f"{con['coppia_netta_Nm'] * 1e3:.3f} mN·m; senza: {senza['potenza_albero_W']:.3f} W e "
                      f"{senza['coppia_netta_Nm'] * 1e3:.3f} mN·m ({cmp['differenza_potenza_pct']:+.1f} % di potenza)"]
        if cpl:
            lines += [f"- condotto con la ventola vera: spinta {cpl['spinta_con_ventola_N']:.4g} N "
                      f"({cpl['scarto_spinta_pct']:+.1f} % sul disco uniforme), "
                      f"{cpl['celle_flusso_invertito']} celle con flusso invertito"]
        lines += ["- assieme CAD, viste 3D e ParaView (`04_cfd/sistema.pvd`): vedi "
                  "`4_sistema/00_sintesi/RISULTATO.md`", ""]
    if v and f and f.get("best") and "perdite" in v:
        c, pl = f["best"]["cases"][0], v["perdite"]
        q = c["volume_flow_m3_s"]
        rows = [("condotto: imbocco → disco", pl["imbocco_Pa"]),
                ("condotto: banda del disco", pl["disco_Pa"]),
                ("condotto: disco → uscita", pl["valle_Pa"]),
                ("ventola: attrito dei profili", c["profile_loss_power_W"] / q),
                *([("statore: attrito delle pale", c["stator_loss_power_W"] / q)]
                  if c.get("stator_enabled") else
                  [("ventola: swirl in uscita (senza statore)", c["swirl_power_W"] / q)])]
        total = sum(x for _, x in rows)
        lines += ["## Perdite di pressione totale", "",
                  "| dove | perdita [Pa] | potenza [W] |", "|---|---|---|",
                  *[f"| {name} | {x:.3f} | {x * q:.4f} |" for name, x in rows],
                  f"| **totale** | **{total:.3f}** | **{total * q:.4f}** |", "",
                  f"Potenza all'albero {c['shaft_power_W']:.4f} W, di cui utile al getto "
                  f"{c['shaft_power_W'] - total * q:.4f} W. Bocca d'imbocco non inclusa.", ""]
    extra = load("4_sistema", "00_sintesi", "note_e_limiti.json")
    if extra:
        from sistema_designer import note
        lines += note.markdown(extra)
    conf = None
    if sub:
        cpath = os.path.join(root, "5_confronto_statore", "confronto_statore.json")
        if os.path.isfile(cpath):
            with open(cpath, encoding="utf-8") as fh:
                conf = json.load(fh)
        lines += ["## Confronto con / senza statore", ""]
        if conf:
            lines += [f"- {x}" for x in (conf.get("sintesi") or [])[:6]]
        lines += ["Dettagli, bilancio di potenza e grafici: `5_confronto_statore/RISULTATO.md`.", ""]
    lines += [f"Dettagli: `1_spinta/RISULTATO.md`, `{pre}2_venturi/00_sintesi/RISULTATO.md`, "
              f"`{pre}3_ventola/00_sintesi/RISULTATO.md`, `{pre}4_sistema/00_sintesi/RISULTATO.md`.", ""]
    path = os.path.join(root, "RIEPILOGO.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\nSummary: {caso.shown(path)}")


def run_confronto(root: str) -> int:
    """5_confronto_statore/ from the two chains (what is missing is said in the report)."""
    from sistema_designer import confronto_varianti
    try:
        out = confronto_varianti.run(root)
    except Exception as e:             # the comparison never stops the chain
        print(f"Comparison failed: {e}")
        return 1
    print(f"Comparison: {out}")
    return 0


def run_case(input_file: str, solo=None, results_dir=None) -> int:
    """One case (a plain input.py, or one case of a series): the whole chain or one step.

    results_dir = folder that holds the case folder (default risultati/).
    """
    from spinta_designer import caso
    if solo == "riepilogo":
        write_summary(input_file, results_dir)
        return 0
    sis = load_sistema(input_file)
    if solo == "masse":
        write_masses(caso.case_dir(input_file, results_dir), sis)
        return 0
    if solo == "confronto":
        if not sis["confronto_statore"]:
            print("SISTEMA['confronto_statore'] is False: nothing to compare.")
            return 1
        rc = run_confronto(caso.case_dir(input_file, results_dir))
        write_summary(input_file, results_dir)
        return rc
    args = argparse.Namespace(input=input_file, solo=solo)
    if args.solo in (None, "spinta"):
        print("\n" + "#" * 66 + "\n#  SPINTA\n" + "#" * 66)
        rc = run_spinta(args.input, results_dir)
        if rc not in (0, 3):
            print(f"\nStep 'spinta' failed (code {rc}): chain stopped.")
            write_summary(args.input, results_dir)
            return rc
    if args.solo != "spinta":
        root = caso.case_dir(args.input, results_dir)
        results = []
        for label, folder, stator in chains(root, sis):
            print("\n" + "#" * 66 + f"\n#  CHAIN {label or 'CASE'}"
                  + (f" (stator {'yes' if stator else 'no'})" if label else "") + "\n" + "#" * 66)
            try:
                rc = run_chain(args.input, root, folder, label, stator, sis, args.solo)
            except ValueError as e:
                print(f"Error: {e}")
                rc = 1
            if rc not in (0, 3):
                print(f"\nChain {label or 'case'} failed (code {rc}).")
            results.append(rc)
        if sis["confronto_statore"] and args.solo is None:
            print("\n" + "#" * 66 + "\n#  CONFRONTO STATORE\n" + "#" * 66)
            run_confronto(root)
        write_summary(args.input, results_dir)
        if args.solo in (None, "sistema"):
            write_masses(root, sis)
        ok = [rc for rc in results if rc in (0, 3)]
        if not ok:
            return results[0] if results else 1
        return 0 if len(ok) == len(results) and 3 not in ok else 3
    write_summary(args.input, results_dir)
    return 0


def run_series(input_file: str, plan: dict, solo=None) -> int:
    """Every case of the series as a complete chain in plan['root']/<label>/; none stops the others."""
    rows = []
    for i, c in enumerate(plan["cases"], 1):
        print("\n" + "=" * 66 + f"\n=  CASE {i}/{len(plan['cases'])}: {c['label']}\n" + "=" * 66)
        rc = 1
        try:
            case_input = write_case_input(input_file, c["folder"], c["label"], plan["axes"], c["combo"])
            rc = run_case(case_input, solo, plan["root"])
        except Exception as e:             # a failing case is recorded, the series goes on
            print(f"Case {c['label']} failed: {e}")
            traceback.print_exc()
            rc = 1
        if rc not in (0, 3):
            print(f"\nCase {c['label']} failed (code {rc}).")
        rows.append(dict(label=c["label"], folder=c["folder"], rc=rc))
        write_series_summary_md(plan, rows + [dict(label=x["label"], folder=x["folder"], rc=None)
                                              for x in plan["cases"][i:]])
    path = write_series_summary_md(plan, rows)
    if solo in (None, "sistema", "masse"):
        sis = {**SISTEMA_DEFAULTS, **plan["raw"].get("SISTEMA", {})}
        first = next((r for r in rows if r["rc"] in (0, 3)), None)
        if first is not None:       # density and filling of the first finished case (they may vary)
            sis = load_sistema(os.path.join(first["folder"], "input_caso.py"))
        write_series_masses(plan, rows, sis)
    print(f"\nSeries summary: {path}")
    ok = [r["rc"] for r in rows if r["rc"] in (0, 3)]
    if not ok:
        return rows[0]["rc"] if rows else 1
    return 0 if len(ok) == len(rows) and 3 not in ok else 3


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Propulsion sizing chain.")
    p.add_argument("--solo", choices=SOLO, default=None,
                   help="Run one step only (in every chain and every case, no band loop); "
                        "'confronto' rewrites 5_confronto_statore/, 'riepilogo' RIEPILOGO.md and "
                        "'masse' the mass workbooks, all without calculating.")
    p.add_argument("--elenca", action="store_true",
                   help="Print the cases of the series (input values 'a; b') and their labels; run nothing.")
    p.add_argument("--input", default=INPUT_FILE, help="Input file (default: input.py).")
    args = p.parse_args(argv)

    try:
        plan = plan_series(args.input)
    except (ValueError, KeyError) as e:
        print(f"Error: {e}")
        return 1
    if args.elenca:
        if plan["axes"]:
            print("\n".join(describe_series(plan)))
        else:
            print("No key with several values: a single case.")
        return 0
    if plan["axes"]:
        sis = {**SISTEMA_DEFAULTS, **plan["raw"].get("SISTEMA", {})}
        if sis["confronto_statore"] and any(a[1][-2:] == ("statore", "presente") for a in plan["axes"]):
            print("WARNING: SISTEMA['confronto_statore'] is True: the stator flag of each chain "
                  "overrides VENTOLA['statore']['presente'] of the series.")
        print("\n".join(describe_series(plan)))
        return run_series(args.input, plan, args.solo)
    try:
        return run_case(args.input, args.solo)
    except ValueError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
