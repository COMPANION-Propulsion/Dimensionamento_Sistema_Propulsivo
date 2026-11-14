"""
adjoint.py
==========
Steady system of the duct, its Newton solver and the discrete adjoint.

Steady residual
---------------
The time-marching solver in solver/solver.py stops being useful for shape
optimisation at the point where the gradient needs it most: its residual
stalls well above what an adjoint needs, because the limiter and the eddy
viscosity keep moving. So the steady equations are written here as a single
system R(U) = 0, built from THE SAME kernels the solver uses. At a steady
state of the solver, dt_f * (a_f - pressure gradient) = 0 on every face, and
that bracket is exactly the momentum part of R. The two differ only by
two small terms the Newton iteration needs: the smooth van Albada limiter
(see solver/kernels._tvd) and the flux dissipation below.

Unknowns U, all scaled to order one:
    F_ax   (Nz, Nr)      axial fluxes, faces 1..Nz (the inlet row follows Q)
    F_rad  (Nz, Nr-1)    conical fluxes, inner faces
    p      (Nz, Nr)      kinematic gauge pressure p/rho, 0 on the exit face
    Q      scalar        flow rate

Equations R:
    momentum on every flux face, continuity in every cell, and one extra
    equation closing the flow rate: the total pressure of the incoming flow
    must equal the ambient total pressure,
        p_mean(inlet row) + alpha * Vin^2 / 2 = V0^2 / 2
    alpha being the kinetic-energy factor of the inlet profile.

Flux dissipation
----------------
The momentum equations act on cell accelerations averaged to the faces, and
cell velocities are averaged from the faces, so an odd-even oscillation of
the fluxes along a grid line is invisible to them. The pressure is compact
(MAC), but the fluxes are not: the Jacobian has singular values about 1e5
times smaller than its largest entries, and those modes are exactly
+ - + - along i. Newton cannot converge on such a matrix. The cure is the
idea behind Rhie-Chow: each flux is pulled towards the value rebuilt from
the neighbouring cell velocities,

    R_face -= kappa * (U / dz) * (F - F_from_cells)

F - F_from_cells is O(h^2) on a smooth field and equal to F on the odd-even
mode, so the term removes the mode and vanishes as the grid is refined.

Adjoint
-------
For a scalar function f(U, x) with R(U, x) = 0:

    J^T lam = df/dU,      df/dx total = df/dx - lam^T dR/dx

One factorisation of J serves every function, so the thrust and each
constraint cost one back-substitution, and the cost does not grow with the
number of design variables. dR/dx and df/dx come from finite differences of
R and f at frozen U, which needs no flow solution.

The eddy viscosity nu_t is frozen in both: the algebraic model searches for
a maximum along the wall normal, which is not differentiable. That is an
approximation of the gradient, not of the flow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable, Dict, Tuple

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ..core.propulsion import PropulsionCase, disk_force, thrust_from_fluxes
from ..solver import inlet_profile, solve_fv
from ..solver.fvmesh import FVMesh, divergence
from ..solver.kernels import explicit_rhs, radial_explicit, reconstruct
from ..solver.projection import compute_face_coefficients
from ..solver.turbulence import compute_nu_t

W_AX = 4        # reach of the stencil along the axis, in cells
W_RAD = 5       # reach of the stencil along the radius, in cells
FD_STEP = 1e-7  # step on the scaled unknowns
KAPPA_FLUX = 0.1    # strength of the flux dissipation
EPS_LIMITER = 1e-3  # velocity differences below this fraction of U are noise
FD_STATE = 1e-7  # step of df/dU on the scaled unknowns
RELAX_KEEP = 3   # updates of nu_t at full strength
RELAX_DECAY = 0.7  # then each update is this much smaller
MAX_STEP = 0.2  # largest change of a scaled unknown in one Newton step
FLAT_INLET = True  # uniform inlet profile (duct drawing still air); False = developed pipe profile

_COLOURINGS: Dict[Tuple[int, int], tuple] = {}


class DuctSystem:
    """R(U) = 0 on one grid, with the eddy viscosity frozen."""

    def __init__(self, mesh: FVMesh, case: PropulsionCase, z_a: float, z_b: float,
                 Re_ref: float):
        self.mesh = mesh
        self.case = case
        Nz, Nr = mesh.Nz, mesh.Nr
        self.Nz, self.Nr = Nz, Nr
        self.n_ax = Nz * Nr
        self.n_rad = Nz * (Nr - 1)
        self.n_p = Nz * Nr
        self.n = self.n_ax + self.n_rad + self.n_p + 1

        coef = compute_face_coefficients(mesh)
        self.c_ax, self.c_rad = coef.c_ax, coef.c_rad
        self.c_ax_diff = self.c_ax.copy()
        self.c_ax_diff[Nz, :] = 0.0
        self.c_in = mesh.A_ax[0, :] / (mesh.z_c[0] - mesh.z_f[0])
        A_w = mesh.A_rad[:, Nr]
        d1 = (mesh.R_c - mesh.r_c[:, Nr - 1]) * mesh.nr_rad[:, Nr]
        d2 = (mesh.R_c - mesh.r_c[:, Nr - 2]) * mesh.nr_rad[:, Nr]
        self.cw1 = A_w * d2 / (d1 * (d2 - d1))
        self.cw2 = -A_w * d1 / (d2 * (d2 - d1))

        self.force = disk_force(mesh, z_a, z_b, case.dp_disk, case.rho)
        # Still air drawn through the bell mouth: uniform speed and total pressure at
        # the entry (the developed pipe profile gave p_t > 0 on the axis, unphysical)
        self.shape = inlet_profile(mesh, Re_ref, 1.0, flat=FLAT_INLET)     # uz_in per unit Q
        A0 = mesh.A_ax[0, :]
        self.A_in = float(A0.sum())
        self.alpha = float(np.sum(A0 * self.shape ** 3) * self.A_in ** 2)
        self.w_in = A0 / self.A_in

        # Scales: the same field on any shape gives the same scaled numbers.
        self.U = case.V_jet_ideal
        self.eps2 = (EPS_LIMITER * self.U) ** 2
        L = float(mesh.R_f.min())
        self.s_ax = mesh.A_ax[1:, :] * self.U
        self.s_rad = mesh.Cr_rad[:, 1:Nr] * self.U
        self.s_p = self.U ** 2
        self.s_Q = self.A_in * self.U
        self.r_ax = mesh.A_ax[1:, :] * self.U ** 2 / L
        self.r_rad = mesh.Cr_rad[:, 1:Nr] * self.U ** 2 / L
        self.r_m = np.maximum(mesh.A_ax[:-1, :], mesh.A_ax[1:, :]) * self.U

        dz_f = np.empty(Nz)
        dz_f[:-1] = mesh.z_c[1:] - mesh.z_c[:-1]
        dz_f[-1] = mesh.z_f[-1] - mesh.z_c[-1]
        self.diss_ax = KAPPA_FLUX * self.U / dz_f[:, None]
        self.diss_rad = KAPPA_FLUX * self.U / np.diff(mesh.z_f)[:, None]

        # work arrays
        self._uz = np.zeros((Nz, Nr))
        self._ur = np.zeros((Nz, Nr))
        self._az_e = np.zeros((Nz, Nr))
        self._ar_e = np.zeros((Nz, Nr))
        self._az = np.zeros((Nz, Nr))
        self._ar = np.zeros((Nz, Nr))
        self._F_ax = np.zeros((Nz + 1, Nr))
        self._F_rad = np.zeros((Nz, Nr + 1))
        self.nu_eff = np.full((Nz, Nr), case.nu)

    # -- state ---------------------------------------------------------------
    def set_nu_t(self, nu_t: np.ndarray) -> None:
        self.nu_eff = nu_t + self.case.nu

    def unpack(self, x: np.ndarray):
        Nz, Nr = self.Nz, self.Nr
        a, b, c = self.n_ax, self.n_ax + self.n_rad, self.n - 1
        F_ax = self._F_ax
        F_rad = self._F_rad
        Q = float(x[-1]) * self.s_Q
        F_ax[0, :] = self.mesh.A_ax[0, :] * self.shape * Q
        F_ax[1:, :] = x[:a].reshape(Nz, Nr) * self.s_ax
        F_rad[:, 1:Nr] = x[a:b].reshape(Nz, Nr - 1) * self.s_rad
        p = x[b:c].reshape(Nz, Nr) * self.s_p
        return F_ax, F_rad, p, Q

    def pack(self, F_ax, F_rad, p, Q) -> np.ndarray:
        return np.concatenate(((F_ax[1:, :] / self.s_ax).ravel(),
                               (F_rad[:, 1:self.Nr] / self.s_rad).ravel(),
                               (p / self.s_p).ravel(), [Q / self.s_Q]))

    def velocities(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        F_ax, F_rad, _, _ = self.unpack(x)
        m = self.mesh
        reconstruct(F_ax, F_rad, m.A_ax, m.Cr_rad, m.Cz_rad, self._uz, self._ur)
        return self._uz, self._ur

    # -- residual ------------------------------------------------------------
    def residual(self, x: np.ndarray, closure: bool = True) -> np.ndarray:
        m = self.mesh
        Nz, Nr = self.Nz, self.Nr
        nu = self.case.nu
        F_ax, F_rad, p, Q = self.unpack(x)
        uz, ur = self._uz, self._ur
        az, ar = self._az, self._ar
        reconstruct(F_ax, F_rad, m.A_ax, m.Cr_rad, m.Cz_rad, uz, ur)
        explicit_rhs(uz, ur, F_ax, F_rad, self.nu_eff, self.c_ax_diff, self.c_rad,
                     self.c_in, m.vol, self.shape * Q, self._az_e, self._ar_e, self.eps2)
        radial_explicit(uz, ur, self._az_e, self._ar_e, self.nu_eff, nu, self.c_rad,
                        self.cw1, self.cw2, m.vol, m.r_c, az, ar)
        az += self.force

        R_ax = np.empty((Nz, Nr))
        R_ax[:-1, :] = (m.A_ax[1:Nz, :] * 0.5 * (az[:-1, :] + az[1:, :])
                        + self.c_ax[1:Nz, :] * (p[:-1, :] - p[1:, :]))
        R_ax[-1, :] = m.A_ax[Nz, :] * az[-1, :] + self.c_ax[Nz, :] * p[-1, :]

        afz = 0.5 * (az[:, :-1] + az[:, 1:])
        afr = 0.5 * (ar[:, :-1] + ar[:, 1:])
        R_rad = (m.Cr_rad[:, 1:Nr] * afr - m.Cz_rad[:, 1:Nr] * afz
                 + self.c_rad[:, 1:Nr] * (p[:, :-1] - p[:, 1:]))

        # Flux dissipation, see the module docstring
        uz_f = np.empty((Nz, Nr))
        uz_f[:-1, :] = 0.5 * (uz[:-1, :] + uz[1:, :])
        uz_f[-1, :] = 1.5 * uz[-1, :] - 0.5 * uz[-2, :]
        R_ax -= self.diss_ax * (F_ax[1:, :] - m.A_ax[1:, :] * uz_f)
        R_rad -= self.diss_rad * (F_rad[:, 1:Nr]
                                  - m.Cr_rad[:, 1:Nr] * 0.5 * (ur[:, :-1] + ur[:, 1:])
                                  + m.Cz_rad[:, 1:Nr] * 0.5 * (uz[:, :-1] + uz[:, 1:]))

        R_m = divergence(F_ax, F_rad, m)
        R_Q = self.closure(p, Q) if closure else 0.0
        return np.concatenate(((R_ax / self.r_ax).ravel(), (R_rad / self.r_rad).ravel(),
                               (R_m / self.r_m).ravel(), [R_Q]))

    def closure(self, p: np.ndarray, Q: float) -> float:
        V = Q / self.A_in
        return float(np.sum(self.w_in * p[0, :]) + 0.5 * self.alpha * V * V
                     - 0.5 * self.case.V0 ** 2) / self.s_p

    # -- Jacobian ------------------------------------------------------------
    def _cell_of_unknowns(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Cell (i, j) and field number of every unknown, except Q."""
        Nz, Nr = self.Nz, self.Nr
        I, J = np.meshgrid(np.arange(Nz), np.arange(Nr), indexing="ij")
        Ir, Jr = np.meshgrid(np.arange(Nz), np.arange(1, Nr), indexing="ij")
        i = np.concatenate((I.ravel(), Ir.ravel(), I.ravel()))
        j = np.concatenate((J.ravel(), Jr.ravel(), J.ravel()))
        field = np.concatenate((np.zeros(I.size, int), np.ones(Ir.size, int),
                                np.full(I.size, 2)))
        return i, j, field

    def _colouring(self):
        """Stencil pattern and a colouring, cached per grid size.

        Two unknowns share a colour when they are further apart than twice
        the reach of the stencil, so no equation sees both, and the whole
        Jacobian takes about (2*W_AX+1) * (2*W_RAD+1) * 3 residuals. The
        closure row is left out, it would couple the whole inlet row; it is
        linear in p and is added analytically.
        """
        key = (self.Nz, self.Nr)
        if key in _COLOURINGS:
            return _COLOURINGS[key]
        i, j, field = self._cell_of_unknowns()
        n = self.n
        wi, wj = 2 * W_AX + 1, 2 * W_RAD + 1
        groups = np.empty(n, dtype=int)
        groups[:-1] = (i % wi) + wi * ((j % wj) + wj * field)
        groups[-1] = groups[:-1].max() + 1

        key_cell = i * self.Nr + j
        order = np.argsort(key_cell, kind="stable")
        sorted_key = key_cell[order]
        cells = np.arange(self.Nz * self.Nr)
        starts = np.searchsorted(sorted_key, cells)
        ends = np.searchsorted(sorted_key, cells, side="right")
        rows, cols = [], []
        for c in range(n - 1):
            b0, b1 = max(j[c] - W_RAD, 0), min(j[c] + W_RAD, self.Nr - 1)
            for a in range(max(i[c] - W_AX, 0), min(i[c] + W_AX, self.Nz - 1) + 1):
                lo, hi = starts[a * self.Nr + b0], ends[a * self.Nr + b1]
                rows.append(order[lo:hi])
                cols.append(np.full(hi - lo, c))
        near_inlet = np.nonzero(i <= W_AX)[0]      # the equations that see Q
        rows.append(near_inlet)
        cols.append(np.full(near_inlet.size, n - 1))
        rows, cols = np.concatenate(rows), np.concatenate(cols)
        pattern = sp.csc_matrix((np.ones(rows.size), (rows, cols)), shape=(n, n))
        pattern.sort_indices()

        n_col = np.diff(pattern.indptr)
        col_of_entry = np.repeat(np.arange(n), n_col)
        by_group = np.argsort(groups[col_of_entry], kind="stable")
        counts = np.bincount(groups[col_of_entry], minlength=groups.max() + 1)
        members = [np.nonzero(groups == g)[0] for g in range(groups.max() + 1)]
        slices = np.split(by_group, np.cumsum(counts)[:-1])
        _COLOURINGS[key] = (pattern.indptr, pattern.indices, members, slices)
        return _COLOURINGS[key]

    def jacobian(self, x: np.ndarray) -> sp.csc_matrix:
        indptr, indices, members, slices = self._colouring()
        data = np.zeros(indices.size)
        R0 = self.residual(x, closure=False)
        trial = x.copy()
        for cols, entries in zip(members, slices):
            if cols.size == 0:
                continue
            trial[cols] += FD_STEP
            dR = (self.residual(trial, closure=False) - R0) / FD_STEP
            trial[cols] = x[cols]
            data[entries] = dR[indices[entries]]
        J = sp.csc_matrix((data, indices, indptr), shape=(self.n, self.n)).tocsr()
        J.eliminate_zeros()

        # closure row, analytic: d/dp[0, :] and d/dQ
        _, _, _, Q = self.unpack(x)
        cols = np.concatenate((self.n_ax + self.n_rad + np.arange(self.Nr), [self.n - 1]))
        vals = np.concatenate((self.w_in,
                               [self.alpha * Q / self.A_in ** 2 * self.s_Q / self.s_p]))
        row = sp.csr_matrix((vals, (np.zeros(cols.size, dtype=int), cols)), shape=(1, self.n))
        return sp.vstack((J[:-1, :], row), format="csc")


@dataclass
class FlowSolution:
    x: np.ndarray
    nu_t: np.ndarray
    converged: bool              # Newton reached its tolerance
    settled: bool                # the thrust stopped moving with nu_t
    residual: float
    newton_steps: int
    system: DuctSystem


def solve_newton(sys_: DuctSystem, x: np.ndarray, tol: float = 1e-9, max_steps: int = 80,
                 sigma0: float = 100.0, verbose: bool = False) -> Tuple[np.ndarray, float, int, bool]:
    """Pseudo-transient continuation at frozen nu_t.

    Plain Newton fails from a time-marched state: the limiter and the
    upwinding make R strongly non-linear in the near-wall cells, so the full
    step is far outside the region where the Jacobian holds. The momentum
    equations read dF/dt = R, so subtracting sigma from their diagonal is an
    implicit time step of 1/sigma (in units of R/U). sigma halves after every
    step that lowers the residual and grows after one that raises it too
    much, which turns the iteration into Newton at the end.
    """
    mom = np.zeros(sys_.n)
    mom[:sys_.n_ax + sys_.n_rad] = 1.0
    D = sp.diags(mom, format="csc")
    R = sys_.residual(x)
    norm = float(np.linalg.norm(R, np.inf))
    sigma = sigma0
    J = None
    for k in range(max_steps):
        if norm < tol:
            return x, norm, k, True
        if J is None:
            J = sys_.jacobian(x)
        step = spla.splu((J - sigma * D).tocsc()).solve(-R)
        step *= min(1.0, MAX_STEP / float(np.abs(step).max()))
        trial = x + step
        R_t = sys_.residual(trial)
        n_t = float(np.linalg.norm(R_t, np.inf))
        if verbose:
            w = int(np.argmax(np.abs(R_t)))
            print(f"    step {k:2d}: |R| {norm:.3e} -> {n_t:.3e}, sigma {sigma:.2e}, worst eq {w}", flush=True)
        if not math.isfinite(n_t) or n_t > 1.2 * norm:
            sigma *= 4.0
            if sigma > 1e8:
                return x, norm, k, False
            continue
        x, R, J = trial, R_t, None
        sigma = max(0.5 * sigma, 1e-8) if n_t < norm else sigma
        norm = n_t
    return x, norm, max_steps, norm < tol


def time_march_start(mesh: FVMesh, case: PropulsionCase, sys_: DuctSystem, Q: float,
                     iters: int = 15000, verbose: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Rough steady field from the time-marching solver, as a first guess."""
    R_in = float(mesh.R_f[0])
    v_in = Q / (math.pi * R_in ** 2)
    cfg = SimpleNamespace(
        rho=case.rho, nu=case.nu, cfl=0.6, time_step="local", tol=1e-4, max_iter=iters,
        v_inlet=v_in, R_inlet=R_in, Re_D=v_in * 2.0 * R_in / case.nu,
        v_throat=case.V_jet_ideal, turbulence_model=case.turbulence_model, p_inlet=0.0,
        inlet_flat=FLAT_INLET)
    res = solve_fv(mesh, cfg, verbose=verbose, body_force=sys_.force)
    x = sys_.pack(res.F_ax, res.F_rad, res.p - res.p_outlet, Q)
    x[sys_.n_ax + sys_.n_rad:-1] /= case.rho
    return x, res.nu_t


def solve_flow(sys_: DuctSystem, x: np.ndarray, nu_t: np.ndarray, relax: float = 0.5,
               outer: int = 30, tol_T: float = 1e-5, sigma0: float = 100.0,
               verbose: bool = False) -> FlowSolution:
    """Newton at frozen nu_t, updating nu_t between Newton solves.

    The algebraic model does not settle on its own. Where the switch between
    its inner and outer layer sits on the edge, a cell flips from one to the
    other and back at every update, and the thrust keeps alternating between
    two values. It works like a relay, so the update is made smaller and
    smaller after the first few passes: the cell then comes to rest at the
    switching value, which moves continuously with the shape.

    The returned nu_t is the one the returned state was solved with.
    """
    case, mesh = sys_.case, sys_.mesh
    T_old = None
    ok, settled, norm, steps = False, False, float("inf"), 0
    used = nu_t
    laminar = case.turbulence_model == "laminar"
    for k in range(1 if laminar else outer):
        used = nu_t
        sys_.set_nu_t(used)
        # after the first pass the state is close, so the steps can start larger
        x, norm, s, ok = solve_newton(sys_, x, sigma0=sigma0 if k == 0 else min(sigma0, 0.1),
                                      verbose=verbose)
        steps += s
        T = thrust(sys_, x)
        if verbose:
            print(f"  outer {k:2d}: T = {T:.6f} N, Newton {'ok' if ok else 'FAILED'}", flush=True)
        if not ok:
            break
        if laminar or (T_old is not None and abs(T - T_old) < tol_T * abs(T)):
            settled = True
            break
        T_old = T
        uz, ur = sys_.velocities(x)
        r = relax * RELAX_DECAY ** max(0, k - RELAX_KEEP)
        nu_t = (1.0 - r) * used + r * compute_nu_t(uz, ur, mesh, case.nu, case.turbulence_model)
    return FlowSolution(x=x, nu_t=used, converged=ok, settled=settled, residual=norm,
                        newton_steps=steps, system=sys_)


def thrust(sys_: DuctSystem, x: np.ndarray) -> float:
    """Net thrust [N] of the state x."""
    F_ax, _, _, Q = sys_.unpack(x)
    return thrust_from_fluxes(F_ax[-1, :], sys_.mesh.A_ax[-1, :], Q, sys_.case.V0,
                              sys_.case.rho)


def momentum_balance(sys_: DuctSystem, x: np.ndarray) -> float:
    """Thrust [N] from the forces instead of the exit jet.

    Sums what pushes the fluid along z: disk, wall pressure, wall friction
    and the inlet stream. It shares no formula with thrust(), so comparing
    the two checks the whole solution.
    """
    m = sys_.mesh
    case = sys_.case
    rho = case.rho
    F_ax, _, p, Q = sys_.unpack(x)
    uz, _ = sys_.velocities(x)
    disk = rho * float(np.sum(sys_.force * m.vol))
    wall_p = rho * float(np.sum(p[:, -1] * math.pi * np.diff(m.R_f ** 2)))
    friction = -rho * case.nu * float(np.sum(sys_.cw1 * uz[:, -1] + sys_.cw2 * uz[:, -2]))
    inlet_p = rho * float(np.sum(sys_.w_in * p[0, :])) * sys_.A_in
    inlet_m = rho * float(np.sum(F_ax[0, :] ** 2 / m.A_ax[0, :]))
    return disk + wall_p + friction + inlet_p + inlet_m - rho * Q * case.V0


def adjoint_gradients(sol: FlowSolution, functions: Dict[str, Callable],
                      build_system: Callable[[np.ndarray], DuctSystem],
                      design: np.ndarray, steps: np.ndarray) -> Dict[str, np.ndarray]:
    """Total derivative of each function with respect to the design vector.

    Args:
        sol: converged flow of the shape `design`.
        functions: name -> f(system, state). Each costs one back-substitution.
        build_system: design vector -> DuctSystem on the new grid.
        design: current design vector.
        steps: finite-difference step of every design variable.
    """
    base = sol.system
    base.set_nu_t(sol.nu_t)
    x = sol.x
    lu = spla.splu(base.jacobian(x))

    lambdas = {}
    for name, f in functions.items():
        df = np.zeros(base.n)
        trial = x.copy()
        for k in range(base.n):     # central: a sharp KS bends within one step
            trial[k] = x[k] + FD_STATE
            up = f(base, trial)
            trial[k] = x[k] - FD_STATE
            df[k] = (up - f(base, trial)) / (2.0 * FD_STATE)
            trial[k] = x[k]
        lambdas[name] = lu.solve(df, trans="T")

    grads = {name: np.zeros(design.size) for name in functions}
    for k in range(design.size):
        systems = []
        for sign in (1.0, -1.0):
            d = design.copy()
            d[k] += sign * steps[k]
            s = build_system(d)
            s.set_nu_t(sol.nu_t)
            systems.append(s)
        dR = (systems[0].residual(x) - systems[1].residual(x)) / (2.0 * steps[k])
        for name, f in functions.items():
            df_dx = (f(systems[0], x) - f(systems[1], x)) / (2.0 * steps[k])
            grads[name][k] = df_dx - float(lambdas[name] @ dR)
    return grads
