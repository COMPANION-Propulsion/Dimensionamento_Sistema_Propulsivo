"""Whole chain: input file, optimisation, report and output files."""
import argparse
import json
import os

import pytest

from conftest import make_case
from venturi_designer.cli import GRID_LEVELS, export_duct, load_case, load_inputs, run_shape_optimisation
from venturi_designer.optimization.shape_opt import DuctProblem, initial_design, optimise, report

INPUT = """
VENTURI = dict(fluid="air_20C", V0=0.0, p_amb=101325.0, dp_disk=1000.0, D_disk=0.10,
               L_disk=0.02, z_disk=None, D_max=0.16, L_max=0.60, P_max=None,
               grid="medium", jobs=3, max_iter=2, n_up=4, n_down=5)
"""


def test_input_file_is_read(tmp_path):
    path = tmp_path / "input.py"
    path.write_text(INPUT)
    case, inputs = load_case(str(path))
    assert case.dp_disk == 1000.0 and inputs["max_iter"] == 2


def test_missing_input_is_named(tmp_path):
    path = tmp_path / "input.py"
    path.write_text("VENTURI = dict(fluid='air_20C')")
    with pytest.raises(ValueError, match="dp_disk"):
        load_inputs(str(path))


def test_input_file_without_dictionary(tmp_path):
    path = tmp_path / "input.py"
    path.write_text("x = 1")
    with pytest.raises(ValueError, match="VENTURI"):
        load_inputs(str(path))


def test_project_input_file_loads():
    case, _ = load_case(os.path.join(os.path.dirname(__file__), "..", "..", "input.py"))
    assert case.D_disk < case.D_max


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


def test_unknown_grid_is_refused(tmp_path):
    path = tmp_path / "input.py"
    path.write_text(INPUT.replace('"medium"', '"huge"'))
    with pytest.raises(ValueError, match="coarse"):
        load_inputs(str(path))


def test_command_line_run_writes_the_files(tmp_path, monkeypatch):
    monkeypatch.setitem(GRID_LEVELS, "medium",
                        dict(optimise=[(40, 18)], verify=[(40, 18), (56, 24), (80, 34)]))
    path = tmp_path / "input.py"
    path.write_text(INPUT)
    out = tmp_path / "out"
    args = argparse.Namespace(input=str(path), output_dir=str(out), no_export=False)
    assert run_shape_optimisation(args) == 0
    data = json.loads((out / "design.json").read_text())
    assert data["summary"]["thrust"] > 0.0
    assert (out / "history_40x18.json").exists()
    est = json.loads((out / "thrust_estimate.json").read_text())["estimate"]
    assert est["error"] >= 0.0 and est["value"] > 0.0
    assert est["grids"] == ["80x34", "56x24", "40x18"]
    assert isinstance(est["reliable"], bool)
    assert (out / "grid_study.md").exists()
    assert len(os.listdir(out)) > 3
