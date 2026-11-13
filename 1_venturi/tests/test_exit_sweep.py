"""Exit sweep: geometry of the family and the re-ordering of the history, no flow solved."""
import json

import numpy as np
import pytest

from conftest import make_case
from venturi_designer.geometry import MorphedGeometry, MorphLayout
from venturi_designer.optimization.exit_sweep import (SWEEP_KEYS, _failed, exit_family,
                                                       optimisation_history, s_range)
from venturi_designer.optimization.scan import case_shape
from venturi_designer.optimization.shape_opt import inlet_radius_limit

R_FAN = 0.03


def setup(exit_factor=1.3):
    case = make_case(L_min=0.30)
    layout = MorphLayout(L_section=2.0 * case.L_disk)
    R_in = min(inlet_radius_limit(case), case.R_int_max)
    d = case_shape(case, layout, R_FAN, exit_factor * R_FAN, 0.25, R_in)
    assert d is not None
    return case, layout, d


def r_exit(layout, d):
    return MorphedGeometry(layout, d).R_exit


def test_s_one_returns_the_design():
    _, layout, d = setup()
    assert np.array_equal(exit_family(layout, d, 1.0), d)


def test_only_the_diffuser_changes():
    _, layout, d = setup()
    d2 = exit_family(layout, d, 0.5)
    n = layout.n_up
    assert np.array_equal(d2[:n], d[:n]) and np.array_equal(d2[-3:], d[-3:])
    assert not np.array_equal(d2, d) and d2 is not d


def test_negative_s_converges_below_the_disk():
    _, layout, d = setup()
    assert r_exit(layout, exit_family(layout, d, -0.5)) < d[-3]
    assert r_exit(layout, exit_family(layout, d, 0.0)) == pytest.approx(d[-3])


@pytest.mark.parametrize("factor", [1.3, 1.0])
def test_exit_radius_is_monotone_in_s(factor):
    case, layout, d = setup(factor)       # factor 1.0: degenerate straight diffuser
    s = np.linspace(-1.0, 3.0, 9)
    R = [r_exit(layout, exit_family(layout, d, v)) for v in s]
    assert all(b > a for a, b in zip(R, R[1:]))


def test_s_range_has_one_and_the_extremes():
    case, layout, d = setup()
    vals = s_range(case, d, 7)
    assert 1.0 in vals and vals == sorted(vals) and len(vals) in (7, 8)
    assert r_exit(layout, exit_family(layout, d, vals[0])) == pytest.approx(0.85 * R_FAN)
    assert r_exit(layout, exit_family(layout, d, vals[-1])) == pytest.approx(case.R_int_max)


def test_failed_row_has_every_key():
    row = _failed(-0.5, "no")
    assert set(row) == set(SWEEP_KEYS) and row["s"] == -0.5 and row["dp_Pa"] is None
    assert row["id"] == "s-0.50" and row["convergito"] is False


def test_optimisation_history_order(tmp_path):
    def hist(c, grid, n):
        h = [dict(iteration=i + 1, thrust=0.1 * i, D_disk=0.06, D_exit=0.08 + 0.001 * i,
                  L_total=0.2, violation=0.0) for i in range(n)]
        (tmp_path / f"history_c{c}_{grid}.json").write_text(json.dumps(dict(design=[], history=h)))
    hist(1, "64x26", 2)
    hist(1, "90x36", 1)
    hist(2, "90x36", 1)
    steps = [dict(ciclo=1, tipo="scansione", griglia="90x36", dp_disk=5.0, spinta=0.1),
             dict(ciclo=1, tipo="ottimizzazione", griglia="64x26", dp_disk=4.0, spinta=0.1),
             dict(ciclo=1, tipo="ottimizzazione", griglia="90x36", dp_disk=4.0, spinta=0.1),
             dict(ciclo=1, tipo="secante", griglia="90x36", dp_disk=4.2, spinta=0.2),
             dict(ciclo=2, tipo="ottimizzazione", griglia="90x36", dp_disk=4.2, spinta=0.2),
             dict(ciclo=2, tipo="secante", griglia="90x36", dp_disk=4.3, spinta=0.2),
             dict(ciclo=0, tipo="finale", griglia="128x51", dp_disk=4.31, spinta=0.2)]
    (tmp_path / "iterazioni_dp.json").write_text(json.dumps(steps))
    scan = dict(griglia="90x36", D_ventola_mm=60.0, migliore=dict(
        D_uscita_mm=70.0, L_diffusore_mm=100.0, L_tubo_mm=250.0, spinta_N=0.09, dp_Pa=5.0))
    out = optimisation_history(str(tmp_path), scan)
    fasi = [p["fase"] for p in out["passi"]]
    assert fasi == ["scansione", "ottimizzazione", "ottimizzazione", "ottimizzazione", "secante",
                    "ottimizzazione", "secante", "secante"]
    assert [p["n"] for p in out["passi"]] == list(range(1, 9))
    assert out["passi"][1]["griglia"] == "64x26" and out["passi"][1]["dp_Pa"] == 4.0
    assert out["passi"][1]["D_uscita_mm"] == pytest.approx(80.0)
    assert out["passi"][4]["D_uscita_mm"] == out["passi"][3]["D_uscita_mm"]
    assert out["scelta"] == out["passi"][-1] and out["scelta"]["ciclo"] == 0
    assert (tmp_path / "storico_ottimizzazione.json").exists()
