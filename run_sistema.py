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

Each step writes only what is its own: what needs both duct and fan is in 4_sistema/.
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
for folder in ("0_spinta", "1_venturi", "2_ventola", "3_sistema"):
    sys.path.insert(0, os.path.join(ROOT, folder))

STEPS = ("spinta", "venturi", "ventola", "sistema")
FAN_DEFAULTS = {
    "temperatura_K": 293.15, "mozzo_su_D": [0.15, 0.25],
    "statore": {"presente": True, "pale": None, "solidita": 1.0, "profilo": "NACA4412",
                "gioco_assiale_m": 0.002},
    "giri_min_max_rpm": [5000.0, 30000.0], "calettamento_min_max_deg": [0.0, 75.0],
    "corda_su_D_min_max": [0.04, 0.22],
    "pale_candidate": [2, 3, 4, 5, 6, 7, 8], "nodi_pala": 2,
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


def run_ventola(input_file: str) -> int:
    """Fan sizing (rotor + stator + CAD), then the boundary layer of its sections."""
    from spinta_designer import caso
    from ventola_designer.optimizer import main as size_main
    try:
        path = fan_input(input_file)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    jobs = caso.load_input(input_file)["VENTOLA"].get("jobs")
    print(f"Fan input: {caso.shown(path)}")
    try:
        rc = size_main(["--input", path] + (["--jobs", str(jobs)] if jobs else []))
    except SystemExit as e:            # argparse errors of the fan command line
        return int(e.code or 1)
    if rc != 0:
        return rc
    fan_dir = os.path.join(caso.case_dir(input_file), caso.STEP_DIRS["ventola"])
    print("\nBoundary layer of rotor and stator sections (XFOIL)")
    try:                               # analysis only: the sizing results stay valid
        from ventola_designer.cp_map import export_cp
        export_cp(os.path.join(fan_dir, "00_sintesi", "report.json"),
                  os.path.join(ROOT, "2_ventola", "tools", "xfoil", "dist", "xfoil.exe"), 17)
    except (OSError, ValueError) as e:
        print(f"  skipped: {e}")
    return 0


def run_sistema_step(input_file: str) -> int:
    """Duct and fan together: everything that needs both, in 4_sistema/."""
    from spinta_designer import caso
    from sistema_designer import run
    root = caso.case_dir(input_file)
    fan_report = os.path.join(root, caso.STEP_DIRS["ventola"], "00_sintesi", "report.json")
    if not os.path.isfile(fan_report):
        print("Error: no fan in this case: run the fan step first.")
        return 1
    with open(fan_report, encoding="utf-8") as fh:
        if not json.load(fh).get("best"):
            print("Error: the fan step found no accepted design: nothing to put together.")
            return 2
    log = run(root, caso.load_input(input_file)["VENTOLA"].get("potenza_max_W"))
    return 0 if not log.get("errori") else 3


def write_summary(input_file: str) -> None:
    """RIEPILOGO.md of the case: the key numbers of the four steps on one page."""
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
    m = load("4_sistema", "00_sintesi", "potenza_manovra.json")
    cmp = load("4_sistema", "00_sintesi", "confronto_statore.json")
    curve = load("4_sistema", "00_sintesi", "curva_potenza.json")
    cpl = load("4_sistema", "04_cfd", "condotto_con_ventola.json")
    lines = [f"# Riepilogo del caso `{os.path.basename(root)}`", ""]
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
    lines += ["Dettagli: `1_spinta/RISULTATO.md`, `2_venturi/00_sintesi/RISULTATO.md`, "
              "`3_ventola/00_sintesi/RISULTATO.md`, `4_sistema/00_sintesi/RISULTATO.md`.", ""]
    path = os.path.join(root, "RIEPILOGO.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\nSummary: {caso.shown(path)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Propulsion sizing chain.")
    p.add_argument("--solo", choices=STEPS, default=None, help="Run one step only.")
    p.add_argument("--input", default=INPUT_FILE, help="Input file (default: input.py).")
    args = p.parse_args(argv)

    run = {"spinta": run_spinta, "venturi": run_venturi, "ventola": run_ventola,
           "sistema": run_sistema_step}
    for step in STEPS:
        if args.solo not in (None, step):
            continue
        print("\n" + "#" * 66 + f"\n#  {step.upper()}\n" + "#" * 66)
        rc = run[step](args.input)
        if rc not in (0, 3):           # 3: done, with warnings in the RISULTATO.md of the step
            print(f"\nStep '{step}' failed (code {rc}): chain stopped.")
            write_summary(args.input)
            return rc
    write_summary(args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
