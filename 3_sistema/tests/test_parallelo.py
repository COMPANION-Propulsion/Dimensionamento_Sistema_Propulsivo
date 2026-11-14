"""Processes of run_sistema.py: the cap rule, which chains / cases run in parallel, log.txt and
the errors. No calculation: the chain is replaced by fake functions and the process pool by a
serial one (the monkeypatches would not reach spawned processes)."""
import os
import pickle
import sys
from concurrent.futures import Future

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "0_spinta")]

import run_sistema as rs

par = rs.parallel_module()
GB = 1024 ** 3


class SerialExecutor:
    """Stands in for ProcessPoolExecutor: runs each job at once, in this process."""
    def __init__(self, max_workers=None):
        SerialExecutor.workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args):
        f = Future()
        try:
            f.set_result(fn(*args))
        except BaseException as e:
            f.set_exception(e)
        return f


# ---- the rule --------------------------------------------------------------------------

def test_automatic_number_follows_cores_and_free_ram():
    assert par.auto_processes(cores=12, free_bytes=31 * GB) == 12
    assert par.auto_processes(cores=12, free_bytes=8 * GB) == 3        # floor(0.6 * 8 / 1.5)
    assert par.auto_processes(cores=12, free_bytes=int(0.5 * GB)) == 1  # at least one
    assert par.auto_processes(cores=6, free_bytes=None) == 6           # RAM unknown: cores
    assert par.auto_processes() >= 1


def test_processi_value_is_checked():
    assert par.resolve_processes(1) == 1 and par.resolve_processes(5) == 5
    assert par.resolve_processes(None) >= 1
    for bad in (0, -2, 2.5, True, "3"):
        with pytest.raises(ValueError):
            par.resolve_processes(bad)


def test_budget_is_split_inwards_and_never_exceeded():
    assert par.split_budget(2, 12) == (2, 6)
    assert par.split_budget(20, 3) == (3, 1)
    assert par.split_budget(1, 12) == (1, 12)       # one job: it keeps the whole budget
    assert par.split_budget(5, 1) == (1, 1)         # budget 1: sequential
    for budget in (1, 2, 5, 12):
        total, left = 1, budget
        for n_jobs in (3, 2, 20):                    # series, variants, inner jobs
            w, left = par.split_budget(n_jobs, budget=left)
            total *= w
        assert total <= budget


def test_fan_jobs_never_exceed_the_budget():
    assert rs.fan_jobs(None, None) is None and rs.fan_jobs(6, None) == 6     # unmanaged: as before
    assert rs.fan_jobs(6, 2) == 2 and rs.fan_jobs(1, 8) == 1
    assert rs.fan_jobs(None, 2) == 2
    assert rs.fan_jobs(None, 12) is None                                      # the fan picks (4 at most)


# ---- jobs, logs, errors ---------------------------------------------------------------------

def test_logged_job_writes_log_and_reports_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(rs._JOBS, "chain", "_fake_job")
    monkeypatch.setattr(rs, "_fake_job", lambda **kw: (print("hello", kw["x"]), kw["x"])[1],
                        raising=False)
    log = tmp_path / "a" / "log.txt"
    res = rs.logged_job(("chain", {"x": 3}, str(log), "A"))
    assert res["rc"] == 3 and res["error"] is None
    assert "hello 3" in log.read_text(encoding="utf-8")
    assert "hello" not in capsys.readouterr().out.replace("[A] inizio", "")   # not on the screen

    def boom(**kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(rs, "_fake_job", boom)
    res = rs.logged_job(("chain", {}, str(log), "A"))
    assert res["rc"] == 1 and "RuntimeError: boom" in res["error"]
    assert "boom" in log.read_text(encoding="utf-8")


def test_job_payload_and_worker_are_picklable(tmp_path):
    payload = ("chain", dict(input_file="i.py", case_root="r", folder="f", label="Statore",
                             stator=True, sis={"processi": 4}, only=None, procs=2),
               str(tmp_path / "log.txt"), "Statore")
    assert pickle.loads(pickle.dumps(payload)) == payload
    assert pickle.loads(pickle.dumps(rs.logged_job)) is rs.logged_job


INPUT = '''
CASO = {"nome": "caso_prova", "sovrascrivi": True}
SPINTA = {"distanza": 0.2, "tempo": 5, "massa": 4, "n_ugelli": 2, "profilo": "bang_bang"}
VENTURI = {"D_ext_max": 0.07, "L_max": 0.16, "L_disk": 0.03, "T_ugello": 0.5}
VENTOLA = {}
SISTEMA = {"confronto_statore": %(cs)r}
'''


def _case(tmp_path, monkeypatch, cs=True, fake=None):
    inp = tmp_path / "in.py"
    inp.write_text(INPUT % dict(cs=cs), encoding="utf-8")
    calls = []

    def run_chain(input_file, case_root, folder, label, stator, sis, only=None, procs=None):
        calls.append((label, procs))
        print("fake chain", label)
        if fake:
            fake(label)
        return 0

    monkeypatch.setattr(rs, "run_chain", run_chain)
    monkeypatch.setattr(rs, "run_confronto", lambda root: 0)
    monkeypatch.setattr(rs, "write_summary", lambda *a, **k: None)
    monkeypatch.setattr(rs, "write_masses", lambda *a, **k: None)
    monkeypatch.setattr(rs, "ProcessPoolExecutor", SerialExecutor)
    return str(inp), calls


def test_variants_run_in_parallel_with_split_budget_and_log(tmp_path, monkeypatch, capsys):
    inp, calls = _case(tmp_path, monkeypatch)
    rc = rs.run_case(inp, "venturi", str(tmp_path / "ris"), procs=8)
    assert rc == 0
    assert sorted(calls) == [("NoStatore", 4), ("Statore", 4)]
    assert SerialExecutor.workers == 2
    for name in ("Statore", "NoStatore"):
        text = (tmp_path / "ris" / "caso_prova" / name / "log.txt").read_text(encoding="utf-8")
        assert f"fake chain {name}" in text
    out = capsys.readouterr().out
    assert "[Statore] inizio" in out and "[Statore] fine, codice 0" in out
    assert "fake chain" not in out                      # the chain output is only in the logs


def test_budget_one_or_unmanaged_is_sequential_as_before(tmp_path, monkeypatch, capsys):
    inp, calls = _case(tmp_path, monkeypatch)
    rs.run_case(inp, "venturi", str(tmp_path / "ris"), procs=1)
    assert calls == [("Statore", 1), ("NoStatore", 1)]          # in order, no log.txt
    assert not (tmp_path / "ris" / "caso_prova" / "Statore" / "log.txt").exists()
    assert "fake chain Statore" in capsys.readouterr().out
    calls.clear()
    rs.run_case(inp, "venturi", str(tmp_path / "ris"))
    assert calls == [("Statore", None), ("NoStatore", None)]


def test_one_chain_keeps_the_whole_budget_and_stays_in_process(tmp_path, monkeypatch):
    inp, calls = _case(tmp_path, monkeypatch, cs=False)
    rs.run_case(inp, "venturi", str(tmp_path / "ris"), procs=8)
    assert calls == [(None, 8)]


def test_failing_parallel_chain_is_reported_and_the_other_goes_on(tmp_path, monkeypatch, capsys):
    def fake(label):
        if label == "Statore":
            raise RuntimeError("boom")

    inp, calls = _case(tmp_path, monkeypatch, fake=fake)
    rc = rs.run_case(inp, "venturi", str(tmp_path / "ris"), procs=4)
    assert rc == 3                                           # one chain ok, one failed
    out = capsys.readouterr().out
    assert "[Statore] fine, codice 1" in out and "RuntimeError: boom" in out and "ERRORE" in out
    assert "[NoStatore] fine, codice 0" in out
    log = (tmp_path / "ris" / "caso_prova" / "Statore" / "log.txt").read_text(encoding="utf-8")
    assert "RuntimeError: boom" in log


def test_sequential_error_propagates_as_before(tmp_path, monkeypatch):
    def fake(label):
        raise RuntimeError("boom")
    inp, _ = _case(tmp_path, monkeypatch, fake=fake)
    with pytest.raises(RuntimeError):
        rs.run_case(inp, "venturi", str(tmp_path / "ris"), procs=1)


SERIES = INPUT.replace('"massa": 4', '"massa": "4; 6"').replace('"nome": "caso_prova", ', '')


def test_series_cases_run_in_parallel_and_summary_keeps_the_order(tmp_path, monkeypatch, capsys):
    inp = tmp_path / "ser.py"
    inp.write_text(SERIES % dict(cs=False), encoding="utf-8")
    plan = rs.plan_series(str(inp), str(tmp_path / "ris"))
    calls = []

    def run_case(case_input, solo, results_dir, procs=None):
        calls.append((os.path.basename(os.path.dirname(case_input)), procs))
        print("fake case")
        return 0 if "massa_6" not in case_input else 1

    monkeypatch.setattr(rs, "run_case", run_case)
    monkeypatch.setattr(rs, "ProcessPoolExecutor", SerialExecutor)
    rc = rs.run_series(str(inp), plan, "venturi", procs=6)
    assert sorted(calls) == [("massa_4", 3), ("massa_6", 3)]
    assert rc == 3
    text = open(os.path.join(plan["root"], "RIEPILOGO.md"), encoding="utf-8").read()
    assert text.index("massa_4") < text.index("massa_6")
    assert "| massa_4 | ok |" in text and "| massa_6 | errore (codice 1) |" in text
    for lab in ("massa_4", "massa_6"):
        assert "fake case" in open(os.path.join(plan["root"], lab, "log.txt"), encoding="utf-8").read()
    assert "[massa_6] fine, codice 1" in capsys.readouterr().out
