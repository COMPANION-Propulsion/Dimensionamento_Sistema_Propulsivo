"""
target_thrust.py
================
From the thrust per nozzle to the pressure rise of the fan.

The shape optimisation (shape_opt.py) gives the largest thrust at a fixed
dp_disk. The question here is the opposite: which dp gives the wanted thrust
T*, with the best shape. The two meet at the solution: if a shape S gives
the largest thrust T* at dp*, any other shape gives less than T* at dp*, so
it needs a larger dp. The shape that maximises the thrust at dp* is then the
one that needs the smallest dp for T*. Hence the loop:

    dp_0 = lossless disk value for T*      (T = 2 dp A_exit when static)
    repeat
        optimise the shape at dp_k                       (largest thrust)
        fixed shape: secant on dp until T(dp) = T*       (dp_k+1)
    until dp_k+1 and dp_k differ less than tol_dp

The secant works on log T against log dp: near the solution T ~ dp^k with
k close to 1 (k = 1 for a lossless disk), so the first step lands within a
fraction of a percent and k comes out as a by-product.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, fields, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .shape_opt import DuctProblem, for_grid, optimise
from ..core.propulsion import PropulsionCase
from ..geometry.morph import MorphedGeometry, MorphLayout

THRUST_TOL = 1e-3      # relative thrust error the secant stops at
MAX_SECANT = 8         # secant steps at one shape
DP_RANGE = (0.2, 5.0)  # largest change of dp in one secant step, as a factor


@dataclass
class SizingResult:
    problem: DuctProblem          # last problem solved: the final dp, last optimisation grid
    design: np.ndarray
    steps: List[dict] = field(default_factory=list)
    exponent: float = 1.0         # d ln T / d ln dp at the final shape
    converged: bool = False


def _row(cycle: int, kind: str, problem: DuctProblem, thrust: float, **extra) -> dict:
    c = problem.case
    return dict(ciclo=cycle, tipo=kind, griglia=f"{c.Nz}x{c.Nr}", dp_disk=c.dp_disk,
                spinta=thrust, **extra)


def match_thrust(problem: DuctProblem, design: np.ndarray, T_target: float,
                 exponent: float = 1.0, cycle: int = 0, tol: float = THRUST_TOL,
                 log: Optional[Callable[[dict], None]] = None,
                 verbose: bool = True) -> Tuple[DuctProblem, List[dict], float]:
    """dp that gives T_target with the shape `design`, on the grid of `problem`.

    Returns the problem at the final dp (already solved), the steps and the
    exponent k of T ~ dp^k.
    """
    rows: List[dict] = []
    prev: Optional[Tuple[float, float]] = None
    for step in range(MAX_SECANT + 1):
        sol = problem.solve(design)
        if not sol.converged:
            raise RuntimeError(f"Flow not converged at dp = {problem.case.dp_disk:.4g} Pa "
                               f"on the {problem.case.Nz}x{problem.case.Nr} grid.")
        dp = problem.case.dp_disk
        T = problem.values(design)["thrust"]
        if prev is not None and T > 0.0 and prev[1] > 0.0 and dp != prev[0]:
            exponent = math.log(T / prev[1]) / math.log(dp / prev[0])
        err = T / T_target - 1.0
        row = _row(cycle, "secante", problem, T, errore_relativo=err, esponente=exponent)
        rows.append(row)
        if log:
            log(row)
        if verbose:
            print(f"  dp {dp:10.4f} Pa -> T {T:.6f} N (error {100 * err:+.3f} %)", flush=True)
        if abs(err) < tol:
            return problem, rows, exponent
        if T <= 0.0 or not exponent > 0.0:
            raise RuntimeError(f"Thrust {T:.4g} N at dp = {dp:.4g} Pa: no secant possible.")
        factor = float(np.clip((T_target / T) ** (1.0 / exponent), *DP_RANGE))
        prev = (dp, T)
        new = DuctProblem(replace(problem.case, dp_disk=dp * factor), problem.layout)
        new.warm_start(sol)
        problem = new
    raise RuntimeError(f"The thrust did not reach {T_target:.4g} N in {MAX_SECANT} steps.")


def initial_dp(case: PropulsionCase, layout: MorphLayout, design: np.ndarray) -> float:
    """dp of a lossless disk with the exit of the starting shape [Pa]."""
    g = MorphedGeometry(layout, design)
    return case.dp_ideal(math.pi * g.R_exit ** 2, case.T_target)


def size_for_thrust(case: PropulsionCase, layout: MorphLayout, design: np.ndarray,
                    grids: Sequence[Tuple[int, int]], max_iter: int = 40,
                    tol_dp: float = 0.01, max_cycles: int = 4, out_dir: Optional[str] = None,
                    verbose: bool = True) -> SizingResult:
    """The dp loop of the module docstring.

    The first cycle optimises on every grid of `grids`, coarse first; the
    later ones only on the last, starting from the shape and flow before.
    """
    if case.T_target is None:
        raise ValueError("The case has no thrust to reach (T_target).")
    T = case.T_target
    case = replace(case, dp_disk=initial_dp(case, layout, design))
    steps: List[dict] = []
    log_file = os.path.join(out_dir, "iterazioni_dp.json") if out_dir else None

    def log(row: dict) -> None:
        steps.append(row)
        if log_file:
            with open(log_file, "w", encoding="utf-8") as fh:
                json.dump(steps, fh, indent=1)

    problem: Optional[DuctProblem] = None
    exponent, converged = 1.0, False
    for cycle in range(1, max_cycles + 1):
        dp = case.dp_disk
        if verbose:
            print(f"\nCycle {cycle}: dp = {dp:.4f} Pa", flush=True)
        for Nz, Nr in (grids if cycle == 1 else grids[-1:]):
            new = DuctProblem(for_grid(case, Nz, Nr), layout)
            if problem is not None and problem.sol is not None:
                new.warm_start(problem.sol)
            problem = new
            if verbose:
                print(f" Shape optimisation, grid {Nz} x {Nr}", flush=True)
            hist = (os.path.join(out_dir, f"history_c{cycle}_{Nz}x{Nr}.json")
                    if out_dir else None)
            res = optimise(problem, design, max_iter=max_iter, log=hist, verbose=verbose)
            design = res.design
            log(_row(cycle, "ottimizzazione", problem, res.thrust, spinta_iniziale=res.thrust_start,
                     iterazioni=len(res.history), messaggio=res.message))
        if verbose:
            print(f" Secant on dp, grid {problem.case.Nz} x {problem.case.Nr}", flush=True)
        problem, _, exponent = match_thrust(problem, design, T, exponent, cycle, log=log,
                                            verbose=verbose)
        case = problem.case
        change = abs(case.dp_disk - dp) / case.dp_disk
        if verbose:
            print(f" dp {dp:.4f} -> {case.dp_disk:.4f} Pa ({100 * change:.2f} %)", flush=True)
        if change < tol_dp:
            converged = True
            break
    return SizingResult(problem=problem, design=design, steps=steps, exponent=exponent,
                        converged=converged)


# ---------------------------------------------------------------------------
# design.json: everything needed to solve the shape again, on any grid
# ---------------------------------------------------------------------------
def case_fields(case: PropulsionCase) -> Dict:
    return {f.name: getattr(case, f.name) for f in fields(case) if f.init}


def save_design(path: str, case: PropulsionCase, layout: MorphLayout, design: np.ndarray,
                summary: Optional[dict] = None) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dict(design=np.asarray(design).tolist(), L_section=layout.L_section,
                       n_up=layout.n_up, n_down=layout.n_down, case=case_fields(case),
                       summary=summary or {}), fh, indent=1)
    return path


def load_design(path: str) -> Tuple[PropulsionCase, MorphLayout, np.ndarray]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    layout = MorphLayout(L_section=data["L_section"], n_up=data["n_up"], n_down=data["n_down"])
    return PropulsionCase(**data["case"]), layout, np.array(data["design"])
