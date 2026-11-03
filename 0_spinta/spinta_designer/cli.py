"""Command line of the thrust step: input.py -> risultati/<caso>/1_spinta/."""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from typing import Optional

from . import caso
from .export import export_all
from .profilo import Motion

REQUIRED = ("distanza", "tempo", "massa", "n_ugelli")


def load_motion(path: str = caso.INPUT_FILE) -> Motion:
    s = caso.load_input(path)["SPINTA"]
    if not s:
        raise ValueError(f"{path} does not define the SPINTA dictionary.")
    missing = [k for k in REQUIRED if s.get(k) is None]
    if missing:
        raise ValueError(f"Missing in SPINTA of {path}: {', '.join(missing)}.")
    names = {f.name for f in fields(Motion)}
    unknown = sorted(set(s) - names)
    if unknown:
        raise ValueError(f"Unknown keys in SPINTA: {', '.join(unknown)}.")
    return Motion(**s)


def run(input_file: str = caso.INPUT_FILE, results_dir: Optional[str] = None) -> int:
    try:
        m = load_motion(input_file)
        out = caso.step_dir("spinta", input_file, results_dir)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    s = m.summary()
    print(f"Profilo {m.profilo}: a = {s['accelerazione_m_s2']:.5g} m/s^2, "
          f"v_max = {s['v_max_m_s']:.4g} m/s")
    print(f"Spinta della faccia {s['T_totale_N']:.5g} N, "
          f"per ugello {s['T_ugello_N']:.5g} N ({m.n_ugelli} ugelli)")
    for f in export_all(m, out):
        print(f"  written {caso.shown(f)}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="spinta", description=(
        "Thrust per nozzle to cover a distance in a given time (SPINTA of input.py)."))
    p.add_argument("--input", default=caso.INPUT_FILE, help="Input file (default: input.py at the root).")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    return run(args.input)
