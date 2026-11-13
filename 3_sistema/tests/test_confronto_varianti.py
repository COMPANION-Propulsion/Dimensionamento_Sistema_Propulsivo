"""confronto_varianti on two minimal fake variants: json, md, xlsx and svg without exceptions."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "3_sistema"), os.path.join(ROOT, "2_ventola")]

from sistema_designer import confronto_varianti as cv


def _w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def variant(folder, stator, shaft):
    q = 0.047
    _w(folder / "2_venturi" / "00_sintesi" / "risultati.json", {
        "ventola": {"dp_disk_Pa": 169.0, "D_ventola_m": 0.058, "z_centro_ventola_m": 0.061,
                    "L_ventola_m": 0.032 if stator else 0.012, "portata_m3_s": q},
        "geometria": {"L_tubo_mm": 137.0 if stator else 117.0, "D_uscita_m": 0.0613},
        "perdite": {"imbocco_Pa": 3.4, "disco_Pa": 4.8, "valle_Pa": 1.8, "totale_Pa": 10.0,
                    "p0_uscita_Pa": 159.0, "potenza_persa_W": 0.47}})
    (folder / "2_venturi" / "03_cad").mkdir(parents=True, exist_ok=True)
    (folder / "2_venturi" / "03_cad" / "profilo.csv").write_text(
        "z_mm,r_mm\n0,32\n40,30\n80,29\n120,30.5\n", encoding="utf-8")
    case = {"rpm": 16000.0, "shaft_power_W": shaft, "axial_total_pressure_rise_Pa": 169.0,
            "volume_flow_m3_s": q, "profile_loss_power_W": 0.9, "stator_enabled": stator,
            "stator_loss_power_W": 1.1, "swirl_power_W": 0.58, "net_torque_Nm": 0.0 if stator else 5e-3,
            "Mach_max": 0.15}
    cad = {"stator": {"vanes": 7, "radius_mm": [13, 20, 28], "chord_mm": [8, 12, 18]}} if stator else {}
    _w(folder / "3_ventola" / "00_sintesi" / "report.json", {
        "best": {"cases": [case], "design": {"blade_count": 3, "profile": "NACA0012"}}, "cad": cad})
    _w(folder / "fascia.json", [
        {"iterazione": 1, "L_disk_m": 0.032, "monte_m": 0.004, "valle_m": 0.03, "L_disk_nuovo_m": 0.031,
         "dp_Pa": 170.0, "L_tubo_mm": 138.0, "D_ventola_mm": 58.0, "convergito": False},
        {"iterazione": 2, "L_disk_m": 0.031, "monte_m": 0.004, "valle_m": 0.03, "L_disk_nuovo_m": 0.031,
         "dp_Pa": 169.0, "L_tubo_mm": 137.0, "D_ventola_mm": 58.0, "convergito": True}])
    _w(folder / "4_sistema" / "00_sintesi" / "potenza_manovra.json",
       {"energia_manovra_J": 99.0, "picco_W": 19.0})


def test_two_variants(tmp_path):
    variant(tmp_path / "Statore", True, 9.96)
    variant(tmp_path / "NoStatore", False, 9.4)
    out = cv.run(tmp_path)
    for name in ("confronto_statore.json", "RISULTATO.md", "confronto_statore.xlsx", "bilancio_potenza.svg",
                 "confronto_grandezze.svg", "profili_tubi.svg", "fascia_iterazioni.svg"):
        assert (out / name).is_file() and (out / name).stat().st_size > 0, name
    data = json.loads((out / "confronto_statore.json").read_text(encoding="utf-8"))
    assert data["vantaggi_senza_statore"]
    assert any("coppia" in x for x in data["svantaggi_senza_statore"])
    s = data["varianti"]["Statore"]
    assert abs(s["bilancio"]["residuo_pct_albero"]) < 5.0
    assert s["tubo"]["area_pale_statore_mm2"] == pytest.approx(7 * (0.5 * 20 * 7 + 0.5 * 30 * 8))
    assert s["tubo"]["area_parete_cm2"] > 100


def test_missing_variant_is_reported(tmp_path):
    variant(tmp_path / "Statore", True, 9.96)
    out = cv.run(tmp_path)
    text = (out / "RISULTATO.md").read_text(encoding="utf-8")
    assert "NoStatore non disponibile" in text
    assert (out / "bilancio_potenza.svg").is_file()
