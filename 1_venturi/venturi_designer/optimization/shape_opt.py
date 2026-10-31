"""
shape_opt.py
============
Shape optimisation of the duct for the largest net thrust.

    shape -> grid -> flow (Newton) -> thrust -> adjoint -> gradient -> SLSQP

The optimiser moves the design vector of morph.py. Every shape starts its
Newton solve from the previous flow: the unknowns are scaled, so the same
numbers are a good guess on the next shape and need no interpolation.

Constraints, all written as g(x) >= 0 for SLSQP:
    geometric (no flow solution needed)
        total length, diffuser slope, intake slope, smooth control polygon
    flow (each one is an adjoint)
        wall friction above a limit in the diffuser, as a separation margin;
        Mach limit for gases; vapour pressure for liquids; power limit

Why the separation margin is not a detail: at fixed dp_disk the ideal thrust
is 2*dp*Ae, so the optimiser always widens the exit, and the only thing that
stops it is the flow leaving the wall. The algebraic turbulence model is at
its weakest right there, so the margin keeps the shape away from separation
rather than trusting a prediction of it.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional

import numpy as np
from scipy.optimize import minimize

from .adjoint import (DuctSystem, FlowSolution, adjoint_gradients, momentum_balance,
                      solve_flow, thrust, time_march_start)
from ..core.config import VenturiConfig
from ..core.propulsion import PropulsionCase
from ..geometry.morph import MorphedGeometry, MorphLayout, fit_design
from ..geometry.venturi import VenturiGeometry
from ..solver.fvmesh import build_fvmesh

CF_MIN = 5e-4          # smallest friction coefficient allowed in the diffuser
MACH_MAX = 0.3         # the solver assumes constant density
SLOPE_DIFFUSER = math.tan(math.radians(7.0))   # steepest diffuser wall
SLOPE_INTAKE = math.tan(math.radians(30.0))    # steepest intake wall
BEND_MAX = 0.25        # largest second difference of the control polygon / R_disk
Z_DISK_TOL = 0.005     # allowed drift of the disk position, as a fraction of the length
KS_RHO = 40.0          # sharpness of the smooth minimum
THROAT_RAMP = 1.5      # cell-size ramp, fixed so the grid moves smoothly
N_SLOPE_SAMPLES = 24   # slope checks along each spline
STEP_RADIUS = 1e-6     # finite-difference step on a control point [m]
STEP_LENGTH = 1e-5     # finite-difference step on a length [m]


def ks_min(values: np.ndarray, rho: float = KS_RHO) -> float:
    """Smooth lower bound of min(values): a differentiable minimum."""
    v0 = float(values.min())
    return v0 + math.log(float(np.mean(np.exp(-rho * (values - v0))))) / rho


# ---------------------------------------------------------------------------
# Flow functions f(system, state)
# ---------------------------------------------------------------------------
def power(sys_: DuctSystem, x: np.ndarray) -> float:
    """Power given to the flow by the disk [W]."""
    return float(x[-1] * sys_.s_Q * sys_.case.dp_disk)


def separation_margin(sys_: DuctSystem, x: np.ndarray) -> float:
    """Smooth minimum of cf / CF_MIN - 1 along the diffuser wall."""
    m, case = sys_.mesh, sys_.case
    uz, ur = sys_.velocities(x)
    keep = m.z_c > sys_.z_b
    # wall-parallel speed of the wall cell, signed: negative means reversed flow
    tz, tr = m.nr_rad[:, -1], -m.nz_rad[:, -1]
    us = uz[:, -1] * tz + ur[:, -1] * tr
    u_core = np.maximum(uz[:, 0], 0.1 * sys_.U)
    cf = 2.0 * case.nu * us / m.wall_distance[:, -1] / u_core ** 2
    return ks_min(cf[keep] / CF_MIN - 1.0)


def mach_margin(sys_: DuctSystem, x: np.ndarray) -> float:
    """Smooth minimum of 1 - Mach / MACH_MAX over the field."""
    uz, ur = sys_.velocities(x)
    mach = np.sqrt(uz ** 2 + ur ** 2) / sys_.case.speed_of_sound
    return ks_min((1.0 - mach / MACH_MAX).ravel())


def cavitation_margin(sys_: DuctSystem, x: np.ndarray) -> float:
    """Smooth minimum of (p - p_vap) / dp_disk over the field."""
    _, _, p, _ = sys_.unpack(x)
    case = sys_.case
    return ks_min(((p * case.rho + case.p_amb - case.p_vap) / case.dp_disk).ravel())


# ---------------------------------------------------------------------------
# Starting shape
# ---------------------------------------------------------------------------
def initial_design(case: PropulsionCase, n_up: int = 5, n_down: int = 8):
    """A mild Venturi inside the limits, fitted with the morphing splines."""
    D_in = min(1.25 * case.D_disk, case.D_max)
    L_section = 2.0 * case.L_disk
    cfg = VenturiConfig(
        D=D_in, beta=case.D_disk / D_in, alpha_conv_deg=30.0, alpha_div_deg=5.0,
        L_inlet_ratio=0.15, L_throat_ratio=L_section / case.D_disk, L_outlet_ratio=0.15,
        fluid=case.fluid, p_throat_target=None, v_inlet=1.0)
    geom = VenturiGeometry(cfg)
    z, R = geom.profile_points(1200)
    z_a, z_b = float(geom.z_stations[2]), float(geom.z_stations[3])
    room = 0.9 * case.L_max - L_section
    excess = z[-1] - L_section
    if excess > room:          # squeeze the two splines, keep the section
        k = room / excess
        z = np.where(z <= z_a, z * k,
                     np.where(z >= z_b, z_a * k + L_section + (z - z_b) * k,
                              z_a * k + (z - z_a)))
        z_a, z_b = z_a * k, z_a * k + L_section
    layout = MorphLayout(R_disk=0.5 * case.D_disk, L_section=L_section,
                         n_up=n_up, n_down=n_down)
    d = fit_design(layout, z, R, z_a, z_b)
    d[:-2] = np.clip(d[:-2], layout.R_disk, 0.5 * case.D_max)
    if case.z_disk is not None:      # move the section, the splines just stretch
        L_total = d[-2] + L_section + d[-1]
        d[-2] = case.z_disk * L_total - 0.5 * L_section
        d[-1] = L_total - L_section - d[-2]
        if d[-2] <= 0.0 or d[-1] <= 0.0:
            raise ValueError(f"z_disk = {case.z_disk} puts the disk section outside the "
                             f"{L_total:.3f} m long starting duct.")
    return layout, d


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------
class DuctProblem:
    """Thrust and constraints of a shape, with their adjoint gradients."""

    def __init__(self, case: PropulsionCase, layout: MorphLayout, verbose: bool = False):
        self.case = case
        self.layout = layout
        self.verbose = verbose
        self.Re_ref = case.V_jet_ideal * case.D_disk / case.nu
        self.sol: Optional[FlowSolution] = None
        self._key = None
        self.functions: Dict[str, Callable] = {"thrust": thrust,
                                               "separation": separation_margin}
        if case.is_gas:
            self.functions["mach"] = mach_margin
        if case.p_vap > 0.0:
            self.functions["cavitation"] = cavitation_margin
        if case.P_max is not None:
            self.functions["power"] = power
        self._grads: Dict[str, np.ndarray] = {}

    def geometry(self, d: np.ndarray) -> MorphedGeometry:
        return MorphedGeometry(self.layout, d)

    def system(self, d: np.ndarray) -> DuctSystem:
        g = self.geometry(d)
        c = self.case
        mesh = build_fvmesh(g, c.Nz, c.Nr, c.wall_clustering, c.throat_refine,
                            throat_ramp=THROAT_RAMP)
        z0 = 0.5 * (g.z_a + g.z_b)
        s = DuctSystem(mesh, c, z0 - 0.5 * c.L_disk, z0 + 0.5 * c.L_disk, self.Re_ref)
        s.z_b = g.z_b
        return s

    def solve(self, d: np.ndarray) -> FlowSolution:
        """Flow of the shape d, reusing the last result when d has not moved."""
        key = d.tobytes()
        if key == self._key:
            return self.sol
        s = self.system(d)
        if self.sol is None:
            g = self.geometry(d)
            Q0 = 0.85 * math.pi * g.R_exit ** 2 * self.case.V_jet_ideal
            x, nu_t = time_march_start(s.mesh, self.case, s, Q0)
            sol = solve_flow(s, x, nu_t, verbose=self.verbose)
        else:
            sol = solve_flow(s, self.sol.x, self.sol.nu_t, relax=0.7, outer=6, sigma0=5.0,
                             verbose=self.verbose)
            if not sol.converged:
                sol = solve_flow(s, self.sol.x, self.sol.nu_t, sigma0=200.0,
                                 verbose=self.verbose)
        if sol.converged:
            self.sol, self._key = sol, key
            self._grads = {}
        return sol

    def values(self, d: np.ndarray) -> Dict[str, float]:
        sol = self.solve(d)
        return {n: float(f(sol.system, sol.x)) for n, f in self.functions.items()}

    def gradients(self, d: np.ndarray) -> Dict[str, np.ndarray]:
        sol = self.solve(d)
        if not self._grads:
            steps = np.r_[np.full(d.size - 2, STEP_RADIUS), STEP_LENGTH, STEP_LENGTH]
            self._grads = adjoint_gradients(sol, self.functions, self.system, d, steps)
        return self._grads

    # -- geometric constraints (>= 0) ----------------------------------------
    def geometric(self, d: np.ndarray) -> np.ndarray:
        g = self.geometry(d)
        lay = self.layout
        c_up, c_down = lay.control_points(d)
        s = (np.arange(N_SLOPE_SAMPLES) + 0.5) / N_SLOPE_SAMPLES
        dr_up = g.radius_derivative(g.L_up * s)
        dr_down = g.radius_derivative(g.z_b + g.L_down * s)
        bend = np.concatenate((np.diff(c_up, 2), np.diff(c_down, 2))) / lay.R_disk
        position = []
        if self.case.z_disk is not None:
            shift = (0.5 * (g.z_a + g.z_b) / g.L_total - self.case.z_disk) / Z_DISK_TOL
            position = [1.0 - shift, 1.0 + shift]
        return np.concatenate((
            [(self.case.L_max - g.L_total) / self.case.L_max], position,
            1.0 - dr_down / SLOPE_DIFFUSER, 1.0 + dr_down / SLOPE_DIFFUSER,
            1.0 - dr_up / SLOPE_INTAKE, 1.0 + dr_up / SLOPE_INTAKE,
            1.0 - bend / BEND_MAX, 1.0 + bend / BEND_MAX))

    def geometric_jac(self, d: np.ndarray) -> np.ndarray:
        g0 = self.geometric(d)
        J = np.empty((g0.size, d.size))
        for k in range(d.size):
            t = d.copy()
            t[k] += 1e-7
            J[:, k] = (self.geometric(t) - g0) / 1e-7
        return J


# ---------------------------------------------------------------------------
# Optimisation
# ---------------------------------------------------------------------------
@dataclass
class OptResult:
    design: np.ndarray
    thrust: float
    thrust_start: float
    history: List[dict] = field(default_factory=list)
    success: bool = False
    message: str = ""


def optimise(problem: DuctProblem, d0: np.ndarray, max_iter: int = 40, ftol: float = 1e-4,
             log: Optional[str] = None, verbose: bool = True) -> OptResult:
    """Largest thrust with SLSQP. All variables and functions are scaled."""
    case, lay = problem.case, problem.layout
    # variables scaled to order one: radii by R_disk, lengths by L_max
    scale = np.r_[np.full(d0.size - 2, lay.R_disk), case.L_max, case.L_max]
    T0 = problem.values(d0)["thrust"]
    T_ref = abs(T0)
    t0 = time.time()
    history: List[dict] = []
    best = {"d": d0.copy(), "T": -math.inf}
    flow_names = [n for n in problem.functions if n != "thrust"]

    def margin(name: str, vals: Dict[str, float]) -> float:
        return 1.0 - vals[name] / case.P_max if name == "power" else vals[name]

    def margin_grad(name: str, g: np.ndarray) -> np.ndarray:
        return -g / case.P_max if name == "power" else g

    def objective(u):
        sol = problem.solve(u * scale)
        if not sol.converged:
            return 0.0            # the line search backs off from this point
        return -float(thrust(sol.system, sol.x)) / T_ref

    def objective_grad(u):
        return -problem.gradients(u * scale)["thrust"] * scale / T_ref

    def flow_con(u):
        vals = problem.values(u * scale)
        return np.array([margin(n, vals) for n in flow_names])

    def flow_jac(u):
        g = problem.gradients(u * scale)
        return np.array([margin_grad(n, g[n]) * scale for n in flow_names])

    def record(u):
        d = u * scale
        vals = problem.values(d)
        g = problem.geometry(d)
        row = dict(iteration=len(history) + 1, time_s=round(time.time() - t0, 1),
                   L_total=g.L_total, D_inlet=2 * g.R_inlet, D_exit=2 * g.R_exit,
                   geometric_min=float(problem.geometric(d).min()), **vals)
        history.append(row)
        feasible = (row["geometric_min"] > -1e-3
                    and all(margin(n, vals) > -1e-3 for n in flow_names))
        if feasible and vals["thrust"] > best["T"]:
            best.update(d=d.copy(), T=vals["thrust"])
        if verbose:
            print(f"  it {row['iteration']:3d} [{row['time_s']:7.1f} s] "
                  f"T = {vals['thrust']:.4f} N, D_exit {row['D_exit']*1e3:.1f} mm, "
                  f"L {row['L_total']*1e3:.0f} mm, "
                  + ", ".join(f"{n} {margin(n, vals):+.3f}" for n in flow_names), flush=True)
        if log:
            with open(log, "w", encoding="utf-8") as fh:
                json.dump(dict(design=d.tolist(), history=history), fh, indent=1)

    lo = np.r_[np.full(d0.size - 2, lay.R_disk), 0.05 * case.L_max, 0.05 * case.L_max] / scale
    hi = np.r_[np.full(d0.size - 2, 0.5 * case.D_max), case.L_max, case.L_max] / scale
    cons = [dict(type="ineq", fun=lambda u: problem.geometric(u * scale),
                 jac=lambda u: problem.geometric_jac(u * scale) * scale),
            dict(type="ineq", fun=flow_con, jac=flow_jac)]
    res = minimize(objective, d0 / scale, jac=objective_grad, method="SLSQP",
                   bounds=list(zip(lo, hi)), constraints=cons, callback=record,
                   options=dict(maxiter=max_iter, ftol=ftol))
    d_best = best["d"] if best["T"] > -math.inf else res.x * scale
    return OptResult(design=d_best, thrust=problem.values(d_best)["thrust"], thrust_start=T0,
                     history=history, success=bool(res.success), message=str(res.message))


def report(problem: DuctProblem, d: np.ndarray) -> Dict[str, float]:
    """Numbers of a finished shape, including the independent thrust check."""
    sol = problem.solve(d)
    case, s = problem.case, sol.system
    g = problem.geometry(d)
    uz, ur = s.velocities(sol.x)
    T = thrust(s, sol.x)
    P = power(s, sol.x)
    return dict(thrust=T, thrust_from_forces=momentum_balance(s, sol.x), power=P,
                thrust_per_power=T / P, Q=float(sol.x[-1] * s.s_Q),
                ideal_thrust=(2.0 * case.dp_disk * math.pi * g.R_exit ** 2
                              if case.V0 == 0.0 else float("nan")),
                area_ratio=(g.R_exit / g.R_throat) ** 2, D_inlet=2 * g.R_inlet,
                D_exit=2 * g.R_exit, L_total=g.L_total,
                mach_max=float(np.sqrt(uz ** 2 + ur ** 2).max() / case.speed_of_sound),
                separation_margin=separation_margin(s, sol.x),
                reversed_cells=int((uz < 0.0).sum()), residual=sol.residual)


def for_grid(case: PropulsionCase, Nz: int, Nr: int) -> PropulsionCase:
    """The same case on another grid."""
    return replace(case, Nz=Nz, Nr=Nr)
