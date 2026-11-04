"""
run_sistema.py
==============
Whole chain of the propulsion sizing, from input.py to risultati/<caso>/.

    1. 0_spinta    mission -> thrust per nozzle            -> 1_spinta/spinta.json
    2. 1_venturi   thrust, size -> duct, fan dp and size   -> 2_venturi/00_sintesi/risultati.json
    3. 2_ventola   dp, diameter, flow rate -> blades, rpm  -> 3_ventola/00_sintesi/report.json
                   then thrust against shaft power, 0..P_max -> 3_ventola/.../curva_potenza.*
    4. summary of the three steps                          -> RIEPILOGO.md

    python run_sistema.py                 the whole chain
    python run_sistema.py --solo ventola  one step only (spinta | venturi | ventola)

The fan input is written from VENTOLA of input.py into risultati/<caso>/input_ventola.json,
with the explicit path of the venturi of THIS case (never "the latest one").
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(ROOT, "input.py")
for folder in ("0_spinta", "1_venturi", "2_ventola"):
    sys.path.insert(0, os.path.join(ROOT, folder))

STEPS = ("spinta", "venturi", "ventola")
FAN_DEFAULTS = {
    "temperatura_K": 293.15, "mozzo_min_max_m": [0.012, 0.024],
    "giri_min_max_rpm": [5000.0, 30000.0], "pale_candidate": [2, 3, 4, 5, 6, 7, 8],
    "profili_candidati": ["NACA0012", "NACA2412", "NACA4412", "NACA4415"],
    "durata_s": 1.0, "gioco_punta_m": 0.0005, "potenza_max_W": None, "jobs": None, "sizing": {},
}


def run_spinta(input_file: str) -> int:
    from spinta_designer import run
    return run(input_file)


def run_venturi(input_file: str) -> int:
    from venturi_designer.cli import run_target_thrust
    return run_target_thrust(argparse.Namespace(input=input_file, output_dir=None,
                                                no_export=False))


def fan_input(input_file: str) -> str:
    """Write the fan input of the case and return its path."""
    from spinta_designer import caso
    inputs = caso.load_input(input_file)
    v = {**FAN_DEFAULTS, **inputs["VENTOLA"]}
    unknown = sorted(set(inputs["VENTOLA"]) - set(FAN_DEFAULTS))
    if unknown:
        raise ValueError(f"Unknown keys in VENTOLA: {', '.join(unknown)}.")
    root = caso.case_dir(input_file)
    venturi = os.path.join(root, caso.STEP_DIRS["venturi"], "00_sintesi", "risultati.json")
    if not os.path.isfile(venturi):
        raise ValueError(f"{caso.shown(venturi)} not found: run the venturi step first.")
    data = {
        "description": "Written by run_sistema.py from VENTOLA of input.py.",
        "design_mode": "pressure_flow",
        "velocity_reference": "full_disk_flow",
        "air": {"temperature_K": v["temperatura_K"],
                "static_pressure_Pa": inputs["VENTURI"].get("p_amb", 101325.0),
                "relative_humidity": None},
        "rotor": {"hub_diameter_bounds_m": list(v["mozzo_min_max_m"]),
                  "blade_count_candidates": list(v["pale_candidate"]),
                  "airfoil_candidates": list(v["profili_candidati"]),
                  "profile_constant_along_span": True,
                  "shaft_speed_bounds_rpm": list(v["giri_min_max_rpm"])},
        "operating_points": [{"name": "venturi", "venturi_result": venturi,
                              "duration_s": v["durata_s"]}],
        "sizing": {"loss_model": "none", **v["sizing"]},
        "cad": {"tip_clearance_m": v["gioco_punta_m"]},
    }
    path = os.path.join(root, "input_ventola.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def run_ventola(input_file: str) -> int:
    from spinta_designer import caso
    from ventola_designer.optimizer import main as size_main
    try:
        path = fan_input(input_file)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    fan = caso.load_input(input_file)["VENTOLA"]
    jobs = fan.get("jobs")
    print(f"Fan input: {caso.shown(path)}")
    try:
        rc = size_main(["--input", path] + (["--jobs", str(jobs)] if jobs else []))
    except SystemExit as e:            # argparse errors of the fan command line
        return int(e.code or 1)
    if rc != 0:
        return rc
    from ventola_designer.power_curve import export_power_curve
    root = caso.case_dir(input_file)
    print("\nPower curve (fixed duct and blades, variable rpm)")
    try:
        curve = export_power_curve(os.path.join(root, caso.STEP_DIRS["ventola"]),
                                   os.path.join(root, caso.STEP_DIRS["venturi"], "00_sintesi",
                                                "risultati.json"), fan.get("potenza_max_W"))
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    last = curve["righe"][-1]
    print(f"  {len(curve['righe'])} points, up to {last['potenza_albero_W']:.3f} W -> "
          f"{last['spinta_ugello_N']:.4f} N")
    return 0


def write_summary(input_file: str) -> None:
    """RIEPILOGO.md of the case: the key numbers of the three steps on one page."""
    from spinta_designer import caso
    root = caso.case_dir(input_file)

    def load(*parts):
        path = os.path.join(root, *parts)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    s = load("1_spinta", "spinta.json")
    v = load("2_venturi", "00_sintesi", "risultati.json")
    f = load("3_ventola", "00_sintesi", "report.json")
    lines = [f"# Riepilogo del caso `{os.path.basename(root)}`", ""]
    if s:
        lines += ["## 1. Spinta", "",
                  f"- {s['input']['distanza']:g} m in {s['input']['tempo']:g} s, "
                  f"{s['input']['massa']:g} kg, profilo `{s['input']['profilo']}`",
                  f"- spinta della faccia {s['T_totale_N']:.4g} N, "
                  f"**per ugello {s['T_ugello_N']:.4g} N** ({s['input']['n_ugelli']} ugelli)", ""]
    if v:
        g, ve = v["geometria"], v["ventola"]
        lines += ["## 2. Condotto", "",
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
        lines += ["## 3. Ventola", ""]
        if best:
            d, c = best["design"], best["cases"][0]
            lines += [f"- {d['profile']}, {d['blade_count']} pale, mozzo "
                      f"{d['hub_diameter_m'] * 1e3:.1f} mm, {c['rpm']:.0f} rpm",
                      f"- Δp assiale {c.get('axial_total_pressure_rise_Pa', float('nan')):.3f} Pa "
                      f"(con swirl {c['total_pressure_rise_Pa']:.3f} Pa)",
                      f"- **potenza all'albero {c['shaft_power_W']:.4f} W**, rendimento "
                      f"{c['total_pressure_efficiency'] * 100:.1f} %, coppia {c['torque_Nm'] * 1e3:.3f} mN·m"]
            curve = load("3_ventola", "00_sintesi", "curva_potenza.json")
            if curve:
                last = curve["righe"][-1]
                lines += [f"- curva di potenza: fino a {last['potenza_albero_W']:.3f} W la spinta "
                          f"dell'ugello arriva a {last['spinta_ugello_N']:.4g} N "
                          f"(`3_ventola/01_grafici/curva_potenza.svg`)",
                          "- CAD: `3_ventola/03_cad/ventola_A` e `ventola_B_speculare` (STEP, STL), "
                          "per ugelli vicini controrotanti"]
        else:
            lines += ["- nessun candidato accettato: vedi `3_ventola/00_sintesi/RISULTATO.md`"]
        lines += [""]
    if v and f and f.get("best") and "perdite" in v:
        c, pl = f["best"]["cases"][0], v["perdite"]
        q = c["volume_flow_m3_s"]
        rows = [("condotto: imbocco → disco", pl["imbocco_Pa"]),
                ("condotto: banda del disco", pl["disco_Pa"]),
                ("condotto: disco → uscita", pl["valle_Pa"]),
                ("ventola: attrito dei profili", c["profile_loss_power_W"] / q),
                ("ventola: swirl in uscita (senza statore)", c["swirl_power_W"] / q)]
        total = sum(x for _, x in rows)
        lines += ["## Perdite di pressione totale", "",
                  "| dove | perdita [Pa] | potenza [W] |", "|---|---|---|",
                  *[f"| {name} | {x:.3f} | {x * q:.4f} |" for name, x in rows],
                  f"| **totale** | **{total:.3f}** | **{total * q:.4f}** |", "",
                  f"Potenza all'albero {c['shaft_power_W']:.4f} W, di cui utile al getto "
                  f"{c['shaft_power_W'] - total * q:.4f} W. Bocca d'imbocco non inclusa.", ""]
    lines += ["Dettagli: `1_spinta/RISULTATO.md`, `2_venturi/00_sintesi/RISULTATO.md`, "
              "`3_ventola/00_sintesi/RISULTATO.md`.", ""]
    path = os.path.join(root, "RIEPILOGO.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\nSummary: {caso.shown(path)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Propulsion sizing chain.")
    p.add_argument("--solo", choices=STEPS, default=None, help="Run one step only.")
    p.add_argument("--input", default=INPUT_FILE, help="Input file (default: input.py).")
    args = p.parse_args(argv)

    run = {"spinta": run_spinta, "venturi": run_venturi, "ventola": run_ventola}
    for step in STEPS:
        if args.solo not in (None, step):
            continue
        print("\n" + "#" * 66 + f"\n#  {step.upper()}\n" + "#" * 66)
        rc = run[step](args.input)
        if rc not in (0, 3):           # 3: venturi done, with warnings in RISULTATO.md
            print(f"\nStep '{step}' failed (code {rc}): chain stopped.")
            return rc
    write_summary(args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
