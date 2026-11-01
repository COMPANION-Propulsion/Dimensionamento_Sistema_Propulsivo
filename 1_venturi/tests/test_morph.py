"""Morphing: shape, end conditions and what the grid makes of it."""
import numpy as np
import pytest

from conftest import make_case
from venturi_designer.geometry import MorphedGeometry, MorphLayout, fit_design
from venturi_designer.optimization.shape_opt import DuctProblem, initial_design
from venturi_designer.solver.fvmesh import build_fvmesh, divergence

LAYOUT = MorphLayout(R_disk=0.05, L_section=0.04)
DESIGN = np.r_[np.linspace(0.065, 0.052, LAYOUT.n_up), np.linspace(0.052, 0.062, LAYOUT.n_down),
               0.12, 0.40]


def test_fit_reproduces_a_shape_of_its_own_family():
    g = MorphedGeometry(LAYOUT, DESIGN)
    z, R = g.profile_points(4001)
    back = fit_design(LAYOUT, z, R, g.z_a, g.z_b)
    assert back == pytest.approx(DESIGN, abs=1e-6)


def test_disk_section_and_ends():
    g = MorphedGeometry(LAYOUT, DESIGN)
    z = np.linspace(g.z_a, g.z_b, 11)
    assert g.radius(z) == pytest.approx(0.05)
    assert g.radius_derivative(z) == pytest.approx(0.0, abs=1e-12)
    assert g.radius(0.0) == pytest.approx(DESIGN[0])
    assert g.radius(g.L_total) == pytest.approx(DESIGN[-3])
    assert g.radius_derivative(0.0) == pytest.approx(0.0, abs=1e-10)
    assert g.radius_derivative(g.L_total) == pytest.approx(0.0, abs=1e-10)


def test_wall_is_smooth_across_the_joints():
    g = MorphedGeometry(LAYOUT, DESIGN)
    for z in (g.z_a, g.z_b):
        e = 1e-7
        assert g.radius(z - e) == pytest.approx(g.radius(z + e), abs=1e-9)
        assert g.radius_derivative(z - e) == pytest.approx(g.radius_derivative(z + e), abs=1e-5)


def test_slope_is_the_derivative_of_the_radius():
    g = MorphedGeometry(LAYOUT, DESIGN)
    z = np.linspace(0.01, g.L_total - 0.01, 200)
    h = 1e-6
    fd = (g.radius(z + h) - g.radius(z - h)) / (2 * h)
    assert g.radius_derivative(z) == pytest.approx(fd, abs=1e-6)


def test_wall_segments_are_continuous():
    g = MorphedGeometry(LAYOUT, DESIGN)
    s = g.wall_segments()
    assert all(a.end == b.start for a, b in zip(s, s[1:]))
    assert s[0].start[0] == 0.0
    assert s[-1].end[0] == pytest.approx(g.L_total)


def test_uniform_flow_has_no_divergence_on_the_morphed_grid():
    g = MorphedGeometry(LAYOUT, DESIGN)
    m = build_fvmesh(g, 64, 26, 2.7, 3.0, throat_ramp=1.5)
    F_ax = m.A_ax.copy()
    F_rad = -m.Cz_rad.copy()
    F_rad[:, -1] = 0.0
    div = divergence(F_ax, F_rad, m)
    assert np.abs(div[:, :-1]).max() < 1e-13


def test_initial_design_respects_the_limits():
    case = make_case()
    layout, d = initial_design(case)
    assert DuctProblem(case, layout).geometric(d).min() >= 0.0
    assert np.all(d[:-2] >= layout.R_disk) and np.all(d[:-2] <= 0.5 * case.D_max)


def test_z_disk_places_the_disk_and_is_constrained():
    case = make_case(z_disk=0.4)
    layout, d = initial_design(case)
    p = DuctProblem(case, layout)
    g = p.geometry(d)
    assert 0.5 * (g.z_a + g.z_b) / g.L_total == pytest.approx(0.4)
    assert p.geometric(d).min() >= 0.0
    moved = d.copy()
    moved[-2] *= 1.3
    assert p.geometric(moved).min() < 0.0


def test_z_disk_out_of_range_is_refused():
    with pytest.raises(ValueError):
        make_case(z_disk=1.2)
