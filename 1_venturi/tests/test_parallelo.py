"""Parallel scan / alternatives / exit scan and the pass without grid study. No flow is solved:
the solving functions are replaced by fakes and the process pool by a serial one."""
import os
import pickle
from concurrent.futures import Future
from types import SimpleNamespace

import numpy as np
import pytest

from conftest import make_case
from venturi_designer import cli, parallel
from venturi_designer.geometry import MorphLayout
from venturi_designer.optimization import alternatives, exit_sweep, scan
from venturi_designer.optimization.target_thrust import SizingResult


class SerialExecutor:
    def __init__(self, max_workers=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args):
        f = Future()
        try:
            f.set_result(fn(*args))
        except BaseException as e:
            f.set_exception(e)
        return f


@pytest.fixture
def serial_pool(monkeypatch):
    monkeypatch.setattr(parallel, "ProcessPoolExecutor", SerialExecutor)


def test_map_ordered_keeps_the_order(serial_pool):
    assert parallel.map_ordered(abs, [-3, 2, -1], 3) == [3, 2, 1]
    seen = []
    parallel.map_ordered(abs, [-3, 2], 2, on_done=lambda i, r: seen.append((i, r)))
    assert sorted(seen) == [(0, 3), (1, 2)]


# ---- scan --------------------------------------------------------------------------------

class FakeProblem:
    def __init__(self, case, layout):
        self.case = case
        self.sol = None

    def solve(self, d):
        return SimpleNamespace(converged=True)


def fake_solve_candidate(case, layout, d, curve, P_max, row, prev_sol=None):
    """Thrust grows with the exit diameter; the case with the largest exit and L_diff 2 is chosen."""
    row.update(stato="ok", spinta_N=row["D_uscita_mm"] * 1e-3 + 1e-6 * row["L_diffusore_mm"],
               dp_Pa=case.dp_disk, Q_m3_s=1.0, potenza_W=1.0, L_tubo_mm=100.0,
               tau_w_min_diffusore_Pa=1.0, celle_invertite=0)
    return row, FakeProblem(case, layout), SimpleNamespace(tag="sol")


def run(procs, monkeypatch, tmp_path):
    monkeypatch.setattr(scan, "solve_candidate", fake_solve_candidate)
    monkeypatch.setattr(scan, "DuctProblem", FakeProblem)
    case = make_case(L_min=0.1, D_ext_max=0.07, L_max=0.16, L_disk=0.03)
    layout = MorphLayout(L_section=2.0 * case.L_disk)
    return scan.run_scan(case, layout, (64, 26), None, 0.04, 3, 2, 5.0, None, str(tmp_path),
                         verbose=False, procs=procs)


def test_parallel_scan_gives_the_same_table_and_best(monkeypatch, tmp_path, serial_pool):
    seq = run(1, monkeypatch, tmp_path)
    par = run(3, monkeypatch, tmp_path)
    assert par["casi"] == seq["casi"] and par["migliore"] == seq["migliore"]
    assert [r["stato"] for r in par["casi"]] == [r["stato"] for r in seq["casi"]]
    assert np.array_equal(par["design"], seq["design"])
    assert par["problem"].case.dp_disk == seq["problem"].case.dp_disk


def test_scan_worker_is_picklable_and_returns_the_row(monkeypatch):
    monkeypatch.setattr(scan, "solve_candidate", fake_solve_candidate)
    case = make_case()
    layout = MorphLayout(L_section=0.04)
    payload = (case, layout, np.zeros(4), None, None, dict(D_uscita_mm=50.0, L_diffusore_mm=20.0))
    pickle.loads(pickle.dumps(payload))
    assert pickle.loads(pickle.dumps(scan.scan_worker)) is scan.scan_worker
    row = scan.scan_worker(payload)
    assert {"D_uscita_mm", "L_diffusore_mm", "stato", "spinta_N", "dp_Pa", "tau_w_min_diffusore_Pa"} <= set(row)


# ---- alternatives and exit scan ------------------------------------------------------------

def test_alternative_worker_is_picklable_and_gives_a_failed_row_with_all_keys():
    assert pickle.loads(pickle.dumps(alternatives.alternative_worker)) is alternatives.alternative_worker
    ref = alternatives.failed_row("ottimo", None, "x")          # dp_Pa None: no reference
    case = make_case(L_max=0.2, T_target=0.5)
    payload = (case, MorphLayout(L_section=0.04), np.zeros(4), 0.1, (64, 26), 2, 40, 0.01, ".", ref)
    pickle.loads(pickle.dumps(payload))
    row = alternatives.alternative_worker(payload)
    assert set(row) == set(alternatives.ROW_KEYS) and row["id"] == "L100"


def test_parallel_alternatives_keep_the_order_of_the_lengths(monkeypatch, tmp_path, serial_pool):
    monkeypatch.setattr(alternatives, "compare_row",
                        lambda p, d, T, ref=None: dict(alternatives.failed_row("ottimo", 1.0, "ok"),
                                                       dp_Pa=1.0, potenza_W=1.0))
    monkeypatch.setattr(alternatives, "_save_files", lambda *a, **k: None)
    monkeypatch.setattr(alternatives, "_solve_one",
                        lambda *a, **k: (None, "nessuna prova"))
    case = make_case(L_max=0.2, T_target=0.5)
    args = (case, MorphLayout(L_section=0.04), np.zeros(4), SimpleNamespace(), [0.1, 0.15, 0.3],
            (64, 26))
    seq = alternatives.run_alternatives(*args, out_dir=str(tmp_path / "s"), verbose=False)
    par = alternatives.run_alternatives(*args, out_dir=str(tmp_path / "p"), verbose=False, procs=3)
    assert [r["id"] for r in par["casi"]] == ["ottimo", "L100", "L150", "L300"]
    assert par["casi"] == seq["casi"]


def test_sweep_worker_is_picklable():
    assert pickle.loads(pickle.dumps(exit_sweep.sweep_worker)) is exit_sweep.sweep_worker


def test_parallel_exit_sweep_gives_the_same_rows(monkeypatch, tmp_path, serial_pool):
    layout = MorphLayout(L_section=0.04, n_up=2, n_down=2)
    d_opt = np.array([0.03, 0.03, 0.032, 0.036, 0.03, 0.02, 0.05])
    case = make_case(T_target=0.5, L_max=0.2)
    ref_problem = SimpleNamespace(case=case, sol=None)

    def fake_point(s, case_g, layout, d_opt, T, ref, max_half_angle, prev_sol, verbose):
        return dict(id=exit_sweep.sweep_id(s), s=float(s), stato="ok"), prev_sol

    monkeypatch.setattr(exit_sweep, "sweep_point", fake_point)
    monkeypatch.setattr(exit_sweep, "compare_row", lambda *a, **k: dict(id="x"))
    monkeypatch.setattr(exit_sweep, "for_grid", lambda c, *g: c)
    args = (case, layout, d_opt, ref_problem, 5, (64, 26))
    seq = exit_sweep.run_exit_sweep(*args, str(tmp_path / "s"), 5.0, verbose=False)
    par = exit_sweep.run_exit_sweep(*args, str(tmp_path / "p"), 5.0, verbose=False, procs=4)
    assert par["punti"] == seq["punti"]


# ---- pass without grid study -----------------------------------------------------------------

def test_skip_extras_skips_the_grid_study_but_matches_the_finest_grid(monkeypatch, tmp_path):
    case = make_case(T_target=0.5, L_max=0.16)
    layout = MorphLayout(L_section=0.04)
    d = np.zeros(4)
    inputs = dict(fluid="air_20C", grid="coarse", ottimizzatore="griglia")
    seen = {}

    class P:
        def __init__(self, c, l):
            self.case, self.layout = c, l

    def match(problem, design, T, exponent=1.0, cycle=0, **k):
        seen["grid"] = (problem.case.Nz, problem.case.Nr)
        seen["dp"] = problem.case.dp_disk
        return problem, [dict(spinta=T)], 1.0

    def no_study(*a, **k):
        raise AssertionError("duct_study must not run in an intermediate pass")

    summary = dict(thrust=0.5, Q=1.0, power=1.0)
    results = dict(ventola=dict(D_ventola_m=0.05, portata_m3_s=1.0, potenza_fluido_W=1.0),
                   geometria=dict(D_esterno_tubo_mm=70.0, L_tubo_mm=100.0, ingombro_rispettato=True))
    exported = {}

    def export(fine, design, summ, dirs, info):
        exported.update(info)
        return dict(results=results, files=[])

    coarse_case = case
    base = SizingResult(problem=P(coarse_case, layout), design=d, steps=[], exponent=1.0,
                        converged=True)
    monkeypatch.setattr(cli, "load_inputs", lambda p: inputs)
    monkeypatch.setattr(cli, "thrust_target", lambda *a: (0.5, "test"))
    monkeypatch.setattr(cli, "load_case", lambda p, T: (case, inputs))
    monkeypatch.setattr(cli, "initial_design", lambda *a: (layout, d))
    monkeypatch.setattr(cli, "scan_sizing", lambda *a, **k: (base, None))
    monkeypatch.setattr(cli, "duct_study", no_study)
    monkeypatch.setattr(cli, "DuctProblem", P)
    monkeypatch.setattr(cli, "match_thrust", match)
    monkeypatch.setattr(cli, "save_design", lambda *a, **k: "design.json")
    monkeypatch.setattr(cli, "report", lambda *a: summary)
    monkeypatch.setattr(cli, "export_duct_results", export)
    monkeypatch.setattr(cli, "optimisation_history", lambda *a: None)
    args = SimpleNamespace(input="x", output_dir=str(tmp_path), no_export=False, skip_extras=True,
                           procs=3)
    assert cli.run_target_thrust(args) == 0
    assert seen["grid"] == cli.GRID_LEVELS["coarse"]["verify"][-1]
    assert seen["dp"] == base.problem.case.dp_disk          # starts from the dp of the optimise grid
    assert np.isnan(exported["dp_error"])
    assert cli.GRID_STUDY_SKIPPED in exported["estimate"]["notes"]


def test_final_pass_still_runs_the_grid_study(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(cli, "duct_study", lambda *a: called.append(a) or (_ for _ in ()).throw(
        StopIteration))
    monkeypatch.setattr(cli, "load_inputs", lambda p: dict(grid="coarse", ottimizzatore="slsqp"))
    case = make_case(T_target=0.5)
    layout = MorphLayout(L_section=0.04)
    monkeypatch.setattr(cli, "thrust_target", lambda *a: (0.5, "t"))
    monkeypatch.setattr(cli, "load_case", lambda p, T: (case, dict(grid="coarse", ottimizzatore="slsqp")))
    monkeypatch.setattr(cli, "initial_design", lambda *a: (layout, np.zeros(4)))
    monkeypatch.setattr(cli, "size_for_thrust", lambda *a, **k: SizingResult(
        problem=SimpleNamespace(case=case), design=np.zeros(4), steps=[], converged=True))
    monkeypatch.setattr(cli, "save_design", lambda *a, **k: "d.json")
    monkeypatch.setattr(cli, "report", lambda *a: {})
    args = SimpleNamespace(input="x", output_dir=str(tmp_path), no_export=False, skip_extras=False,
                           procs=2)
    with pytest.raises(StopIteration):
        cli.run_target_thrust(args)
    assert called and called[0][2] == min(3, 2)            # jobs capped by the budget
