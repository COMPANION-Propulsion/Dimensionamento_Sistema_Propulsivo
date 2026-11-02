"""Genera tabelle NeuralFoil/AeroSandbox dalle coordinate del generatore locale."""
import importlib.metadata
import json
from pathlib import Path
import numpy as np
import aerosandbox as asb
from .config import load_catalog
from .geometry import naca4
from .polars import coordinate_hash


def main():
    output = Path(__file__).parent / "airfoils" / "polars_neuralfoil"
    output.mkdir(exist_ok=True)
    re = [5000,10000,20000,30000,50000,75000,100000,150000]
    mach = [0.0,0.1,0.2,0.3,0.45,0.5]
    alpha = np.arange(-12,24.01,0.5)
    versions = {p:importlib.metadata.version(p) for p in ("neuralfoil","aerosandbox","numpy","scipy")}
    for profile in load_catalog():
        coordinates = naca4(profile)
        airfoil = asb.Airfoil(name=profile, coordinates=np.array(coordinates))
        normalized = airfoil.normalize()
        fitted = normalized.to_kulfan_airfoil(n_weights_per_side=8, normalize_coordinates=False)
        fit_errors = []
        for original, evaluator in ((normalized.upper_coordinates(), fitted.upper_coordinates),
                                    (normalized.lower_coordinates(), fitted.lower_coordinates)):
            x = np.clip(original[:,0], 0, 1)
            fit_errors.extend((evaluator(x)[:,1]-original[:,1]).tolist())
        fit_error = {"metric":"vertical_difference_at_normalized_input_coordinates",
                     "max_abs_fraction_chord":float(np.max(np.abs(fit_errors))),
                     "rms_fraction_chord":float(np.sqrt(np.mean(np.square(fit_errors))))}
        fields = {k:[] for k in ("cl","cd","confidence")}
        for reynolds in re:
            planes = {k:[] for k in fields}
            for m in mach:
                aero = airfoil.get_aero_from_neuralfoil(alpha=alpha, Re=reynolds, mach=m, n_crit=9, model_size="xlarge")
                for key, source in (("cl","CL"),("cd","CD"),("confidence","analysis_confidence")):
                    planes[key].append(np.asarray(aero[source], dtype=float).reshape(-1).tolist())
            for k in fields:
                fields[k].append(planes[k])
        data = {"schema_version":1,"profile":profile,"reynolds":re,"mach":mach,
                "alpha_deg":alpha.tolist(),"coordinates_sha256":coordinate_hash(coordinates),
                "coordinates":coordinates,"versions":versions,"n_crit":9,"model_size":"xlarge",
                "source":"https://github.com/peterdsharpe/NeuralFoil",
                "method":"NeuralFoil via AeroSandbox with Kulfan fit and compressibility corrections",
                "kulfan_fit_error":fit_error,
                "experimental_validation":False,
                "confidence_note":"Model confidence is not experimental uncertainty. Threshold 0.5 is a project screening policy.",**fields}
        (output/f"{profile}.json").write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
        (output/f"{profile}.dat").write_text(profile+"\n"+"\n".join(f"{x:.12g} {y:.12g}" for x,y in coordinates)+"\n",encoding="ascii")
        print(f"{profile}: {len(re)*len(mach)*len(alpha)} punti numerici",flush=True)


if __name__ == "__main__":
    main()
