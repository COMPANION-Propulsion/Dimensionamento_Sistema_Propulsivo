"""
export.py
=========
Files of the thrust step, in risultati/<caso>/1_spinta/:

    spinta.json          what the venturi reads (T_ugello) and the whole summary
    RISULTATO.md         readable summary
    grafici/moto.svg     s, v, a and nozzle thrust against time
    excel/spinta.xlsx    sheets Sintesi and Profilo
"""

from __future__ import annotations

import json
import os
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.styles import Alignment, Font, PatternFill

from .profilo import Motion

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def export_json(m: Motion, out: str) -> str:
    path = os.path.join(out, "spinta.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(m.summary(), fh, indent=1)
    return path


def export_report(m: Motion, out: str) -> str:
    s = m.summary()
    path = os.path.join(out, "RISULTATO.md")
    lines = [
        "# Spinta richiesta", "",
        "## Input", "",
        f"- distanza: {m.distanza:g} m, tempo: {m.tempo:g} s, massa: {m.massa:g} kg",
        f"- profilo: `{m.profilo}`, frazione di crociera: {m.frazione_crociera:g}",
        f"- ugelli per faccia: {m.n_ugelli}, fattore di margine: {m.fattore_margine:g}", "",
        "## Risultato", "",
        "| grandezza | valore |", "|---|---|",
        f"| accelerazione | {s['accelerazione_m_s2']:.6g} m/s² |",
        f"| tempo di accelerazione (= frenata) | {s['t_accelerazione_s']:.4g} s |",
        f"| tempo di crociera | {s['t_crociera_s']:.4g} s |",
        f"| velocità massima | {s['v_max_m_s']:.6g} m/s |",
        f"| spinta della faccia | {s['T_totale_N']:.6g} N |",
        f"| **spinta per ugello** | **{s['T_ugello_N']:.6g} N** |",
        f"| impulso per ugello (spinta + frenata) | {s['impulso_per_ugello_Ns']:.6g} N s |", "",
        "La frenata usa gli ugelli della faccia opposta con la stessa spinta.",
        "Il venturi legge `T_ugello_N` da `spinta.json`.", "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def export_svg(m: Motion, out: str) -> str:
    d = m.history()
    path = os.path.join(out, "moto.svg")
    fig, axes = plt.subplots(4, 1, figsize=(9, 11), sharex=True)
    panels = [("s", "posizione s [m]"), ("v", "velocità v [m/s]"),
              ("a", "accelerazione a [m/s²]"), ("T_ugello", "spinta per ugello [N]")]
    for ax, (key, label) in zip(axes, panels):
        ax.plot(d["t"], d[key], "b-", linewidth=2)
        ax.set_ylabel(label)
        ax.grid(True, linestyle=":", alpha=0.6)
        for tk in (m.t_acc, m.tempo - m.t_acc):
            ax.axvline(tk, color="k", linewidth=0.6, alpha=0.4)
    axes[-1].axhline(0.0, color="k", linewidth=0.6)
    axes[-1].set_xlabel("tempo t [s]")
    axes[0].set_title(f"Profilo {m.profilo}: {m.distanza:g} m in {m.tempo:g} s, "
                      f"T_ugello = {m.thrust_nozzle:.4g} N ({m.n_ugelli} ugelli)")
    fig.tight_layout()
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path


def _header(ws, row: int, names: List[str]) -> None:
    for col, name in enumerate(names, 1):
        c = ws.cell(row=row, column=col, value=name)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", wrap_text=True)


def export_xlsx(m: Motion, out: str) -> str:
    path = os.path.join(out, "spinta.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Sintesi"
    _header(ws, 1, ["grandezza", "valore", "unità"])
    s = m.summary()
    rows = [("distanza", m.distanza, "m"), ("tempo", m.tempo, "s"), ("massa", m.massa, "kg"),
            ("ugelli per faccia", m.n_ugelli, "-"), ("profilo", m.profilo, "-"),
            ("frazione di crociera", m.frazione_crociera, "-"),
            ("fattore di margine", m.fattore_margine, "-"),
            ("accelerazione", s["accelerazione_m_s2"], "m/s²"),
            ("tempo di accelerazione", s["t_accelerazione_s"], "s"),
            ("tempo di crociera", s["t_crociera_s"], "s"),
            ("velocità massima", s["v_max_m_s"], "m/s"),
            ("spinta della faccia", s["T_totale_N"], "N"),
            ("spinta per ugello", s["T_ugello_N"], "N"),
            ("impulso per ugello", s["impulso_per_ugello_Ns"], "N s")]
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            if isinstance(v, float):
                cell.number_format = "0.000000"
    ws.cell(row=14, column=1).font = Font(bold=True)
    ws.cell(row=14, column=2).font = Font(bold=True)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 16

    wp = wb.create_sheet("Profilo")
    _header(wp, 1, ["t [s]", "s [m]", "v [m/s]", "a [m/s²]", "T_ugello [N]"])
    d = m.history(201)
    for i in range(d["t"].size):
        for c, key in enumerate(("t", "s", "v", "a", "T_ugello"), 1):
            wp.cell(row=i + 2, column=c, value=float(d[key][i])).number_format = "0.000000"
    wp.freeze_panes = "A2"
    n = d["t"].size + 1
    x = Reference(wp, min_col=1, min_row=2, max_row=n)
    for col, title, anchor in ((3, "Velocità [m/s]", "G2"), (5, "Spinta per ugello [N]", "G20")):
        ch = ScatterChart()
        ch.title, ch.style = title, 13
        ch.x_axis.title = "t [s]"
        ch.series.append(Series(Reference(wp, min_col=col, min_row=1, max_row=n), x,
                                title_from_data=True))
        ch.legend = None
        wp.add_chart(ch, anchor)
    wb.save(path)
    return path


def export_all(m: Motion, out: str) -> List[str]:
    graphs, excel = os.path.join(out, "grafici"), os.path.join(out, "excel")
    os.makedirs(graphs, exist_ok=True)
    os.makedirs(excel, exist_ok=True)
    return [export_json(m, out), export_report(m, out), export_svg(m, graphs),
            export_xlsx(m, excel)]
