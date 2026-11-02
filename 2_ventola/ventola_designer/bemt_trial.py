"""Ripete la scansione NACA4412 con polari multi-Re coerenti con la geometria."""
import json
from pathlib import Path
from .bemt import ModelDomainError, solve
from .config import load_case
from .geometry import initial_design
from .polars import PolarGrid


def main():
    root = Path(__file__).resolve().parents[1]
    case = load_case(root / "input_esempio.json")
    polar = PolarGrid.load(Path(__file__).parent / "airfoils" / "polars_neuralfoil" / "NACA4412.json")
    found = []
    errors = {}
    examples = []
    for blades in range(2,9):
        print(f"NACA4412, {blades} pale...", flush=True)
        for rpm in (5000,10000,15000,20000,25000,30000):
            for root_angle in (10,14,18,22):
              for tip_angle in (4,8,12,16):
                design = initial_design(case,"NACA4412",blades)
                design["rpm"] = rpm
                design["pitch_deg"] = [root_angle+(tip_angle-root_angle)*s for s in design["span_nodes"]]
                try:
                    result = [solve(case,design,point,polar) for point in case["operating_points"]]
                    if all(r["thrust_rotor_N"] >= p["minimum_rotor_thrust_N"] for r,p in zip(result,case["operating_points"])):
                        energy = sum(r["shaft_power_W"]*p["duration_s"] for r,p in zip(result,case["operating_points"]))
                        found.append((energy,blades,rpm,root_angle,tip_angle,result))
                except ModelDomainError as exc:
                    errors[type(exc).__name__] = errors.get(type(exc).__name__,0)+1
                    if len(examples) < 8:
                        examples.append({"blades":blades,"rpm":rpm,"root_angle_deg":root_angle,"tip_angle_deg":tip_angle,"reason":str(exc)})
    report = {"method":"coarse_parameter_scan_not_SLSQP", "attempted":7*6*4*4,
              "rejected":errors,"rejection_examples":examples,
              "feasible_in_model":len(found),"best":None}
    if found:
        energy,blades,rpm,root_angle,tip_angle,results = min(found,key=lambda x:x[0])
        report["best"] = {"energy_J":energy,"blades":blades,"rpm":rpm,"root_angle_deg":root_angle,"tip_angle_deg":tip_angle,
                          "valid_for_design":False,
                          "reason":"Polari numeriche interpolate nel dominio; modello rotorico privo di validazione sperimentale e delle perdite di punta/mozzo.",
                          "polar_domain_covered":True,
                          "design":{**initial_design(case,"NACA4412",blades),"rpm":rpm,
                              "pitch_deg":[root_angle+(tip_angle-root_angle)*s for s in (0,.35,.7,1)]},
                          "cases":[{k:v for k,v in r.items() if k!="local"} for r in results]}
        finer = [solve(case,report["best"]["design"],p,polar,stations=64) for p in case["operating_points"]]
        report["radial_refinement_32_to_64"] = [
            {"thrust_change_fraction":fine["thrust_rotor_N"]/coarse["thrust_rotor_N"]-1,
             "power_change_fraction":fine["shaft_power_W"]/coarse["shaft_power_W"]-1,
             "fine":{k:v for k,v in fine.items() if k!="local"}}
            for coarse,fine in zip(results,finer)]
    previous = initial_design(case,"NACA4412",2)
    previous.update(rpm=10000,pitch_deg=[18-2*s for s in previous["span_nodes"]])
    try:
        report["previous_geometry_recomputed"] = [
            {k:v for k,v in solve(case,previous,p,polar).items() if k!="local"}
            for p in case["operating_points"]]
    except ModelDomainError as exc:
        report["previous_geometry_recomputed"] = {"rejected":str(exc)}
    report["polar_source"] = polar.data["source"]
    report["polar_conditions"] = {k:polar.data[k] for k in ("reynolds","mach","alpha_deg","n_crit","versions","coordinates_sha256","method","kulfan_fit_error")}
    report["warnings"] = ["Polari numeriche NeuralFoil/AeroSandbox, non dati sperimentali.",
        "Coordinate di input coincidenti con il generatore; approssimazione interna Kulfan quantificata nei metadati.",
        "Nessuna extrapolazione: controllati Reynolds, Mach, alpha e confidence >= 0.5.",
        "Perdite di punta/mozzo, condotto e cascata non modellati.",
        "axial_inlet_velocity_m_s interpretata come velocita lontano a monte, non sul disco.",
        "La scansione non e SLSQP e un rifiuto durante iterazione non dimostra assenza di soluzione."]
    out = root/"ventola_output"/"bemt_multire.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(report["best"] or {"feasible_in_model":0,"rejected":errors,"rejection_examples":examples[:3]},indent=2))
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
