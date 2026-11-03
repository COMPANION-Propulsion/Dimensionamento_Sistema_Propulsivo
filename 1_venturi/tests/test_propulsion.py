"""Physics of the duct: disk, thrust and limits that theory fixes."""
import math

import numpy as np
import pytest

from conftest import make_case
from venturi_designer.core.propulsion import disk_force, thrust_from_fluxes
from venturi_designer.geometry import MorphedGeometry, MorphLayout
from venturi_designer.optimization.adjoint import momentum_balance, thrust
from venturi_designer.optimization.shape_opt import DuctProblem, initial_design, report
from venturi_designer.solver.fvmesh import build_fvmesh


def test_disk_force_integrates_to_the_pressure_rise():
    lay = MorphLayout(L_section=0.04)
    d = np.r_[np.full(lay.n_up, 0.06), np.full(lay.n_down, 0.06), 0.05, 0.1, 0.3]
    g = MorphedGeometry(lay, d)
    m = build_fvmesh(g, 64, 26, 2.7, 3.0, throat_ramp=1.5)
    rho, dp = 1.2, 1000.0
    f = disk_force(m, g.z_a + 0.01, g.z_a + 0.03, dp, rho)
    assert np.sum(f[:, 0] * np.diff(m.z_f)) == pytest.approx(dp / rho)
    assert np.ptp(f, axis=1).max() == 0.0


def test_disk_outside_the_grid_is_refused():
    lay = MorphLayout(L_section=0.04)
    d = np.r_[np.full(lay.n_up, 0.06), np.full(lay.n_down, 0.06), 0.05, 0.1, 0.3]
    m = build_fvmesh(MorphedGeometry(lay, d), 20, 10, 2.7, 1.0)
    with pytest.raises(ValueError):
        disk_force(m, 5.0, 6.0, 100.0, 1.2)


def test_thrust_formula():
    A = np.array([0.5, 0.5])
    F = np.array([1.0, 1.0])
    assert thrust_from_fluxes(F, A, 2.0, 0.0, 1.2) == pytest.approx(4.8)
    assert thrust_from_fluxes(F, A, 2.0, 1.0, 1.2) == pytest.approx(4.8 - 2.4)


def test_thrust_stays_below_the_ideal_limit(turbulent):
    problem, d = turbulent
    r = report(problem, d)
    assert 0.6 * r["ideal_thrust"] < r["thrust"] < r["ideal_thrust"]


def test_jet_and_forces_give_the_same_thrust(turbulent):
    problem, d = turbulent
    r = report(problem, d)
    assert r["thrust_from_forces"] == pytest.approx(r["thrust"], rel=0.02)


def test_duct_without_energy_makes_drag():
    case = make_case(V0=10.0, dp_disk=0.01)
    layout, d = initial_design(case)
    p = DuctProblem(case, layout)
    sol = p.solve(d)
    assert sol.converged
    assert thrust(sol.system, sol.x) < 0.0


def test_forward_speed_lowers_thrust():
    case = make_case(V0=15.0)
    layout, d = initial_design(case)
    p = DuctProblem(case, layout)
    sol = p.solve(d)
    assert sol.converged
    T = thrust(sol.system, sol.x)
    g = p.geometry(d)
    A = math.pi * g.R_exit ** 2
    ideal = case.rho * A * case.V_jet_ideal * (case.V_jet_ideal - case.V0)
    assert 0.0 < T < ideal
    assert momentum_balance(sol.system, sol.x) == pytest.approx(T, rel=0.03)
