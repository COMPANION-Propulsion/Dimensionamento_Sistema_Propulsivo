"""Motion profiles, thrust and the results folder of the case."""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spinta_designer import Motion, caso, run

INPUT = """
CASO = dict(nome={nome!r}, sovrascrivi=False)
SPINTA = dict(distanza=2.0, tempo=8.0, massa=9.0, n_ugelli=3, profilo="bang_bang",
              frazione_crociera=0.0, fattore_margine=1.0)
VENTURI = dict(D_ext_max=0.07, L_max=0.15)
"""


def test_bang_bang_is_four_s_over_t_squared():
    m = Motion(distanza=2.0, tempo=8.0, massa=9.0, n_ugelli=3)
    assert m.acceleration == pytest.approx(4 * 2.0 / 8.0 ** 2)
    assert m.thrust_total == pytest.approx(9.0 * 0.125)
    assert m.thrust_nozzle == pytest.approx(9.0 * 0.125 / 3)


def test_trapezoid_tends_to_bang_bang():
    bb = Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
    tr = Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2, profilo="trapezio",
                frazione_crociera=1e-9)
    assert tr.thrust_nozzle == pytest.approx(bb.thrust_nozzle, rel=1e-6)


def test_coasting_needs_more_thrust():
    bb = Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
    tr = Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2, profilo="trapezio",
                frazione_crociera=0.5)
    assert tr.thrust_nozzle > bb.thrust_nozzle


@pytest.mark.parametrize("fc", [0.0, 0.3, 0.8])
def test_history_covers_the_distance_and_stops(fc):
    m = Motion(distanza=1.5, tempo=12.0, massa=5.0, n_ugelli=1, profilo="trapezio",
               frazione_crociera=fc)
    d = m.history(4001)
    assert d["s"][-1] == pytest.approx(1.5)
    assert d["v"][0] == 0.0 and d["v"][-1] == pytest.approx(0.0, abs=1e-12)
    assert np.trapezoid(d["v"], d["t"]) == pytest.approx(1.5, rel=1e-4)
    assert d["v"].max() == pytest.approx(m.v_max)


def test_margin_scales_the_thrust():
    a = Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
    b = Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2, fattore_margine=1.5)
    assert b.thrust_nozzle == pytest.approx(1.5 * a.thrust_nozzle)


def test_residual_disturbance_adds_to_the_thrust():
    kw = dict(distanza=0.15, tempo=5.0, massa=4.5, n_ugelli=2, fattore_margine=2.0)
    m = Motion(disturbo_residuo_g=0.01, **kw)
    assert m.thrust_total == pytest.approx(2 * 4.5 * (4 * 0.15 / 25 + 0.0980665))
    assert m.thrust_total == pytest.approx(1.0986, abs=1e-4)
    assert m.acceleration == pytest.approx(4 * 0.15 / 25)
    assert m.history()["T_ugello"].max() == pytest.approx(m.thrust_nozzle)
    # default 0 = free fall, as before
    assert Motion(**kw).thrust_total == pytest.approx(2 * 4.5 * 4 * 0.15 / 25)


def test_negative_disturbance_is_refused():
    with pytest.raises(ValueError):
        Motion(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2, disturbo_residuo_g=-0.01)


@pytest.mark.parametrize("kw", [dict(distanza=0.0), dict(tempo=-1.0), dict(n_ugelli=0),
                                dict(n_ugelli=1.5), dict(profilo="x"),
                                dict(profilo="trapezio", frazione_crociera=0.95)])
def test_bad_inputs_are_refused(kw):
    values = dict(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
    values.update(kw)
    with pytest.raises(ValueError):
        Motion(**values)


def test_run_writes_the_case_folder(tmp_path):
    path = tmp_path / "input.py"
    path.write_text(INPUT.format(nome=None))
    assert run(str(path), str(tmp_path / "risultati")) == 0
    (case,) = os.listdir(tmp_path / "risultati")
    assert case.startswith("m9kg_s2m_t8s_n3_bangbang_D70xL150mm_h")
    root = tmp_path / "risultati" / case
    data = json.loads((root / "1_spinta" / "spinta.json").read_text())
    assert data["T_ugello_N"] == pytest.approx(9.0 * 0.125 / 3)
    for f in ("caso.json", "input_usato.py", "1_spinta/RISULTATO.md",
              "1_spinta/grafici/moto.svg", "1_spinta/excel/spinta.xlsx"):
        assert (root / f).is_file(), f


def test_named_case_with_other_inputs_is_refused(tmp_path):
    path = tmp_path / "input.py"
    path.write_text(INPUT.format(nome="prova"))
    res = str(tmp_path / "risultati")
    caso.case_dir(str(path), res)
    path.write_text(INPUT.format(nome="prova").replace("massa=9.0", "massa=8.0"))
    with pytest.raises(ValueError, match="sovrascrivi"):
        caso.case_dir(str(path), res)


def test_overwrite_warns_about_old_steps(tmp_path, capsys):
    path = tmp_path / "input.py"
    text = INPUT.format(nome="prova").replace("sovrascrivi=False", "sovrascrivi=True")
    path.write_text(text)
    res = str(tmp_path / "risultati")
    root = caso.case_dir(str(path), res)
    os.makedirs(os.path.join(root, "2_venturi"))
    caso.case_dir(str(path), res)
    assert "WARNING" not in capsys.readouterr().out
    path.write_text(text.replace("massa=9.0", "massa=8.0"))
    caso.case_dir(str(path), res)
    out = capsys.readouterr().out
    assert "WARNING" in out and "2_venturi" in out and "3_ventola" not in out


def test_automatic_names_differ_when_inputs_differ(tmp_path):
    path = tmp_path / "input.py"
    path.write_text(INPUT.format(nome=None))
    a = caso.case_name(caso.load_input(str(path)))
    path.write_text(INPUT.format(nome=None).replace("L_max=0.15", "L_max=0.15, grid='fine'"))
    assert caso.case_name(caso.load_input(str(path))) != a
