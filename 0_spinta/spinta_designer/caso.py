"""
caso.py
=======
Where the results of a case go, shared by every module of the project.

All the outputs live in one folder at the project root:

    risultati/<nome_caso>/
        caso.json, input_usato.py
        1_spinta/  2_venturi/  3_ventola/  4_sistema/

The case name is CASO["nome"] of input.py, or, when that is None, a name
built from the inputs that identify the case plus a short hash of all the
inputs, so two different cases never share a folder.

The other modules load this file by path (it is not on their import path):

    spec = importlib.util.spec_from_file_location("caso", CASO_FILE)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from typing import Dict, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INPUT_FILE = os.path.join(ROOT, "input.py")
RESULTS_DIR = os.path.join(ROOT, "risultati")
STEP_DIRS = {"spinta": "1_spinta", "venturi": "2_venturi", "ventola": "3_ventola",
             "sistema": "4_sistema"}
HASHED = ("SPINTA", "VENTURI")      # dictionaries that define the case


def load_input(path: str = INPUT_FILE) -> Dict[str, dict]:
    """The dictionaries of input.py (CASO, SPINTA, VENTURI, VENTOLA), missing ones empty.

    VENTOLA is not in the hash: the fan settings do not change spinta and venturi,
    so a new fan search reuses the case and rewrites only 3_ventola/.
    """
    spec = importlib.util.spec_from_file_location("project_input", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: dict(getattr(module, name, None) or {})
            for name in ("CASO",) + HASHED + ("VENTOLA",)}


def input_hash(inputs: Dict[str, dict]) -> str:
    """Short hash of every value that defines the case."""
    text = json.dumps({k: inputs.get(k, {}) for k in HASHED}, sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]


def _g(x: float) -> str:
    return f"{x:g}".replace(".", "p")


def automatic_name(inputs: Dict[str, dict]) -> str:
    """Readable name from the main inputs, plus the hash of all of them."""
    s, v = inputs.get("SPINTA", {}), inputs.get("VENTURI", {})
    parts = []
    if s:
        parts.append(f"m{_g(s['massa'])}kg_s{_g(s['distanza'])}m_t{_g(s['tempo'])}s"
                     f"_n{s['n_ugelli']}_{s.get('profilo', 'bang_bang').replace('_', '')}")
    if v.get("D_ext_max") and v.get("L_max"):
        parts.append(f"D{_g(v['D_ext_max'] * 1e3)}xL{_g(v['L_max'] * 1e3)}mm")
    parts.append("h" + input_hash(inputs))
    return "_".join(parts)


def case_name(inputs: Dict[str, dict]) -> str:
    name = inputs.get("CASO", {}).get("nome")
    if name is None:
        return automatic_name(inputs)
    name = str(name).strip()
    if not name or any(c in name for c in '<>:"/\\|?*'):
        raise ValueError(f"CASO['nome'] = {name!r} is not a valid folder name.")
    return name


def case_dir(path: str = INPUT_FILE, results_dir: Optional[str] = None) -> str:
    """Folder of the case of input.py, created and stamped if new.

    A folder that already holds a case with different inputs is refused,
    unless CASO["sovrascrivi"] is True.
    """
    inputs = load_input(path)
    root = os.path.join(results_dir or RESULTS_DIR, case_name(inputs))
    stamp = os.path.join(root, "caso.json")
    h = input_hash(inputs)
    if os.path.isfile(stamp):
        with open(stamp, encoding="utf-8") as fh:
            old = json.load(fh).get("hash")
        if old != h and not inputs.get("CASO", {}).get("sovrascrivi", False):
            raise ValueError(
                f"{root} holds a case with other inputs (hash {old}, now {h}). Change "
                f"CASO['nome'], set it to None for an automatic name, or set "
                f"CASO['sovrascrivi'] = True.")
        if old != h:
            stale = [d for d in STEP_DIRS.values()
                     if d != STEP_DIRS["spinta"] and os.path.isdir(os.path.join(root, d))]
            if stale:
                print(f"WARNING: {root} held a case with other inputs (hash {old}, now {h}). "
                      f"These steps were computed with the old inputs and must be rerun: "
                      f"{', '.join(stale)}.")
    os.makedirs(root, exist_ok=True)
    with open(stamp, "w", encoding="utf-8") as fh:
        json.dump(dict(nome=os.path.basename(root), hash=h,
                       **{k: inputs[k] for k in HASHED}), fh, indent=1, default=str)
    shutil.copyfile(path, os.path.join(root, "input_usato.py"))
    return root


def step_dir(step: str, path: str = INPUT_FILE, results_dir: Optional[str] = None) -> str:
    """Folder of one step ("spinta", "venturi", "ventola") of the case."""
    out = os.path.join(case_dir(path, results_dir), STEP_DIRS[step])
    os.makedirs(out, exist_ok=True)
    return out


def shown(path: str) -> str:
    """Path relative to the project root when it is inside it."""
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:       # another drive on Windows
        return path
    return path if rel.startswith("..") else rel


def thrust_file(path: str = INPUT_FILE, results_dir: Optional[str] = None) -> str:
    """spinta.json of the case: the thrust the venturi has to give."""
    return os.path.join(step_dir("spinta", path, results_dir), "spinta.json")
