"""The time-marching solver must give the numbers of the original code."""
import pytest

from venturi_designer import (VenturiConfig, build_fvmesh, create_venturi_geometry, solve_fv,
                              validate)

# Default case on the 90 x 36 grid, computed before any change to the solver.
REFERENCE = dict(iters=18556, Cd=0.9751020738869793, dp=6652.124512494367,
                 recovery=0.8868148104708974, p_sum=321122716.1941597,
                 uz_sum=4871.233948327525)


def test_default_case_is_unchanged():
    c = VenturiConfig()
    g = create_venturi_geometry(c)
    m = build_fvmesh(g, c.Nz, c.Nr, c.wall_clustering, c.throat_refine)
    r = solve_fv(m, c, verbose=False)
    rep = validate(r, m, g, c)
    assert r.converged
    assert r.n_iter == REFERENCE["iters"]
    assert rep.Cd == pytest.approx(REFERENCE["Cd"], rel=1e-10)
    assert rep.dp_measured == pytest.approx(REFERENCE["dp"], rel=1e-10)
    assert rep.pressure_recovery == pytest.approx(REFERENCE["recovery"], rel=1e-10)
    assert float(r.p.sum()) == pytest.approx(REFERENCE["p_sum"], rel=1e-10)
    assert float(r.uz.sum()) == pytest.approx(REFERENCE["uz_sum"], rel=1e-10)
