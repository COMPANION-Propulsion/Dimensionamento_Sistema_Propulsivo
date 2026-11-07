"""
fan_curve.py
============
Operating point of the duct with a fan curve dp(Q), instead of a fixed dp.

With a fixed dp the static thrust is about 2 dp A_exit, so a wider exit is always
better and the optimum sits on the size limit. A real fan gives less dp at more
flow: the duct and the fan meet where

    dp_fan(Q) = dp_needed_by_the_duct(Q)

and the duct shape changes Q, hence dp, hence the thrust. Here the duct is solved
at a trial dp, giving Q(dp); a secant on dp finds dp = curve(Q(dp)).

The curve comes from input.py (VENTURI["curva_ventola"]): a table of flow rates
[m3/s] and total-pressure rises [Pa], interpolated linearly, decreasing in Q. The
example in input.py is FICTITIOUS until the measured or computed curve is there.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, Dict, Optional, Sequence

import numpy as np

from .shape_opt import DuctProblem

TOL = 1e-3          # relative mismatch between dp and curve(Q) at the end
MAX_STEPS = 12


class FanCurve:
    """dp(Q) from a table; outside the table the end slopes are extended."""

    def __init__(self, Q: Sequence[float], dp: Sequence[float], fictitious: bool = False,
                 source: str = ""):
        q, p = np.asarray(Q, float), np.asarray(dp, float)
        order = np.argsort(q)
        self.Q, self.dp = q[order], p[order]
        if self.Q.size < 2 or np.any(np.diff(self.Q) <= 0):
            raise ValueError("Fan curve: at least two distinct flow rates are needed.")
        if np.any(np.diff(self.dp) > 0):
            raise ValueError("Fan curve: dp must not grow with Q (stable branch only).")
        self.fictitious, self.source = fictitious, source

    @classmethod
    def from_input(cls, d: Optional[Dict]) -> Optional["FanCurve"]:
        if not d:
            return None
        return cls(d["Q_m3_s"], d["dp_Pa"], bool(d.get("fittizia", False)), d.get("fonte", ""))

    def __call__(self, q: float) -> float:
        if q <= self.Q[0]:
            s = (self.dp[1] - self.dp[0]) / (self.Q[1] - self.Q[0])
            return float(self.dp[0] + s * (q - self.Q[0]))
        if q >= self.Q[-1]:
            s = (self.dp[-1] - self.dp[-2]) / (self.Q[-1] - self.Q[-2])
            return float(self.dp[-1] + s * (q - self.Q[-1]))
        return float(np.interp(q, self.Q, self.dp))

    def to_dict(self) -> Dict:
        return dict(Q_m3_s=self.Q.tolist(), dp_Pa=self.dp.tolist(), fittizia=self.fictitious,
                    fonte=self.source)


def operating_point(problem: DuctProblem, design: np.ndarray, curve: FanCurve,
                    dp0: Optional[float] = None, verbose: bool = False):
    """dp where the duct and the fan curve agree, for the shape `design`.

    Returns (problem at that dp, already solved; info dict). Raises RuntimeError
    when the flow does not converge or no crossing is found.
    """
    from .shape_opt import report
    dp = dp0 or curve(curve.Q.mean())
    prev = None
    rows = []
    for _ in range(MAX_STEPS):
        p = DuctProblem(replace(problem.case, dp_disk=dp), problem.layout,
                        disk_profile=problem.disk_profile)
        if problem.sol is not None:
            p.warm_start(problem.sol)
        sol = p.solve(design)
        if not sol.converged:
            raise RuntimeError(f"flow not converged at dp = {dp:.3g} Pa")
        q = float(sol.x[-1] * sol.system.s_Q)
        g = curve(q) - dp
        rows.append(dict(dp_Pa=dp, Q_m3_s=q, curva_Pa=curve(q)))
        if verbose:
            print(f"    dp {dp:8.3f} Pa -> Q {1e3*q:.4f} L/s, curve {curve(q):8.3f} Pa", flush=True)
        problem = p
        if abs(g) < TOL * dp:
            r = report(p, design)
            return p, dict(dp_Pa=dp, Q_m3_s=q, potenza_W=q * dp, spinta_N=r["thrust"],
                           passi=rows, scarto_curva_pct=100 * g / dp)
        if prev is None:
            new = 0.5 * (dp + curve(q))         # first step: halfway to the curve
        else:
            dp1, g1 = prev
            new = dp - g * (dp - dp1) / (g - g1) if g != g1 else 0.5 * (dp + curve(q))
        prev = (dp, g)
        dp = float(np.clip(new, 0.3 * dp, 3.0 * dp))
        if dp <= 0:
            raise RuntimeError("fan curve gives no positive dp at this flow")
    raise RuntimeError("no operating point found (dp and curve do not meet)")
