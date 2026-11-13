"""
shape_opt.py
============
Shape optimisation of the duct for the largest net thrust.

    shape -> grid -> flow (Newton) -> thrust -> adjoint -> gradient -> SLSQP

The optimiser moves the design vector of morph.py. Every shape starts its
Newton solve from the previous flow: the unknowns are scaled, so the same
numbers are a good guess on the next shape and need no interpolation.

Design variables: the control points of the two splines, the disk (fan)
radius and the two spline lengths, so the optimiser chooses diameter and
position of the fan. Every radius stays between R_min and R_int_max.

Constraints, all written as g(x) >= 0 for SLSQP:
    geometric (no flow solution needed)
        overall length (at most L_max, at least L_min) and outer diameter of the
        tube with its bell mouth,
        no radius below the disk radius (the fan sits in the throat),
        monotone intake (narrowing) and diffuser (widening),
        diffuser slope, intake slope, smooth control polygon
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
from ..core.propulsion import PropulsionCase
from ..export.cad import bell_envelope
from ..geometry.morph import MorphedGeometry, MorphLayout, fit_design
from ..solver.fvmesh import build_fvmesh

CF_MIN = 5e-4          # smallest friction coefficient allowed in the diffuser
MACH_MAX = 0.3         # the solver assumes constant density
SLOPE_DIFFUSER = math.tan(math.radians(4.0))   # default steepest diffuser wall (case.semiangolo_max_deg)
SLOPE_INTAKE = math.tan(math.radians(30.0))    # steepest intake wall
BEND_MAX = 0.25        # largest second difference of the control polygon / R_int_max
KS_RHO = 40.0          # sharpness of the smooth minimum
# Names of the constraint margins in the log and in the history files
MARGIN_NAMES = {"separation": "margine_separazione", "mach": "margine_mach",
                "cavitation": "margine_cavitazione", "power": "margine_potenza"}
THROAT_RAMP = 1.5      # cell-size ramp, fixed so the grid moves smoothly
N_SLOPE_SAMPLES = 64   # slope checks along each spline
L_WINDOW = 0.0005      # half width of the tube length window around L_target [m]
STEP_RADIUS = 1e-6     # finite-difference step on a control point [m]
STEP_LENGTH = 1e-5     # finite-difference step on a length [m]
DISK_START = 0.8       # starting disk radius / R_int_max
INLET_START = 1.2      # starting inlet radius / disk radius
START_SPLIT = 0.3      # share of the free length given to the starting intake
START_SLOPE = 0.6      # steepest starting wall / steepest wall allowed
START_FLOW = (0.85, 0.6, 0.45, 1.0)  # flow-rate guesses of a cold start / ideal one


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
def inlet_radius_limit(case: PropulsionCase) -> float:
    """Largest inlet radius whose bell mouth stays inside D_ext_max [m]."""
    lo, hi = 0.0, case.R_ext
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bell_envelope(mid, case.spessore_parete, case.raggio_bocca_su_D)[0] <= case.R_ext:
            lo = mid
        else:
            hi = mid
    return min(lo, case.R_int_max)


def initial_design(case: PropulsionCase, n_up: int = 5, n_down: int = 8):
    """A mild Venturi inside the limits, fitted with the morphing splines.

    Intake and diffuser are half cosines, R_in -> R_disk -> R_exit, whose
    steepest slope is START_SLOPE of the allowed one: the radius changes are
    cut where the length is too short for them.
    """
    R_in = min(INLET_START * DISK_START * case.R_int_max, 0.98 * inlet_radius_limit(case))
    R_disk = max(min(DISK_START * case.R_int_max, R_in / INLET_START), case.R_min)
    if R_in <= R_disk:
        raise ValueError(f"No room for an intake: inlet radius {R_in*1e3:.1f} mm, "
                         f"disk radius {R_disk*1e3:.1f} mm. Raise D_ext_max or lower "
                         f"spessore_parete / D_disk_min_ratio.")
    L_section = 2.0 * case.L_disk
    l_env = bell_envelope(R_in, case.spessore_parete, case.raggio_bocca_su_D)[1]
    room = 0.9 * (case.L_max - l_env) - L_section
    if case.L_min is not None:      # start inside [L_min, L_max]
        room = max(room, 0.5 * (case.L_min + case.L_max) - l_env - L_section)
    if room <= 0.0:
        raise ValueError(f"L_max ({case.L_max}) leaves no room around the disk section.")
    L_up, L_down = START_SPLIT * room, (1.0 - START_SPLIT) * room
    # a half cosine of rise dR over L has its steepest slope pi dR / (2 L)
    R_in = min(R_in, R_disk + START_SLOPE * SLOPE_INTAKE * 2.0 * L_up / math.pi)
    R_exit = min(case.R_int_max,
                 R_disk + START_SLOPE * math.tan(math.radians(case.semiangolo_max_deg))
                 * 2.0 * L_down / math.pi)
    z_up = np.linspace(0.0, L_up, 400)
    z_down = np.linspace(0.0, L_down, 800)
    z_a, z_b = L_up, L_up + L_section
    z = np.concatenate((z_up, z_b + z_down))
    R = np.concatenate((R_disk + (R_in - R_disk) * 0.5 * (1.0 + np.cos(np.pi * z_up / L_up)),
                        R_disk + (R_exit - R_disk) * 0.5 * (1.0 - np.cos(np.pi * z_down / L_down))))
    layout = MorphLayout(L_section=L_section, n_up=n_up, n_down=n_down)
    d = fit_design(layout, z, R, z_a, z_b, R_disk)
    d[:-3] = np.clip(d[:-3], R_disk, case.R_int_max)
    return layout, d


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------
class DuctProblem:
    """Thrust and constraints of a shape, with their adjoint gradients."""

    def __init__(self, case: PropulsionCase, layout: MorphLayout, verbose: bool = False,
                 Re_ref: Optional[float] = None,
                 disk_profile: Optional[Callable[[np.ndarray], np.ndarray]] = None):
        self.case = case
        # dp of the disk across the radius / dp_disk, as a function of r / R_disk:
        # None = uniform disk; a fan gives its own profile (0 inside the hub)
        self.disk_profile = disk_profile
        self.layout = layout
        self.verbose = verbose
        # Reynolds number of the inlet profile, fixed for the whole optimisation
        self.Re_ref = Re_ref or case.V_jet_ideal * 2.0 * case.R_int_max / case.nu
        self.sol: Optional[FlowSolution] = None
        self._key = None
        self._foreign = False        # self.sol comes from another dp
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
        if self.disk_profile is not None:
            s.force = s.force * np.asarray(self.disk_profile(mesh.eta_c))[None, :]
        if c.mozzo_su_D_disco > 0.0 or c.perdita_swirl > 0.0:   # first-order fan limits
            keep = (1.0 - c.perdita_swirl) * (mesh.eta_c >= c.mozzo_su_D_disco)
            s.force = s.force * keep[None, :]
        return s

    def solve(self, d: np.ndarray) -> FlowSolution:
        """Flow of the shape d, reusing the last result when d has not moved."""
        key = d.tobytes()
        if key == self._key:
            return self.sol
        s = self.system(d)
        if self.sol is None:
            sol = self._cold(s, d)
        else:
            sol = solve_flow(s, self.sol.x, self.sol.nu_t, outer=16, sigma0=5.0,
                             verbose=self.verbose)
            if not sol.converged:
                sol = solve_flow(s, self.sol.x, self.sol.nu_t, sigma0=200.0,
                                 verbose=self.verbose)
            if not sol.converged:     # too far from the last flow: start afresh
                sol = self._cold(s, d)
        if sol.converged:
            self.sol, self._key, self._foreign = sol, key, False
            self._grads = {}
        return sol

    def _cold(self, s: DuctSystem, d: np.ndarray) -> FlowSolution:
        """Flow from nothing: time marching at a guessed flow rate, then Newton.

        The time-marching start holds its inlet flow rate fixed, and from a
        guess too far off Newton may not converge: the next guess is tried then.
        """
        g = self.geometry(d)
        Q_ideal = math.pi * g.R_exit ** 2 * self.case.V_jet_ideal
        for k in START_FLOW:
            x, nu_t = time_march_start(s.mesh, self.case, s, k * Q_ideal)
            sol = solve_flow(s, x, nu_t, verbose=self.verbose)
            if sol.converged:
                break
        return sol

    def warm_start(self, sol: FlowSolution) -> None:
        """Start the next solve from the flow of another dp on the same grid.

        The unknowns are scaled by the ideal jet speed, so the same numbers
        are already a good guess; the eddy viscosity scales with that speed.
        A flow from another grid is ignored.
        """
        if (sol.system.Nz, sol.system.Nr) != (self.case.Nz, self.case.Nr):
            return
        k = self.case.V_jet_ideal / sol.system.case.V_jet_ideal
        self.sol = replace(sol, nu_t=sol.nu_t * k)
        self._key, self._foreign, self._grads = None, True, {}

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
        lay, c = self.layout, self.case
        c_up, c_down = lay.control_points(d)
        up, down, R_disk, _, _ = lay.split(d)
        s = (np.arange(N_SLOPE_SAMPLES) + 0.5) / N_SLOPE_SAMPLES
        dr_up = g.radius_derivative(g.L_up * s)
        dr_down = g.radius_derivative(g.z_b + g.L_down * s)
        bend = np.concatenate((np.diff(c_up, 2), np.diff(c_down, 2))) / c.R_int_max
        r_env, l_env = bell_envelope(g.R_inlet, c.spessore_parete, c.raggio_bocca_su_D)
        return np.concatenate((
            [(c.L_max - g.L_total - l_env) / c.L_max, (c.R_ext - r_env) / c.R_ext],
            [] if c.L_min is None else [(g.L_total + l_env - c.L_min) / c.L_max],
            [] if c.L_target is None else
            [(c.L_target + L_WINDOW - g.L_total - l_env) / c.L_max,
             (g.L_total + l_env - (c.L_target - L_WINDOW)) / c.L_max],
            (np.r_[up, down] - R_disk) / c.R_int_max,
            # monotone walls: the intake only narrows towards the fan, the diffuser
            # only widens. A monotone control polygon gives a monotone B-spline, so
            # no bumps (they only add losses and separation risk).
            -np.diff(c_up) / c.R_int_max, np.diff(c_down) / c.R_int_max,
            1.0 - dr_down / math.tan(math.radians(c.semiangolo_max_deg)),
            1.0 + dr_down / math.tan(math.radians(c.semiangolo_max_deg)),
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
    # variables scaled to order one: radii by R_int_max, lengths by L_max
    scale = np.r_[np.full(d0.size - 2, case.R_int_max), case.L_max, case.L_max]
    T0 = problem.values(d0)["thrust"]
    T_ref = abs(T0)
    t0 = time.time()
    history: List[dict] = []
    best = {"d": d0.copy(), "T": -math.inf}
    flow_names = [n for n in problem.functions if n != "thrust"]

    def margin(name: str, vals: Dict[str, float]) -> float:
        return 1.0 - vals[name] / case.P_max if name == "power" else vals[name]

    def violation(d: np.ndarray, vals: Dict[str, float]) -> float:
        """How far a shape is from feasible: sum of the violated margins (0 = feasible)."""
        return float(-min(problem.geometric(d).min(), 0.0)
                     - sum(min(margin(n, vals), 0.0) for n in flow_names))

    # When no iterate is feasible, the least infeasible one is kept, not the last:
    # SLSQP can wander away from the constraints in its final iterations.
    least = {"d": d0.copy(), "v": violation(d0, problem.values(d0)), "T": T0}

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
        sol = problem.solve(d)
        uz, ur = sol.system.velocities(sol.x)
        # The constraints are margins (1 = far, 0 = at the limit); the log shows the
        # physical Mach number next to them, the largest in the field.
        row = dict(iteration=len(history) + 1, time_s=round(time.time() - t0, 1),
                   L_total=g.L_total, D_inlet=2 * g.R_inlet, D_disk=2 * g.R_disk,
                   D_exit=2 * g.R_exit, thrust=vals["thrust"],
                   mach_max=float(np.sqrt(uz ** 2 + ur ** 2).max() / case.speed_of_sound),
                   geometric_min=float(problem.geometric(d).min()),
                   **{MARGIN_NAMES.get(n, n): margin(n, vals) for n in flow_names})
        history.append(row)
        row["converged"] = bool(sol.converged)
        feasible = (row["converged"] and row["geometric_min"] > -1e-3
                    and all(margin(n, vals) > -1e-3 for n in flow_names))
        if feasible and vals["thrust"] > best["T"]:
            best.update(d=d.copy(), T=vals["thrust"])
        row["violation"] = violation(d, vals)
        if row["converged"] and (row["violation"], -vals["thrust"]) < (least["v"], -least["T"]):
            least.update(d=d.copy(), v=row["violation"], T=vals["thrust"])
        if verbose:
            print(f"  it {row['iteration']:3d} [{row['time_s']:7.1f} s] "
                  f"T = {vals['thrust']:.4f} N, D_disk {row['D_disk']*1e3:.1f} mm, "
                  f"D_exit {row['D_exit']*1e3:.1f} mm, "
                  f"L {row['L_total']*1e3:.0f} mm, Mach {row['mach_max']:.4f}, "
                  + ", ".join(f"{MARGIN_NAMES.get(n, n)} {margin(n, vals):+.3f}"
                              for n in flow_names), flush=True)
        if log:
            with open(log, "w", encoding="utf-8") as fh:
                json.dump(dict(design=d.tolist(), history=history), fh, indent=1)

    lo = np.r_[np.full(d0.size - 2, case.R_min), 0.05 * case.L_max, 0.05 * case.L_max] / scale
    hi = np.r_[np.full(d0.size - 2, case.R_int_max), case.L_max, case.L_max] / scale
    cons = [dict(type="ineq", fun=lambda u: problem.geometric(u * scale),
                 jac=lambda u: problem.geometric_jac(u * scale) * scale),
            dict(type="ineq", fun=flow_con, jac=flow_jac)]
    res = minimize(objective, d0 / scale, jac=objective_grad, method="SLSQP",
                   bounds=list(zip(lo, hi)), constraints=cons, callback=record,
                   options=dict(maxiter=max_iter, ftol=ftol))
    feasible = best["T"] > -math.inf
    d_best = best["d"] if feasible else least["d"]
    message = str(res.message)
    if not feasible:
        message += f" | no feasible shape: least infeasible kept (violation {least['v']:.3g})"
        if verbose:
            print(f"  WARNING: no feasible shape, kept the least infeasible one "
                  f"(violation {least['v']:.3g})", flush=True)
    return OptResult(design=d_best, thrust=problem.values(d_best)["thrust"], thrust_start=T0,
                     history=history, success=bool(res.success) and feasible, message=message)


def report(problem: DuctProblem, d: np.ndarray) -> Dict[str, float]:
    """Numbers of a finished shape, including the independent thrust check."""
    sol = problem.solve(d)
    case, s = problem.case, sol.system
    g = problem.geometry(d)
    uz, ur = s.velocities(sol.x)
    T = thrust(s, sol.x)
    P = power(s, sol.x)
    Q = float(sol.x[-1] * s.s_Q)
    A_e = math.pi * g.R_exit ** 2
    r_env, l_env = bell_envelope(g.R_inlet, case.spessore_parete, case.raggio_bocca_su_D)
    T_forces = momentum_balance(s, sol.x)
    m_dot = case.rho * Q
    return dict(dp_disk=case.dp_disk, thrust=T, thrust_from_forces=T_forces,
                thrust_check_pct=100.0 * (T_forces / T - 1.0),
                beta=T / (m_dot * Q / A_e) if Q > 0 else float("nan"),
                power=P, thrust_per_power=T / P, Q=Q, mass_flow=case.rho * Q,
                V_disk=Q / (math.pi * g.R_disk ** 2), V_exit=Q / A_e,
                ideal_thrust=(2.0 * case.dp_disk * A_e if case.V0 == 0.0 else float("nan")),
                area_ratio=(g.R_exit / g.R_throat) ** 2, D_inlet=2 * g.R_inlet,
                D_disk=2 * g.R_disk, z_disk=0.5 * (g.z_a + g.z_b),
                D_exit=2 * g.R_exit, L_total=g.L_total,
                D_ext_tube=2.0 * max(r_env, case.R_int_max + case.spessore_parete),
                L_tube=g.L_total + l_env,
                mach_max=float(np.sqrt(uz ** 2 + ur ** 2).max() / case.speed_of_sound),
                separation_margin=separation_margin(s, sol.x),
                reversed_cells=int((uz < 0.0).sum()), residual=sol.residual)


def for_grid(case: PropulsionCase, Nz: int, Nr: int) -> PropulsionCase:
    """The same case on another grid."""
    return replace(case, Nz=Nz, Nr=Nr)
