"""
run_sistema.py
==============
Whole chain of the propulsion sizing, from input.py to risultati/<caso>/ (DRAFT).

    1. 0_spinta    mission -> thrust per nozzle          -> 1_spinta/spinta.json
    2. 1_venturi   thrust, size -> duct, fan dp and size -> 2_venturi/00_sintesi/risultati.json
    3. 2_ventola   NOT LINKED YET: it still reads its own input file. The values it
                   will take (dp, diameter, flow rate) are in risultati.json above.

    python run_sistema.py                 the whole chain
    python run_sistema.py --solo spinta   one step only (spinta | venturi)
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(ROOT, "input.py")
for folder in ("0_spinta", "1_venturi"):
    sys.path.insert(0, os.path.join(ROOT, folder))

STEPS = ("spinta", "venturi")


def run_spinta(input_file: str) -> int:
    from spinta_designer import run
    return run(input_file)


def run_venturi(input_file: str) -> int:
    from venturi_designer.cli import run_target_thrust
    return run_target_thrust(argparse.Namespace(input=input_file, output_dir=None,
                                                no_export=False))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Propulsion sizing chain (draft).")
    p.add_argument("--solo", choices=STEPS, default=None, help="Run one step only.")
    p.add_argument("--input", default=INPUT_FILE, help="Input file (default: input.py).")
    args = p.parse_args(argv)

    for step in STEPS:
        if args.solo not in (None, step):
            continue
        print("\n" + "#" * 66 + f"\n#  {step.upper()}\n" + "#" * 66)
        rc = {"spinta": run_spinta, "venturi": run_venturi}[step](args.input)
        if rc not in (0, 3):           # 3: venturi done, with warnings in RISULTATO.md
            print(f"\nStep '{step}' failed (code {rc}): chain stopped.")
            return rc
    if args.solo is None:
        print("\n2_ventola: link still to do. The fan inputs (dp, diameter, flow rate) are in "
              "risultati/<caso>/2_venturi/00_sintesi/risultati.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
