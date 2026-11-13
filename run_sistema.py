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
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(ROOT, "input.py")
for folder in ("0_spinta", "1_venturi", "2_ventola", "3_sistema"):
    sys.path.insert(0, os.path.join(ROOT, folder))

STEPS = ("spinta", "venturi", "ventola", "sistema")
SOLO = STEPS + ("confronto", "riepilogo")
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
SISTEMA_DEFAULTS = {"confronto_statore": False, "iterazioni_fascia": 3}
VARIANTS = (("Statore", True), ("NoStatore", False))


def run_spinta(input_file: str) -> int:
    from spinta_designer import run
    return run(input_file)


def load_sistema(input_file: str) -> dict:
    """SISTEMA of the input file (defaults for a missing dictionary or key)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("project_input_sistema", input_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    given = dict(getattr(module, "SISTEMA", None) or {})
    unknown = sorted(set(given) - set(SISTEMA_DEFAULTS))
    if unknown:
        raise ValueError(f"Unknown keys in SISTEMA: {', '.join(unknown)}.")
    return {**SISTEMA_DEFAULTS, **given}


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


def write_summary(input_file: str) -> None:
    """RIEPILOGO.md of the case: the key numbers of the four steps on one page."""
    from spinta_designer import caso
    root = caso.case_dir(input_file)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Propulsion sizing chain.")
    p.add_argument("--solo", choices=SOLO, default=None,
                   help="Run one step only (in every chain, no band loop); 'confronto' rewrites "
                        "5_confronto_statore/ and 'riepilogo' RIEPILOGO.md, both without calculating.")
    p.add_argument("--input", default=INPUT_FILE, help="Input file (default: input.py).")
    args = p.parse_args(argv)

    if args.solo == "riepilogo":
        write_summary(args.input)
        return 0
    from spinta_designer import caso
    try:
        sis = load_sistema(args.input)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    if args.solo == "confronto":
        if not sis["confronto_statore"]:
            print("SISTEMA['confronto_statore'] is False: nothing to compare.")
            return 1
        rc = run_confronto(caso.case_dir(args.input))
        write_summary(args.input)
        return rc
    if args.solo in (None, "spinta"):
        print("\n" + "#" * 66 + "\n#  SPINTA\n" + "#" * 66)
        rc = run_spinta(args.input)
        if rc not in (0, 3):
            print(f"\nStep 'spinta' failed (code {rc}): chain stopped.")
            write_summary(args.input)
            return rc
    if args.solo != "spinta":
        root = caso.case_dir(args.input)
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
        write_summary(args.input)
        ok = [rc for rc in results if rc in (0, 3)]
        if not ok:
            return results[0] if results else 1
        return 0 if len(ok) == len(results) and 3 not in ok else 3
    write_summary(args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
