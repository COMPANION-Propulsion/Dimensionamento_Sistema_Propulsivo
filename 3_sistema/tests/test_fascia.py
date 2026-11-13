"""Fan band: need from the fan CAD, update rule, loop of venturi + fan (no CFD, no fan sizing)."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "3_sistema"), os.path.join(ROOT, "2_ventola"), ROOT]

from sistema_designer.fascia import band_need, update_band

CAD = {"fan_centre_x_mm": 61.0, "hub_length_mm": 13.0,
       "stator": {"x_end_mm": 91.1, "axial_gap_mm": 2.0, "length_mm": 18.0, "vanes": 7}}
VENTURI = {"ventola": {"z_centro_ventola_m": 0.061}}
REF = os.path.join(ROOT, "risultati", "Run_20261112_fine_4kg")


def test_band_need_with_stator_from_cad_numbers():
    need = band_need({"cad": CAD}, VENTURI, True)
    assert need["valle_m"] == pytest.approx(0.0301)              # x_end - centre
    assert need["monte_m"] == pytest.approx(0.004, abs=1e-4)     # hub 13, rotor downstream 9.1


def test_band_need_without_stator_is_the_rotor_end():
    need = band_need({"cad": CAD}, VENTURI, False)
    assert need["valle_m"] == pytest.approx(0.0091, abs=1e-4)
    assert need["monte_m"] + need["valle_m"] == pytest.approx(0.013, abs=1e-4)


def test_band_need_errors():
    with pytest.raises(ValueError):
        band_need({}, VENTURI, True)
    with pytest.raises(ValueError):
        band_need({"cad": {**CAD, "stator": None}}, VENTURI, True)


def test_band_need_reads_the_stl_of_the_rotor(tmp_path):
    import numpy as np
    tri = np.zeros(2, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    tri["v"][0] = [[58, 0, 0], [66, 1, 0], [60, 0, 1]]
    tri["v"][1] = [[58, 0, 0], [66, 1, 0], [62, 3, 1]]
    with open(tmp_path / "ventola_A.stl", "wb") as fh:
        fh.write(b"\0" * 80 + np.uint32(2).tobytes() + tri.tobytes())
    need = band_need({"cad": CAD}, VENTURI, False, tmp_path)
    assert need["monte_m"] == pytest.approx(0.003) and need["valle_m"] == pytest.approx(0.005)
    assert need["fonte"] == "STL del rotore"


@pytest.mark.skipif(not os.path.isfile(os.path.join(REF, "3_ventola", "00_sintesi", "report.json")),
                    reason="reference run missing")
def test_band_need_on_the_4kg_run():
    with open(os.path.join(REF, "3_ventola", "00_sintesi", "report.json"), encoding="utf-8") as fh:
        rep = json.load(fh)
    with open(os.path.join(REF, "2_venturi", "00_sintesi", "risultati.json"), encoding="utf-8") as fh:
        ven = json.load(fh)
    need = band_need(rep, ven, True, os.path.join(REF, "3_ventola", "03_cad"))
    assert need["valle_m"] == pytest.approx(0.0301, abs=2e-4)
    assert need["monte_m"] == pytest.approx(0.0039, abs=2e-4)
    assert band_need(rep, ven, True)["valle_m"] == pytest.approx(need["valle_m"], abs=1e-6)


def test_update_margin_and_convergence():
    need = {"monte_m": 0.004, "valle_m": 0.0301}
    u = update_band(0.032, need, margin=0.001)
    assert u["L_disk_nuovo_m"] == pytest.approx(0.0311) and not u["convergito"]
    assert update_band(0.0311, need, margin=0.001)["convergito"]
    assert update_band(0.0314, need, margin=0.001)["convergito"]       # 0.3 mm: within 0.5


def test_update_minimum_and_upstream():
    assert update_band(0.01, {"monte_m": 0.004, "valle_m": 0.009}, 0.001, minimum=0.02)["L_disk_nuovo_m"] == 0.02
    assert update_band(0.01, {"monte_m": 0.012, "valle_m": 0.009}, 0.001)["L_disk_nuovo_m"] == pytest.approx(0.013)


def test_update_respects_lmax():
    u = update_band(0.03, {"monte_m": 0.01, "valle_m": 0.05}, 0.001, L_max=0.16)
    assert u["tagliato"] and 4 * u["L_disk_nuovo_m"] < 0.16


# ---- loop of run_sistema.py with fake venturi and fan ------------------------------------

INPUT = """
CASO = {"nome": "t"}
SPINTA = {}
VENTURI = {"L_disk": 0.032, "L_max": 0.16, "T_ugello": 0.9}
VENTOLA = {"margine_fascia_m": 0.001, "fascia_min_m": None, "statore": {"presente": True}}
SISTEMA = {"confronto_statore": True, "iterazioni_fascia": 3}
"""


def _fakes(monkeypatch, valles, calls):
    """Fake venturi and fan; `valles` = iterator of the downstream need [mm] of each fan run."""
    import run_sistema as rs

    def venturi(input_file, output_dir=None, skip_extras=False):
        calls["venturi"].append(skip_extras)
        d = os.path.join(output_dir, "00_sintesi")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "risultati.json"), "w") as fh:
            json.dump({"ventola": {"dp_disk_Pa": 100.0, "D_ventola_m": 0.058, "z_centro_ventola_m": 0.061},
                       "geometria": {"L_tubo_mm": 130.0}}, fh)
        return 0

    def ventola(input_file, root=None):
        calls["ventola"] += 1
        d = os.path.join(root, "3_ventola", "00_sintesi")
        os.makedirs(d, exist_ok=True)
        cad = {"fan_centre_x_mm": 61.0, "hub_length_mm": 13.0,
               "stator": {"x_end_mm": 61.0 + next(valles), "axial_gap_mm": 2.0, "length_mm": 18.0}}
        with open(os.path.join(d, "report.json"), "w") as fh:
            json.dump({"best": {"cases": [{}]}, "cad": cad}, fh)
        return 0

    monkeypatch.setattr(rs, "run_venturi", venturi)
    monkeypatch.setattr(rs, "run_ventola", ventola)
    return rs


def _run(rs, tmp_path):
    inp = tmp_path / "input.py"
    inp.write_text(INPUT, encoding="utf-8")
    folder = tmp_path / "Statore"
    rc = rs.fascia_loop(str(inp), str(tmp_path), str(folder), "Statore", True,
                        {"confronto_statore": True, "iterazioni_fascia": 3})
    with open(folder / "fascia.json") as fh:
        return rc, json.load(fh), folder


def test_loop_converges_and_finalises_with_extras(tmp_path, monkeypatch):
    calls = {"venturi": [], "ventola": 0}
    rs = _fakes(monkeypatch, iter([30.1] * 10), calls)
    rc, rows, folder = _run(rs, tmp_path)
    assert rc == 0
    assert calls["venturi"] == [True, True, False]                    # extras only in the last pass
    assert calls["ventola"] == 2                                       # the last venturi is the same duct
    assert [r["L_disk_m"] for r in rows] == pytest.approx([0.032, 0.0311, 0.0311])
    assert rows[-1]["convergito"] and rows[-1]["ventola_riusata"]
    text = (folder / "input_usato.py").read_text()
    assert '"L_disk": 0.0311' in text and '"presente": True' in text and '"T_ugello": 0.9' in text


def test_loop_not_converged_is_reported_and_kept(tmp_path, monkeypatch):
    calls = {"venturi": [], "ventola": 0}
    rs = _fakes(monkeypatch, iter([30.1, 20.0, 10.0]), calls)         # the fan keeps changing its need
    rc, rows, _ = _run(rs, tmp_path)
    assert rc == 0 and len(rows) == 3 and not rows[-1]["convergito"]
    assert calls["venturi"] == [True, True, False]
