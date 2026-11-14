"""masse: STL volumes, chain masses and the Excel summaries on tiny fake cases."""
import json
import math
import os
import shutil
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "3_sistema"), os.path.join(ROOT, "2_ventola")]

from sistema_designer import masse
from sistema_designer import confronto_varianti as cv

RUN = os.path.join(ROOT, "risultati", "Run_20261112_fine_4kg")


def cube_tris(a=10.0):
    v = np.array([[x, y, z] for x in (0, a) for y in (0, a) for z in (0, a)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for q in quads:
        tris += [[v[q[0]], v[q[1]], v[q[2]]], [v[q[0]], v[q[2]], v[q[3]]]]
    return np.array(tris)


def cylinder_tris(r=5.0, h=20.0, n=360):
    th = 2*np.pi*np.arange(n)/n
    tris = []
    for a, b in zip(th, np.roll(th, -1)):
        p0, p1 = (0, r*np.cos(a), r*np.sin(a)), (0, r*np.cos(b), r*np.sin(b))
        q0, q1 = (h, p0[1], p0[2]), (h, p1[1], p1[2])
        tris += [[p0, q1, q0], [p0, p1, q1], [(0, 0, 0), p1, p0], [(h, 0, 0), q0, q1]]
    return np.array(tris, float)


def write_binary(tris, path):
    data = np.zeros(len(tris), dtype=[("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")])
    data["v"] = tris.reshape(-1, 9)
    with open(path, "wb") as f:
        f.write(b" "*80)
        f.write(np.uint32(len(tris)).tobytes())
        data.tofile(f)


def write_ascii(tris, path):
    with open(path, "w") as f:
        f.write("solid t\n")
        for t in tris:
            f.write("facet normal 0 0 0\nouter loop\n")
            for p in t:
                f.write(f"vertex {float(p[0])!r} {float(p[1])!r} {float(p[2])!r}\n")
            f.write("endloop\nendfacet\n")
        f.write("endsolid t\n")


@pytest.mark.parametrize("writer", [write_binary, write_ascii])
def test_cube_and_cylinder(tmp_path, writer):
    writer(cube_tris(10.0), tmp_path/"c.stl")
    v = masse.stl_volume_m3(tmp_path/"c.stl")
    assert v.volume_m3 == pytest.approx(1000e-9, rel=1e-3) and v.chiuso
    writer(cylinder_tris(), tmp_path/"y.stl")
    v = masse.stl_volume_m3(tmp_path/"y.stl")
    exact = 360/2*5.0**2*math.sin(2*math.pi/360)*20*1e-9      # inscribed polygon
    assert v.volume_m3 == pytest.approx(exact, rel=1e-3) and v.chiuso


def test_inverted_orientation_and_open_surface(tmp_path):
    tris = cube_tris()
    write_binary(tris[:, ::-1], tmp_path/"inv.stl")
    assert masse.stl_volume_m3(tmp_path/"inv.stl").volume_m3 == pytest.approx(1000e-9, rel=1e-3)
    write_binary(tris[:-2], tmp_path/"open.stl")                 # one face missing
    v = masse.stl_volume_m3(tmp_path/"open.stl")
    assert v.chiuso is False and v.volume_m3 > 0


def fake_chain(folder, scale=1.0, stator=True):
    cad = folder/"2_venturi"/"03_cad"
    cad.mkdir(parents=True)
    write_binary(cube_tris(10.0*scale), cad/"tubo.stl")
    fan = folder/"3_ventola"/"03_cad"
    fan.mkdir(parents=True)
    write_binary(cube_tris(5.0), fan/"ventola_A.stl")
    if stator:
        write_binary(cube_tris(4.0), fan/"statore_A.stl")


def test_masses_of_chain_and_missing(tmp_path):
    fake_chain(tmp_path/"c")
    m = masse.masses_of_chain(tmp_path/"c", 1000.0, 0.5)
    assert m["tubo"]["massa_g"] == pytest.approx(1000e-9*1000*0.5*1e3, rel=1e-3)
    assert m["totale"]["massa_g"] == pytest.approx(
        (1000 + 125 + 64)*1e-9*1000*0.5*1e3, rel=1e-3)
    assert m["alternative"] == [] and m["note"]
    m = masse.masses_of_chain(tmp_path/"vuota")                  # nothing at all: no exception
    assert m["tubo"]["massa_g"] is None and m["totale"]["massa_g"] is None and m["note"]


def fake_chain_json(folder, stator, shaft, L_tubo):
    def w(rel, data):
        p = folder/rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
    w("2_venturi/00_sintesi/risultati.json", {
        "ventola": {"dp_disk_Pa": 169.0, "D_ventola_m": 0.058, "L_ventola_m": 0.03},
        "geometria": {"L_tubo_mm": L_tubo}})
    w("3_ventola/00_sintesi/report.json", {"best": {"cases": [
        {"shaft_power_W": shaft, "net_torque_Nm": 0.0 if stator else 5e-3}]}})
    w("fascia.json", [{"iterazione": 1, "L_disk_m": 0.031}])
    w("2_venturi/05_convergenza/alternative/alternative.json", {"casi": [
        {"id": "ottimo", "L_tubo_mm": L_tubo, "dp_Pa": 169.0, "potenza_W": shaft, "stato": "ok"},
        {"id": "L100", "L_tubo_mm": 100.0, "dp_Pa": 175.0, "potenza_W": shaft*1.05, "stato": "ok",
         "design_json": "L100/design.json"},
        {"id": "L90", "L_tubo_mm": 90.0, "dp_Pa": None, "potenza_W": None, "stato": "non converge"}]})


def test_write_mass_summary_variants(tmp_path):
    from openpyxl import load_workbook
    fake_chain(tmp_path/"Statore")
    fake_chain(tmp_path/"NoStatore", scale=1.1, stator=False)
    fake_chain_json(tmp_path/"Statore", True, 9.96, 137.0)
    fake_chain_json(tmp_path/"NoStatore", False, 9.4, 120.0)
    path = masse.write_mass_summary(tmp_path)
    assert os.path.isfile(path) and (tmp_path/"RIEPILOGO_masse.json").is_file()
    wb = load_workbook(path)
    assert wb.sheetnames == ["Alternative", "Statore", "Decisione", "Parametri"]
    ws = wb["Statore"]
    assert "togliendo lo statore" in str(ws["A7"].value)
    assert ws["A4"].value.startswith("NoStatore")
    data = json.loads((tmp_path/"RIEPILOGO_masse.json").read_text(encoding="utf-8"))
    assert data["statore"]["differenza"]["potenza albero [W]"] == pytest.approx(9.4 - 9.96)
    # series, one failed case included
    out = masse.write_series_summary([tmp_path, tmp_path/"manca"], tmp_path/"s"/"confronto_casi.xlsx",
                                     ["massa=4", "massa=6"])
    ws = load_workbook(out)["Casi"]
    assert ws.max_row == 3 and ws["A2"].value == "massa=4" and "assente" in ws["B3"].value
    masse.write_series_summary([tmp_path/"Statore"], tmp_path/"uno.xlsx", ["solo"])


def test_confronto_varianti_has_masses(tmp_path):
    from test_confronto_varianti import variant
    variant(tmp_path/"Statore", True, 9.96)
    variant(tmp_path/"NoStatore", False, 9.4)
    for n in ("Statore", "NoStatore"):
        fake_chain(tmp_path/n/"_x", stator=(n == "Statore"))
        for sub in ("2_venturi/03_cad", "3_ventola/03_cad"):
            for f in (tmp_path/n/"_x"/sub).iterdir():
                dest = tmp_path/n/sub
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dest/f.name)
    out = cv.run(tmp_path, densita_kg_m3=1240.0, riempimento=1.0)
    data = json.loads((out/"confronto_statore.json").read_text(encoding="utf-8"))
    assert data["varianti"]["Statore"]["masse"]["massa_statore_g"] > 0
    assert data["varianti"]["NoStatore"]["masse"]["massa_statore_g"] == 0.0
    assert any("massa" in x for x in data["vantaggi_senza_statore"])
    assert "massa del tubo" in (out/"RISULTATO.md").read_text(encoding="utf-8")


@pytest.mark.skipif(not os.path.isfile(os.path.join(RUN, "2_venturi", "05_convergenza", "design.json")),
                    reason="run 4 kg assente")
def test_tube_volume_from_design_matches_tubo_stl():
    v = masse.tube_volume_from_design(os.path.join(RUN, "2_venturi", "05_convergenza", "design.json"))
    ref = masse.stl_volume_m3(os.path.join(RUN, "2_venturi", "03_cad", "tubo.stl"))
    assert ref.chiuso
    assert v == pytest.approx(ref.volume_m3, rel=5e-3)
