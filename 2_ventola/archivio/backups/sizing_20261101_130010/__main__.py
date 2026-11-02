"""Avvio: python -m ventola_designer --input input_esempio.json."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
from .config import load_case, load_catalog
from .geometry import blade_sections, initial_design
from .export import export_geometry


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera una geometria iniziale della ventola (non ottimizzata).")
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "input_esempio.json")
    parser.add_argument("--output", type=Path, help="Nuova cartella risultati; deve essere vuota o non esistere.")
    parser.add_argument("--profile", default=None, help="Profilo del seme geometrico; default primo candidato del caso.")
    parser.add_argument("--blades", type=int, default=None, help="Pale del seme; default primo candidato del caso.")
    parser.add_argument("--validate-only", action="store_true", help="Controlla solo la struttura del caso.")
    args = parser.parse_args(argv)
    try:
        case = load_case(args.input)
        if args.validate_only:
            print(f"Input valido: {len(case['operating_points'])} punti operativi. Nessun calcolo aerodinamico.")
            return 0
        rotor = case["rotor"]
        profile = args.profile if args.profile is not None else rotor["airfoil_candidates"][0]
        blades = args.blades if args.blades is not None else rotor["blade_count_candidates"][0]
        design = initial_design(case, profile, blades)
        sections = blade_sections(design)
        out = args.output or args.input.resolve().parent / "ventola_output" / datetime.now().strftime("geometry_%Y%m%d_%H%M%S_%f")
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            raise ValueError("La cartella risultati esiste e non è vuota: scegliere un nuovo percorso.")
        export_geometry(out, case, design, sections, load_catalog())
        print(f"Geometria iniziale generata: {profile}, {blades} pale.")
        print(f"Risultati: {out.resolve()}")
        print("Stato: NON OTTIMIZZATA. Polari, BEMT e ottimizzazione ancora da implementare.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
