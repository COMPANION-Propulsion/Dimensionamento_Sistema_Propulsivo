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


def thrust_full(a_d_g, tempo=5.0, d=0.2, m=4.5, n=2, k=2.0):
    a = 4 * d / tempo ** 2
    return {"input": {"n_ugelli": n, "tempo": tempo, "distanza": d, "massa": m,
                      "disturbo_residuo_g": a_d_g, "fattore_margine": k},
            "t_accelerazione_s": tempo / 2, "accelerazione_m_s2": a,
            "T_ugello_N": k * m * (a + a_d_g * 9.80665) / n}


def test_no_disturbance_is_the_design_power_scaled_by_the_margin():
    # thrust needed = design thrust / 2: power = P* / 2^1.5 on both phases
    p = profile(thrust_full(0.0), fan(1.0))["con_disturbo"]
    assert p["energia_del_disturbo_J"] == pytest.approx(0.0)
    assert p["picco_W"] == pytest.approx(2 * 1.0 / 2 ** 1.5)
    assert p["energia_J"] == pytest.approx(5.0 * 2 * 1.0 / 2 ** 1.5)
    assert p["potenza_per_tenere_la_posizione_W"] == 0.0


def test_disturbance_larger_than_the_manoeuvre_keeps_the_rear_face_on_while_braking():
    p = profile(thrust_full(0.01), fan(1.0))["con_disturbo"]
    assert [x["faccia"] for x in p["fasi"]] == ["posteriore", "posteriore"]
    assert p["fasi"][0]["spinta_faccia_N"] == pytest.approx(4.5 * (0.032 + 0.0980665))
    assert p["fasi"][1]["spinta_faccia_N"] == pytest.approx(4.5 * (0.0980665 - 0.032))
    assert p["energia_del_disturbo_J"] > 0.0
    assert p["picco_W"] < profile(thrust_full(0.01), fan(1.0))["picco_W"]


def test_power_curve_is_used_when_given():
    curve = {"righe": [{"spinta_ugello_N": 0.0, "potenza_albero_W": 0.0},
                       {"spinta_ugello_N": 0.3, "potenza_albero_W": 0.9},
                       {"spinta_ugello_N": 0.6, "potenza_albero_W": 3.0}]}
    p = profile(thrust_full(0.0), fan(1.0), curve)["con_disturbo"]
    assert p["modello_potenza"].startswith("curva")
    assert p["picco_W"] == pytest.approx(2 * 0.9 * (4.5 * 0.032 / 2) / 0.3)


def test_ground_to_flight_follows_the_fan_laws(tmp_path):
    import json
    from sistema_designer.data import Case
    from sistema_designer import note
    for sub, name, data in (
            ("1_spinta", "spinta.json", {**thrust_full(0.01), "T_totale_N": 1.17}),
            ("2_venturi/00_sintesi", "risultati.json", {"ventola": {"densita_kg_m3": 1.204}}),
            ("2_venturi/05_convergenza", "design.json", {"case": {"p_amb": 100000.0}}),
            ("3_ventola/00_sintesi", "report.json",
             {"best": {"cases": [{"shaft_power_W": 6.0, "rpm": 20000.0, "Re_min": 30000.0}]}})):
        (tmp_path / sub).mkdir(parents=True)
        (tmp_path / sub / name).write_text(json.dumps(data), encoding="utf-8")
    case = Case(tmp_path)
    out = note.export(case, 81000.0, profile(case.thrust, fan(6.0)), {"scarto_spinta_pct": -8.0})
    f = out["terra_volo"]
    assert f["a_giri_di_progetto"]["spinta_ugello_N"] == pytest.approx(0.81 * case.thrust["T_ugello_N"])
    assert f["a_giri_di_progetto"]["margine_effettivo"] == pytest.approx(2 * 0.81)
    assert f["a_spinta_di_progetto"]["rpm"] == pytest.approx(20000 / 0.9)
    assert f["a_spinta_di_progetto"]["potenza_albero_W"] == pytest.approx(6.0 / 0.9)
    assert len(out["note"]) == 4 and any("3 facce" in x for x in out["note"])
    assert note.export(case, None)["terra_volo"] is None
    assert note.markdown(out)[0].startswith("## Dimensionato a terra")
