"""Shared cases of the test suite."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from venturi_designer.core.propulsion import PropulsionCase
from venturi_designer.optimization.shape_opt import DuctProblem, initial_design


def make_case(**kw):
    values = dict(fluid="air_20C", V0=0.0, p_amb=101325.0, dp_disk=1000.0, D_disk=0.10,
                  L_disk=0.02, D_max=0.16, L_max=0.60)
    values.update(kw)
    return PropulsionCase(**values)


@pytest.fixture(scope="session")
def turbulent():
    """Air, static, Baldwin-Lomax, already solved."""
    case = make_case()
    layout, d = initial_design(case)
    problem = DuctProblem(case, layout)
    problem.solve(d)
    return problem, d


@pytest.fixture(scope="session")
def laminar():
    """Oil at Re about 3000, laminar: the adjoint here has no approximation."""
    case = make_case(fluid="oil_VG46", turbulence_model="laminar")
    layout, d = initial_design(case)
    problem = DuctProblem(case, layout)
    problem.solve(d)
    return problem, d
