"""Morphing: shape, end conditions and what the grid makes of it."""
import numpy as np
import pytest
from scipy.interpolate import BSpline

from conftest import make_case
from venturi_designer.geometry import MorphedGeometry, MorphLayout, fit_design
from venturi_designer.optimization.shape_opt import DuctProblem, initial_design
from venturi_designer.solver.fvmesh import build_fvmesh, divergence

LAYOUT = MorphLayout(L_section=0.04)
DESIGN = np.r_[np.linspace(0.065, 0.052, LAYOUT.n_up), np.linspace(0.052, 0.062, LAYOUT.n_down),
               0.05, 0.12, 0.40]


def test_fit_reproduces_a_shape_of_its_own_family():
    g = MorphedGeometry(LAYOUT, DESIGN)
    z, R = g.profile_points(4001)
    back = fit_design(LAYOUT, z, R, g.z_a, g.z_b, 0.05)
    assert back == pytest.approx(DESIGN, abs=1e-6)


def test_disk_section_and_ends():
    g = MorphedGeometry(LAYOUT, DESIGN)
    z = np.linspace(g.z_a, g.z_b, 11)
    assert g.radius(z) == pytest.approx(0.05)
    assert g.radius_derivative(z) == pytest.approx(0.0, abs=1e-12)
    assert g.radius(0.0) == pytest.approx(DESIGN[0])
    assert g.radius(g.L_total) == pytest.approx(DESIGN[-4])
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


def test_bspline_curves_are_the_wall():
    g = MorphedGeometry(LAYOUT, DESIGN)
    for knots, poles in g.bspline_curves():
        pts = BSpline(knots, poles, 3)(np.linspace(0.0, 1.0, 301))
        assert pts[:, 1] == pytest.approx(g.radius(pts[:, 0]), abs=1e-12)


@pytest.mark.parametrize("size", [(0.17, 0.6), (0.07, 0.15), (0.05, 0.10), (0.04, 0.06)])
def test_initial_design_respects_the_limits(size):
    case = make_case(D_ext_max=size[0], L_max=size[1], L_disk=0.01)
    layout, d = initial_design(case)
    assert DuctProblem(case, layout).geometric(d).min() >= 0.0
    assert np.all(d[:-3] >= d[-3]) and np.all(d[:-3] <= case.R_int_max)
    assert case.R_min <= d[-3] <= case.R_int_max


def test_tube_envelope_is_a_constraint():
    case = make_case(D_ext_max=0.07, L_max=0.15, L_disk=0.01)
    layout, d = initial_design(case)
    p = DuctProblem(case, layout)
    wide = d.copy()
    wide[0] = case.R_int_max          # inlet at the inner limit: the bell mouth sticks out
    assert p.geometric(wide)[1] < 0.0
    long = d.copy()
    long[-1] += case.L_max
    assert p.geometric(long)[0] < 0.0


def test_fan_must_sit_in_the_throat():
    case = make_case()
    layout, d = initial_design(case)
    p = DuctProblem(case, layout)
    big = d.copy()
    big[-3] = d[:-3].min() + 0.002
    assert p.geometric(big).min() < 0.0
