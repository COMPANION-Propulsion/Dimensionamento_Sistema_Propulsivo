"""Scan: geometric classification of the wall downstream of the disk (no flow solved)."""
import pytest

from conftest import make_case
from venturi_designer.geometry import MorphedGeometry, MorphLayout
from venturi_designer.optimization.scan import MAX_CONV_HALF_ANGLE, case_shape, half_angles_deg
from venturi_designer.optimization.shape_opt import inlet_radius_limit

R_FAN = 0.03


def angles(R_exit, L_diff):
    case = make_case()
    layout = MorphLayout(L_section=2.0 * case.L_disk)
    R_in = min(inlet_radius_limit(case), case.R_int_max)
    d = case_shape(case, layout, R_FAN, R_exit, L_diff, R_in)
    assert d is not None
    return half_angles_deg(MorphedGeometry(layout, d))


def test_steep_nozzle_is_converging_only():
    div, conv = angles(0.92 * R_FAN, 0.009)           # about 22 deg of closing
    assert div < 1.0
    assert 10.0 < conv < MAX_CONV_HALF_ANGLE


def test_steep_diffuser_is_diverging_only():
    div, conv = angles(1.5 * R_FAN, 0.009)            # far above any diffuser limit
    assert div > 30.0
    assert conv < 1.0


def test_gentle_diffuser_is_below_the_diffuser_limit():
    div, conv = angles(1.2 * R_FAN, 0.3)
    assert 0.5 < div < 4.0
    assert conv < 1.0
