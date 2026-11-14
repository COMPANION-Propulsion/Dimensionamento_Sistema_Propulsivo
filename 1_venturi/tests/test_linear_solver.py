"""PARDISO is the linear solver of the Newton steps and of the adjoint."""
import numpy as np
import pytest
import scipy.sparse as sp
import scipy.sparse.linalg as spla

pytest.importorskip("pypardiso")

from venturi_designer.optimization import adjoint                      # noqa: E402
from venturi_designer.optimization.adjoint import solve_newton, thrust  # noqa: E402


def _superlu(A):
    """The solver used before PARDISO (kept here as the reference)."""
    return spla.splu(A.tocsc())


def _small_matrix(n=40, seed=3):
    A = sp.random(n, n, density=0.15, random_state=seed, format="csc") + 5.0 * sp.eye(n, format="csc")
    return A


def test_solve_and_transposed_solve_match_dense():
    A = _small_matrix()
    b = np.random.default_rng(0).standard_normal(A.shape[0])
    dense = A.toarray()
    lu = adjoint.factorize(A)
    assert np.abs(lu.solve(b) - np.linalg.solve(dense, b)).max() < 1e-10
    assert np.abs(lu.solve(b, trans="T") - np.linalg.solve(dense.T, b)).max() < 1e-10
    # transposed flag is reset: a plain solve afterwards is still the plain one
    assert np.abs(lu.solve(b) - np.linalg.solve(dense, b)).max() < 1e-10


def test_newton_matches_superlu_within_tolerance(laminar, monkeypatch):
    problem, d = laminar
    sol = problem.solve(d)
    s = sol.system
    s.set_nu_t(sol.nu_t)
    x0 = sol.x * (1.0 + 1e-3 * np.cos(np.arange(sol.x.size)))
    new = solve_newton(s, x0.copy(), sigma0=1.0)
    monkeypatch.setattr(adjoint, "factorize", _superlu)
    old = solve_newton(s, x0.copy(), sigma0=1.0)
    assert new[3] and old[3]
    assert thrust(s, new[0]) == pytest.approx(thrust(s, old[0]), rel=1e-8)
    assert np.abs(new[0] - old[0]).max() < 1e-7


def test_adjoint_gradients_match_superlu(laminar, monkeypatch):
    problem, d = laminar
    new = problem.gradients(d)
    monkeypatch.setattr(adjoint, "factorize", _superlu)
    old = problem.gradients(d)
    for name in old:
        scale = np.abs(old[name]).max()
        assert np.abs(new[name] - old[name]).max() <= 1e-8 * scale
