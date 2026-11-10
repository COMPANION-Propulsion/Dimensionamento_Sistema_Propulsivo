"""
excel_duct.py
=============
venturi_risultati.xlsx of an optimised duct. Sheets:

    Sintesi        inputs, result for the fan, checks
    Geometria      wall profile and control points
    Assiale        section values along the axis (with charts)
    Parete         wall values (with charts)
    Radiale        profiles across the duct at five stations
    Campo          every cell of the grid
    Ottimizzazione SLSQP history, every grid and cycle
    Iterazioni_dp  dp loop
    Griglia        grid study and error band

Lengths in mm, pressures in Pa relative to p_amb.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import numpy as np
from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.styles import Alignment, Font, PatternFill

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SECTION_FONT = Font(bold=True, color="1F4E78", size=12)
MM = 1e3


def _table(ws, header: Sequence[str], rows, start_row: int = 1, fmt: str = "0.000000") -> int:
    for c, name in enumerate(header, 1):
        cell = ws.cell(row=start_row, column=c, value=name)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    r = start_row
    for r, row in enumerate(rows, start_row + 1):
        for c, v in enumerate(row, 1):
            if isinstance(v, (np.floating, np.integer)):
                v = v.item()
            cell = ws.cell(row=r, column=c, value=v)
            if isinstance(v, float):
                cell.number_format = fmt
    for c in range(1, len(header) + 1):
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = 16
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    return r


def _chart(ws, title: str, x_col: int, y_cols: Sequence[int], n: int, anchor: str,
           y_title: str, x_title: str = "z [mm]") -> None:
    ch = ScatterChart()
    ch.title, ch.style, ch.height, ch.width = title, 13, 8, 16
    ch.x_axis.title, ch.y_axis.title = x_title, y_title
    x = Reference(ws, min_col=x_col, min_row=2, max_row=n)
    for c in y_cols:
        s = Series(Reference(ws, min_col=c, min_row=1, max_row=n), x, title_from_data=True)
        s.marker.symbol = "none"
        s.smooth = False
        ch.series.append(s)
    ws.add_chart(ch, anchor)


def export_duct_xlsx(F: Dict, results: Dict, design: np.ndarray, histories: Dict[str, List[dict]],
                     steps: List[dict], grid: Optional[dict], path: str) -> str:
    geom, case = F["geom"], F["case"]
    wb = Workbook()

    ws = wb.active
    ws.title = "Sintesi"
    rows = []
    for group, items in results.items():
        if not isinstance(items, dict):
            continue
        rows.append((group.upper(), None, None))
        for k, v in items.items():
            if isinstance(v, dict) or isinstance(v, (list, tuple)):
                continue
            unit = k.rsplit("_", 1)[-1] if "_" in k else ""
            rows.append((k, v, unit if unit in ("Pa", "N", "m", "mm", "W", "s", "kg") else ""))
    last = _table(ws, ["grandezza", "valore", "unità"], rows)
    for r in range(2, last + 1):
        if ws.cell(row=r, column=2).value is None:
            ws.cell(row=r, column=1).font = SECTION_FONT
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 20

    wg = wb.create_sheet("Geometria")
    z, r = geom.profile_points(601)
    last = _table(wg, ["z [mm]", "R [mm]", "dR/dz [-]"],
                  zip(z * MM, r * MM, geom.radius_derivative(z)))
    _chart(wg, "Profilo della parete", 1, [2], last, "E2", "R [mm]")
    (_, p_up), (_, p_dn) = geom.bspline_curves()
    row0 = 22
    wg.cell(row=row0, column=5, value="Punti di controllo (poli delle B-spline)").font = SECTION_FONT
    for c, h in enumerate(["tratto", "z [mm]", "r [mm]"], 5):
        cell = wg.cell(row=row0 + 1, column=c, value=h)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    k = row0 + 2
    for name, P in (("imbocco", p_up), ("diffusore", p_dn)):
        for zz, rr in P:
            wg.cell(row=k, column=5, value=name)
            wg.cell(row=k, column=6, value=float(zz * MM)).number_format = "0.0000"
            wg.cell(row=k, column=7, value=float(rr * MM)).number_format = "0.0000"
            k += 1
    wg.cell(row=k + 1, column=5, value="Vettore di progetto [m]").font = SECTION_FONT
    for i, v in enumerate(design):
        wg.cell(row=k + 2 + i, column=5, value=f"x[{i}]")
        wg.cell(row=k + 2 + i, column=6, value=float(v)).number_format = "0.0000000"

    s = F["sections"]
    wa = wb.create_sheet("Assiale")
    last = _table(wa, ["z [mm]", "R [mm]", "A [mm²]", "V media [m/s]", "V asse [m/s]",
                       "p media [Pa]", "p asse [Pa]", "p parete [Pa]", "p0 media [Pa]",
                       "Mach max [-]", "ν_t/ν max [-]"],
                  zip(s["z"] * MM, s["R"] * MM, s["A"] * MM ** 2, s["V_mean"], s["V_axis"],
                      s["p_mean"], s["p_axis"], s["p_wall"], s["p0_mean"], s["mach_max"],
                      s["nu_ratio_max"]))
    _chart(wa, "Pressione statica e totale", 1, [6, 9], last, "M2", "p - p_amb [Pa]")
    _chart(wa, "Velocità", 1, [4, 5], last, "M20", "V [m/s]")

    w = F["wall"]
    wp = wb.create_sheet("Parete")
    last = _table(wp, ["z [mm]", "R [mm]", "p [Pa]", "τ_w [Pa]", "c_f [-]", "y+ [-]",
                       "u parete [m/s]"],
                  zip(w["z"] * MM, w["R"] * MM, w["p"], w["tau_w"], w["cf"], w["y_plus"],
                      w["u_wall"]))
    _chart(wp, "Coefficiente d'attrito", 1, [5], last, "I2", "c_f [-]")
    _chart(wp, "y+", 1, [6], last, "I20", "y+ [-]")

    wr = wb.create_sheet("Radiale")
    col = 1
    header = ["r/R", "r [mm]", "u_z [m/s]", "u_r [m/s]", "p [Pa]", "p0 [Pa]"]
    for name, d in F["radial"].items():
        wr.cell(row=1, column=col, value=f"{name}, z = {d['z'] * MM:.2f} mm").font = SECTION_FONT
        for k, h in enumerate(header):
            cell = wr.cell(row=2, column=col + k, value=h)
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        for i, row in enumerate(zip(d["eta"], d["r"] * MM, d["uz"], d["ur"], d["p"], d["p0"])):
            for k, v in enumerate(row):
                wr.cell(row=3 + i, column=col + k, value=float(v)).number_format = "0.000000"
        col += len(header) + 1
    wr.freeze_panes = "A3"

    c = F["cells"]
    wc = wb.create_sheet("Campo")
    _table(wc, ["z [mm]", "r [mm]", "u_z [m/s]", "u_r [m/s]", "|V| [m/s]", "p [Pa]",
                "p0 [Pa]", "Mach [-]", "ν_t/ν [-]", "volume [mm³]"],
           zip(*(a.ravel() for a in (c["z"] * MM, c["r"] * MM, c["uz"], c["ur"], c["V"],
                                     c["p"], c["p0"], c["mach"], c["nu_ratio"],
                                     c["vol"] * MM ** 3))), fmt="0.00000")

    wo = wb.create_sheet("Ottimizzazione")
    rows = []
    for name, hist in histories.items():
        for h in hist:
            rows.append([name] + [h.get(k) for k in ("iteration", "time_s", "thrust", "D_inlet",
                                                        "D_disk", "D_exit", "L_total", "mach_max")]
                        + [h.get("margine_separazione", h.get("separation")),
                           h.get("geometric_min"), h.get("violation")])
    _table(wo, ["fase", "iterazione", "tempo [s]", "spinta [N]", "D ingresso [m]",
                "D ventola [m]", "D uscita [m]", "L [m]", "Mach massimo [-]",
                "margine separazione [-]", "vincolo geometrico min [-]",
                "violazione vincoli [-]"], rows)

    wd = wb.create_sheet("Iterazioni_dp")
    keys = ["ciclo", "tipo", "griglia", "dp_disk", "spinta", "errore_relativo", "esponente"]
    _table(wd, ["ciclo", "tipo", "griglia", "Δp [Pa]", "spinta [N]", "errore relativo [-]",
                "esponente k [-]"], ([st.get(k) for k in keys] for st in steps))

    if grid:
        wq = wb.create_sheet("Griglia")
        last = _table(wq, ["griglia", "celle", "convergito", "y+ max", "spinta [N]",
                           "spinta da forze [N]", "tempo [s]"],
                      ([f"{g['Nz']}x{g['Nr']}", g["cells"], g["converged"], g["y_plus"],
                        g["thrust"], g["thrust_from_forces"], g["time_s"]]
                       for g in grid["grids"]))
        est = grid["estimate"]
        info = [("valore (griglia fine)", est["value"]), ("estrapolata", est["extrapolated"]),
                ("errore ±", est["error"]), ("errore [%]", est["error_pct"]),
                ("ordine osservato", est["order"]), ("affidabile", est["reliable"]),
                ("problemi", "; ".join(est["problems"]) or "-"),
                ("metodo della banda", est.get("method", "GCI")),
                ("note", "; ".join(est.get("notes", [])) or "-")]
        for i, (k, v) in enumerate(info):
            wq.cell(row=last + 2 + i, column=1, value=k).font = Font(bold=True)
            wq.cell(row=last + 2 + i, column=2, value=v)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return path
