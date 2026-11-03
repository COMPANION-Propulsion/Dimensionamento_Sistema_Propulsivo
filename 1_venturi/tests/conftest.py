"""Shared cases of the test suite."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from venturi_designer.core.config import VenturiConfig
from venturi_designer.core.propulsion import PropulsionCase
from venturi_designer.geometry import MorphLayout, VenturiGeometry, fit_design
from venturi_designer.optimization.shape_opt import DuctProblem


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: whole chain, several minutes (-m 'not slow' skips it)")


def make_case(**kw):
    values = dict(fluid="air_20C", V0=0.0, p_amb=101325.0, dp_disk=1000.0, D_ext_max=0.17,
                  L_disk=0.02, L_max=0.60)
    values.update(kw)
    return PropulsionCase(**values)


def reference_design(case, D_disk=0.10, n_up=5, n_down=8):
    """The fixed duct the solver checks were tuned on: a 30 deg / 5 deg Venturi
    with a 100 mm disk, fitted with the splines (the starting shape of the
    optimiser has changed since, this one stays)."""
    D_in = 1.25 * D_disk
    L_section = 2.0 * case.L_disk
    cfg = VenturiConfig(D=D_in, beta=D_disk / D_in, alpha_conv_deg=30.0, alpha_div_deg=5.0,
                        L_inlet_ratio=0.15, L_throat_ratio=L_section / D_disk,
                        L_outlet_ratio=0.15, fluid=case.fluid, p_throat_target=None,
                        v_inlet=1.0)
    geom = VenturiGeometry(cfg)
    z, R = geom.profile_points(1200)
    layout = MorphLayout(L_section=L_section, n_up=n_up, n_down=n_down)
    d = fit_design(layout, z, R, float(geom.z_stations[2]), float(geom.z_stations[3]),
                   0.5 * D_disk)
    d[:-3] = np.clip(d[:-3], 0.5 * D_disk, case.R_int_max)
    return layout, d


@pytest.fixture(scope="session")
def turbulent():
    """Air, static, Baldwin-Lomax, already solved."""
    case = make_case()
    layout, d = reference_design(case)
    problem = DuctProblem(case, layout, Re_ref=case.V_jet_ideal * 0.10 / case.nu)
    problem.solve(d)
    return problem, d


@pytest.fixture(scope="session")
def laminar():
    """Oil at Re about 3000, laminar: the adjoint here has no approximation."""
    case = make_case(fluid="oil_VG46", turbulence_model="laminar")
    layout, d = reference_design(case)
    problem = DuctProblem(case, layout, Re_ref=case.V_jet_ideal * 0.10 / case.nu)
    problem.solve(d)
    return problem, d
