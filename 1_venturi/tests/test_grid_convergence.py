"""Grid levels and the error estimate of the thrust."""
import pytest

from venturi_designer.analysis.grid_study import error_estimate, gci
from venturi_designer.core.propulsion import GRID_LEVELS


def test_exact_second_order_is_recovered():
    h = [1.0, 2.0 ** 0.5, 2.0]
    g = gci(h, [10.0 + 0.1 * x ** 2 for x in h])
    assert g.p == pytest.approx(2.0, abs=1e-6)
    assert g.phi_ext == pytest.approx(10.0, abs=1e-6)


def test_estimate_on_clean_data_is_trusted():
    h = [1.0, 2.0 ** 0.5, 2.0]
    est = error_estimate(h, [10.0 + 0.1 * x ** 2 for x in h])
    assert est["problems"] == []
    assert est["extrapolated"] == pytest.approx(10.0, abs=1e-6)
    assert est["asymptotic_ratio"] == pytest.approx(1.0, abs=0.02)


def test_error_band_covers_the_exact_value():
    h = [1.0, 1.4, 2.0]
    phi = [20.0 - 0.2 * x ** 1.7 for x in h]
    assert abs(phi[0] - 20.0) <= error_estimate(h, phi)["error"]


def test_oscillating_result_is_flagged_and_keeps_a_band():
    est = error_estimate([1.0, 1.4, 2.0], [10.0, 10.3, 10.1])
    assert est["problems"]
    assert est["error"] == pytest.approx(1.25 * 0.3)


def test_flat_result_is_grid_independent():
    est = error_estimate([1.0, 1.4, 2.0], [0.19993, 0.19993, 0.19998])
    assert est["problems"] == []
    assert est["error"] == pytest.approx(1.25 * 5e-5)


def test_grid_too_coarse_for_richardson_is_flagged():
    assert error_estimate([1.0, 1.4, 2.0], [10.0, 10.01, 11.0])["problems"]


@pytest.mark.parametrize("name", list(GRID_LEVELS))
def test_levels_are_valid(name):
    level = GRID_LEVELS[name]
    cells = [a * b for a, b in level["verify"]]
    assert len(cells) == 3 and cells == sorted(cells)
    for coarse, fine in zip(cells, cells[1:]):
        assert 1.3 < (fine / coarse) ** 0.5 < 1.6      # Celik et al.: r > 1.3
    assert level["optimise"][-1] == level["verify"][0]


def test_fine_is_the_finest():
    assert GRID_LEVELS["fine"]["verify"][-1][0] > GRID_LEVELS["medium"]["verify"][-1][0]
