"""Power along the manoeuvre: phases, peak and energy."""
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path[:0] = [os.path.join(ROOT, "3_sistema"), os.path.join(ROOT, "2_ventola")]

from sistema_designer.mission_power import profile


def fan(p):
    return {"best": {"cases": [{"shaft_power_W": p, "rpm": 15000.0, "torque_Nm": 1e-3}]}}


def thrust(t_acc, tempo, n=2):
    return {"input": {"n_ugelli": n, "tempo": tempo, "distanza": 1.0},
            "t_accelerazione_s": t_acc, "T_ugello_N": 0.1}


def test_bang_bang_has_two_phases_and_the_right_energy():
    p = profile(thrust(2.5, 5.0), fan(1.2))
    assert [x["fase"] for x in p["fasi"]] == ["accelerazione", "frenata"]
    assert p["picco_W"] == pytest.approx(2.4)
    assert p["energia_manovra_J"] == pytest.approx(2.4 * 5.0)


def test_coasting_adds_a_phase_with_no_power():
    p = profile(thrust(2.0, 10.0, n=4), fan(1.0))
    assert [x["fase"] for x in p["fasi"]] == ["accelerazione", "crociera", "frenata"]
    assert p["fasi"][1]["potenza_faccia_W"] == 0.0
    assert p["tempo_con_motori_accesi_s"] == pytest.approx(4.0)
    assert p["energia_manovra_J"] == pytest.approx(4 * 1.0 * 4.0)
    assert p["potenza_media_W"] == pytest.approx(16.0 / 10.0)
