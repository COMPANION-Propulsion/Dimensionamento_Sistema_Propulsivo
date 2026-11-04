"""Whole chain: input file, thrust, dp loop, report and output files."""
import argparse
import json
import os

import numpy as np
import pytest

from conftest import make_case
from venturi_designer.cli import (GRID_LEVELS, load_case, load_inputs, run_target_thrust,
                                  thrust_target)
from venturi_designer.optimization.shape_opt import DuctProblem, initial_design, optimise, report
from venturi_designer.optimization.target_thrust import (load_design, match_thrust, save_design)

INPUT = """
CASO = dict(nome="prova", sovrascrivi=True)
SPINTA = dict(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
VENTURI = dict(fluid="air_20C", V0=0.0, p_amb=101325.0, T_ugello=T_VALUE, D_ext_max=0.07,
               L_max=0.15, gap_parete=0.005, spessore_parete=0.002, L_disk=0.01,
               D_disk_min_ratio=0.4, P_max=None, grid="medium", jobs=3, max_iter=2,
               n_up=4, n_down=5, tol_dp=0.05, max_cicli_dp=1)
"""


def write_input(tmp_path, T="0.2"):
    path = tmp_path / "input.py"
    path.write_text(INPUT.replace("T_VALUE", T))
    return str(path)


def test_input_file_is_read(tmp_path):
    case, inputs = load_case(write_input(tmp_path), 0.2)
    assert case.T_target == 0.2 and inputs["max_iter"] == 2
    assert case.R_int_max == pytest.approx(0.03)


def test_missing_input_is_named(tmp_path):
    path = tmp_path / "input.py"
    path.write_text("VENTURI = dict(fluid='air_20C')")
    with pytest.raises(ValueError, match="D_ext_max"):
        load_inputs(str(path))


def test_input_file_without_dictionary(tmp_path):
    path = tmp_path / "input.py"
    path.write_text("x = 1")
    with pytest.raises(ValueError, match="VENTURI"):
        load_inputs(str(path))


def test_project_input_file_loads():
    case, _ = load_case(os.path.join(os.path.dirname(__file__), "..", "..", "input.py"), 0.2)
    assert 0.0 < case.R_min < case.R_int_max < case.R_ext


def test_unknown_grid_is_refused(tmp_path):
    path = tmp_path / "input.py"
    path.write_text(INPUT.replace("T_VALUE", "0.2").replace('"medium"', '"huge"'))
    with pytest.raises(ValueError, match="coarse"):
        load_inputs(str(path))


def test_thrust_comes_from_the_thrust_step(tmp_path):
    path = write_input(tmp_path, "None")
    res = str(tmp_path / "risultati")
    with pytest.raises(ValueError, match="0_spinta"):
        thrust_target(load_inputs(path), path, res)
    out = tmp_path / "risultati" / "prova" / "1_spinta"
    (out / "spinta.json").write_text(json.dumps({"T_ugello_N": 0.123}))
    T, source = thrust_target(load_inputs(path), path, res)
    assert T == 0.123 and "spinta.json" in source


def test_number_in_input_overrides_the_thrust_step(tmp_path):
    path = write_input(tmp_path, "0.31")
    assert thrust_target(load_inputs(path), path, str(tmp_path / "r"))[0] == 0.31


def test_optimisation_raises_thrust_inside_the_limits():
    case = make_case()
    layout, d0 = initial_design(case)
    problem = DuctProblem(case, layout)
    res = optimise(problem, d0, max_iter=8, verbose=False)
    assert res.thrust > res.thrust_start
    assert problem.geometric(res.design).min() > -1e-3
    assert problem.values(res.design)["separation"] > -1e-3
    assert problem.geometry(res.design).L_total <= case.L_max * (1 + 1e-6)


def test_power_limit_is_respected():
    free = make_case()
    layout, d0 = initial_design(free)
    P_start = report(DuctProblem(free, layout), d0)["power"]
    case = make_case(P_max=1.02 * P_start)
    problem = DuctProblem(case, layout)
    res = optimise(problem, d0, max_iter=6, verbose=False)
    assert report(problem, res.design)["power"] <= case.P_max * (1 + 1e-3)


def test_secant_reaches_the_thrust():
    case = make_case(D_ext_max=0.07, L_max=0.15, L_disk=0.01, dp_disk=40.0)
    layout, d = initial_design(case)
    problem = DuctProblem(case, layout)
    T0 = problem.values(d)["thrust"]
    problem, rows, k = match_thrust(problem, d, 1.5 * T0, verbose=False)
    # this starting shape separates: T(dp) is noisy by about 1 %
    assert problem.values(d)["thrust"] == pytest.approx(1.5 * T0, rel=1e-2)
    assert 0.5 <= k <= 2.0         # T ~ dp^k, k = 1 for a lossless disk


def test_design_file_round_trip(tmp_path):
    case = make_case(D_ext_max=0.07, L_max=0.15, L_disk=0.01, dp_disk=37.5, T_target=0.2)
    layout, d = initial_design(case, 4, 5)
    path = save_design(str(tmp_path / "design.json"), case, layout, d)
    case2, layout2, d2 = load_design(path)
    assert case2.dp_disk == 37.5 and case2.T_target == 0.2 and layout2 == layout
    assert np.array_equal(d2, d)


@pytest.mark.slow
def test_command_line_run_writes_the_files(tmp_path, monkeypatch):
    monkeypatch.setitem(GRID_LEVELS, "medium",
                        dict(optimise=[(64, 26)], verify=[(64, 26), (90, 36), (128, 51)]))
    path = write_input(tmp_path, "0.2")
    root = tmp_path / "out"
    args = argparse.Namespace(input=path, output_dir=str(root), results_dir=str(tmp_path / "r"))
    assert run_target_thrust(args) in (0, 3)       # 3: grid study or envelope warning
    res = json.loads((root / "00_sintesi" / "risultati.json").read_text(encoding="utf-8"))
    assert res["ventola"]["dp_disk_Pa"] > 0.0
    assert res["spinta"]["calcolata_N"] == pytest.approx(0.2, rel=2e-3)
    assert res["geometria"]["ingombro_rispettato"]
    assert res["numerica"]["STL_chiusi"]
    for f in ("00_sintesi/RISULTATO.md", "01_grafici/geometria.svg",
              "01_grafici/campo_pressione_totale.svg", "01_grafici/profili_assiali.svg",
              "02_excel/venturi_risultati.xlsx", "03_cad/tubo.step", "03_cad/fluido.stl",
              "03_cad/fluido_parete.stl", "04_cfd/venturi_cfd_2d.vts", "04_cfd/venturi_pointcloud.csv",
              "05_convergenza/design.json", "05_convergenza/iterazioni_dp.json",
              "05_convergenza/grid_study.md"):
        assert (root / f).is_file(), f
