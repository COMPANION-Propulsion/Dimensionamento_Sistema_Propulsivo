"""Series of cases of run_sistema.py: "4; 6" parsing, combinations, labels, derived input, --elenca."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "0_spinta")]

import run_sistema as rs

BASE = '''
CASO = {"nome": None, "sovrascrivi": True}
SPINTA = {"distanza": 0.2, "tempo": 5, "massa": %(massa)r, "n_ugelli": 2, "profilo": "bang_bang"}
VENTURI = {"D_ext_max": %(D)r, "L_max": 0.16, "L_disk": 0.03, "T_ugello": None}
VENTOLA = {"statore": {"presente": %(st)r, "pale": None}, "mozzo_su_D": [0.3, 0.4]}
SISTEMA = {"combinazioni": %(comb)r, "confronto_statore": False}
'''


def make_input(tmp_path, massa="4; 6", D="0.07; 0.08", st=True, comb="tutte"):
    path = tmp_path / "in.py"
    path.write_text(BASE % dict(massa=massa, D=D, st=st, comb=comb), encoding="utf-8")
    return str(path)


def test_parse_numbers_text_none_and_plain():
    assert rs.parse_multi("4; 6") == [4, 6]
    assert rs.parse_multi("bang_bang; trapezio") == ["bang_bang", "trapezio"]
    assert rs.parse_multi("None; 0.1") == [None, 0.1]
    assert rs.parse_multi("True; False") == [True, False]
    assert rs.parse_multi("[1, 2]; [3]") == [[1, 2], [3]]
    assert rs.parse_multi("bang_bang") is None
    assert rs.parse_multi(4) is None
    assert rs.parse_multi(None) is None


def test_nested_value_is_found(tmp_path):
    raw = rs.load_raw(make_input(tmp_path, massa=4, D=0.07, st="True; False"))
    axes = rs.find_axes(raw)
    assert axes == [("VENTOLA", ("statore", "presente"), [True, False])]


def test_combinations_all_and_paired(tmp_path):
    axes = rs.find_axes(rs.load_raw(make_input(tmp_path, massa="4; 6; 8", D="0.07; 0.08")))
    assert len(rs.combine(axes, "tutte")) == 6
    assert rs.combine(axes[:1] + [axes[1][:2] + ([0.07, 0.08, 0.09],)], "accoppiate") == \
        [[4, 0.07], [6, 0.08], [8, 0.09]]
    with pytest.raises(ValueError, match="same length"):
        rs.combine(axes, "accoppiate")
    with pytest.raises(ValueError, match="combinazioni"):
        rs.combine(axes, "boh")


def test_labels_are_safe_and_unique(tmp_path):
    axes = rs.find_axes(rs.load_raw(make_input(tmp_path)))
    labels = rs.make_labels(axes, rs.combine(axes, "tutte"))
    assert labels[0] == "massa_4__D_ext_max_0.07"
    assert len(set(labels)) == len(labels) == 4
    bad = [("SPINTA", ("a",), ['x/y', 'x:y', 'x?y'])]
    lab = rs.make_labels(bad, [[v] for v in bad[0][2]])
    assert len(set(lab)) == 3 and not any(c in "".join(lab) for c in '<>:"/\\|?* ')
    nested = [("VENTOLA", ("statore", "presente"), [True, False])]
    assert rs.make_labels(nested, [[True], [False]]) == ["statore.presente_True", "statore.presente_False"]


def test_series_name_is_stable_and_uses_original_strings(tmp_path):
    p = make_input(tmp_path)
    plan1, plan2 = rs.plan_series(p, str(tmp_path)), rs.plan_series(p, str(tmp_path))
    assert plan1["name"] == plan2["name"] and "_serie_h" in plan1["name"]
    other = rs.plan_series(make_input(tmp_path, massa="4; 6; 8"), str(tmp_path))
    assert other["name"] != plan1["name"]
    assert plan1["root"] == os.path.join(str(tmp_path), plan1["name"])


def test_derived_input_reloads_with_case_values(tmp_path):
    from spinta_designer import caso
    p = make_input(tmp_path, massa="4; 6", D=0.07, st="True; False")
    plan = rs.plan_series(p, str(tmp_path))
    c = plan["cases"][3]                      # massa 6, statore False
    path = rs.write_case_input(p, c["folder"], c["label"], plan["axes"], c["combo"])
    assert os.path.dirname(path) == c["folder"]
    inp = caso.load_input(path)
    assert inp["SPINTA"]["massa"] == 6 and inp["VENTURI"]["D_ext_max"] == 0.07
    assert inp["VENTOLA"]["statore"] == {"presente": False, "pale": None}
    assert inp["CASO"]["nome"] == c["label"]
    assert rs.load_sistema(path)["densita_kg_m3"] == 1240.0


def test_sistema_defaults():
    d = rs.SISTEMA_DEFAULTS
    assert d["combinazioni"] == "tutte" and d["densita_kg_m3"] == 1240.0 and d["riempimento"] == 1.0


def test_elenca_runs_nothing(tmp_path):
    p = make_input(tmp_path)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run_sistema.py"), "--elenca", "--input", p],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "4 cases" in r.stdout and "massa_6__D_ext_max_0.08" in r.stdout
    assert not os.path.exists(os.path.join(ROOT, "risultati", rs.plan_series(p)["name"]))


def test_series_summary_table(tmp_path):
    p = make_input(tmp_path, massa="4; 6", D=0.07)
    plan = rs.plan_series(p, str(tmp_path))
    rows = [dict(label=c["label"], folder=c["folder"], rc=rc) for c, rc in zip(plan["cases"], (0, 1))]
    text = open(rs.write_series_summary_md(plan, rows), encoding="utf-8").read()
    assert "| massa_4 | ok |" in text and "| massa_6 | errore (codice 1) |" in text


def test_series_runs_spinta_in_every_case_and_survives_a_failure(tmp_path):
    p = make_input(tmp_path, massa="4; -1; 6", D=0.07)
    plan = rs.plan_series(p, str(tmp_path))
    rc = rs.run_series(p, plan, "spinta")
    for lab in ("massa_4", "massa_6"):
        assert os.path.isfile(os.path.join(plan["root"], lab, "1_spinta", "spinta.json"))
        assert os.path.isfile(os.path.join(plan["root"], lab, "input_usato.py"))
    text = open(os.path.join(plan["root"], "RIEPILOGO.md"), encoding="utf-8").read()
    assert "| massa_6 | ok |" in text
    assert rc == 3 or rc == 0
