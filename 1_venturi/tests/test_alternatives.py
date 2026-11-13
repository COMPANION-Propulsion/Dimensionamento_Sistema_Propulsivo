"""Alternatives at fixed length: pure geometry and bookkeeping, no flow solved."""
import numpy as np
import pytest

from conftest import make_case
from venturi_designer.export.cad import bell_envelope
from venturi_designer.geometry import MorphedGeometry, MorphLayout
from venturi_designer.optimization.alternatives import (ROW_KEYS, failed_row, lengths_from_input,
                                                         rescale_length)
from venturi_designer.optimization.scan import case_shape
from venturi_designer.optimization.shape_opt import inlet_radius_limit

R_FAN = 0.03


def setup():
    case = make_case(L_min=0.30)
    layout = MorphLayout(L_section=2.0 * case.L_disk)
    R_in = min(inlet_radius_limit(case), case.R_int_max)
    d = case_shape(case, layout, R_FAN, 1.3 * R_FAN, 0.25, R_in)
    assert d is not None
    return case, layout, d


def tube_length(case, layout, d):
    g = MorphedGeometry(layout, d)
    return g.L_total + bell_envelope(g.R_inlet, case.spessore_parete, case.raggio_bocca_su_D)[1]


@pytest.mark.parametrize("L", [0.40, 0.45, 0.55])
def test_rescale_gives_the_wanted_length_and_keeps_the_radii(L):
    case, layout, d = setup()
    d2 = rescale_length(layout, case, d, L)
    assert abs(tube_length(case, layout, d2) - L) < 1e-5
    assert np.array_equal(d2[:-2], d[:-2])
    assert d2 is not d and d2[-1] / d[-1] == pytest.approx(d2[-2] / d[-2])


def test_rescale_too_short_raises():
    case, layout, d = setup()
    with pytest.raises(ValueError):
        rescale_length(layout, case, d, 0.01)


def test_lengths_from_input():
    case = make_case(L_min=0.30, L_max=0.60)
    L = lengths_from_input(5, case)
    assert len(L) == 5 and L[0] == pytest.approx(0.30) and L[-1] == pytest.approx(0.60)
    assert lengths_from_input([0.5, 0.4], case) == [0.5, 0.4]
    assert lengths_from_input(None, case) == []
    assert lengths_from_input(0, case) == []
    assert lengths_from_input(3, make_case(L_max=0.5))[0] == pytest.approx(0.3)


def test_failed_row_has_every_key():
    row = failed_row("L130", 0.13, "non converge")
    assert set(row) == set(ROW_KEYS)
    assert row["convergito"] is False and row["stato"] == "non converge"
    assert row["L_tubo_mm"] == pytest.approx(130.0) and row["dp_Pa"] is None


def test_length_target_adds_two_constraints_and_allows_short_tubes():
    from venturi_designer.optimization.shape_opt import DuctProblem, initial_design
    base = make_case(L_disk=0.032, L_max=0.20, L_min=0.12)
    layout, d = initial_design(base, 4, 5)
    n0 = DuctProblem(base, layout).geometric(d).size
    short = make_case(L_disk=0.032, L_max=0.20, L_min=0.12, L_target=0.110)
    assert DuctProblem(short, layout).geometric(d).size == n0 + 2
    with pytest.raises(ValueError):
        make_case(L_target=0.9)
