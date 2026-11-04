"""
duct.py
=======
All the output of an optimised duct, in risultati/<caso>/2_venturi/:

    00_sintesi/      RISULTATO.md, risultati.json  (dp for the fan, thrust, size)
    01_grafici/      .svg figures (plots_duct.py)
    02_excel/        venturi_risultati.xlsx (excel_duct.py)
    03_cad/          STEP, STL, DXF, CSV (cad_duct.py)
    04_cfd/          ParaView .vts 2D and 3D, point cloud .csv/.ply
    05_convergenza/  design.json, SLSQP histories, dp loop, grid study
"""

from __future__ import annotations

import glob
import json
import math
import os
import shutil
from typing import Dict, List, Optional

import numpy as np

from ..core.config import VenturiConfig
from ..geometry import MorphedGeometry
from .cad_duct import export_duct_cad, sample, tube_pieces
from .excel_duct import export_duct_xlsx
from .fields import duct_fields
from .paraview import export_paraview_2d, export_paraview_3d
from .plots_duct import export_duct_plots
from .tables import export_pointcloud

OUTPUT_DIRS = dict(sintesi="00_sintesi", grafici="01_grafici", excel="02_excel", cad="03_cad",
                   cfd="04_cfd", convergenza="05_convergenza")
ENVELOPE_TOL_MM = 1e-3


def output_dirs(root: str, clean: bool = True) -> Dict[str, str]:
    """The output folders under root, emptied first so no file of an older run stays."""
    dirs = {k: os.path.join(root, v) for k, v in OUTPUT_DIRS.items()}
    for d in dirs.values():
        if clean and os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    return dirs


def load_histories(conv_dir: str) -> Dict[str, List[dict]]:
    """SLSQP histories of the run, in the order they were written."""
    out = {}
    for f in sorted(glob.glob(os.path.join(conv_dir, "history_*.json")), key=os.path.getmtime):
        name = os.path.basename(f)[len("history_"):-len(".json")].replace("_", " ")
        with open(f, encoding="utf-8") as fh:
            out[name] = json.load(fh).get("history", [])
    return out


def cad_geometry(problem, design) -> MorphedGeometry:
    """The shape with the VenturiConfig the CAD export reads (wall thickness, inlet)."""
    case = problem.case
    g = problem.geometry(design)
    config = VenturiConfig(D=2.0 * g.R_inlet, beta=min(g.R_disk / g.R_inlet, 0.999),
                           fluid=case.fluid, p_inlet=case.p_amb, p_throat_target=None,
                           wall_thickness=case.spessore_parete)
    return MorphedGeometry(problem.layout, design, config)


def build_results(problem, design, summary: Dict, F: Dict, cad: Dict, info: Dict) -> Dict:
    case = problem.case
    g = F["geom"]
    est = info.get("estimate") or {}
    ck = cad["checks"]
    fits = (ck["diametro_esterno_mm"] <= case.D_ext_max * 1e3 + ENVELOPE_TOL_MM
            and ck["lunghezza_mm"] <= case.L_max * 1e3 + ENVELOPE_TOL_MM)
    return dict(
        ventola=dict(
            dp_disk_Pa=case.dp_disk, dp_errore_Pa=info.get("dp_error", float("nan")),
            D_ventola_m=2.0 * g.R_disk, z_centro_ventola_m=0.5 * (g.z_a + g.z_b),
            L_ventola_m=case.L_disk, portata_m3_s=summary["Q"],
            portata_massica_kg_s=summary["mass_flow"], V_disco_m_s=summary["V_disk"],
            potenza_fluido_W=summary["power"], densita_kg_m3=case.rho, V0_m_s=case.V0,
            spinta_rotore_N=case.dp_disk * math.pi * g.R_disk ** 2,
            tipo_dp="salto di pressione totale ASSIALE del disco attuatore (senza swirl)",
            mozzo_modellato=False,
            nota="z misurato dal piano d'ingresso del condotto (inizio della parete bagnata, "
                 "dopo la bocca d'imbocco). Il disco e pieno: il mozzo della ventola non e "
                 "nel modello del condotto. La spinta sul rotore e dp x area del disco; il "
                 "resto della spinta lo da il condotto (depressione sul labbro d'ingresso)."),
        spinta=dict(
            richiesta_N=case.T_target, sorgente=info.get("source", ""),
            calcolata_N=summary["thrust"], da_bilancio_forze_N=summary["thrust_from_forces"],
            errore_griglia_N=est.get("error", float("nan")),
            errore_griglia_pct=est.get("error_pct", float("nan")),
            estrapolata_N=est.get("extrapolated", float("nan")),
            affidabile=bool(est.get("reliable", False)),
            problemi="; ".join(est.get("problems", [])) or "-",
            spinta_su_potenza_N_W=summary["thrust_per_power"]),
        geometria=dict(
            D_ingresso_m=summary["D_inlet"], D_ventola_m=summary["D_disk"],
            D_uscita_m=summary["D_exit"], L_condotto_m=summary["L_total"],
            rapporto_aree_uscita_disco=summary["area_ratio"],
            D_esterno_tubo_mm=ck["diametro_esterno_mm"], L_tubo_mm=ck["lunghezza_mm"],
            D_esterno_max_mm=case.D_ext_max * 1e3, L_max_mm=case.L_max * 1e3,
            D_interno_max_mm=2e3 * case.R_int_max, spessore_parete_mm=ck["spessore_mm"],
            ingombro_rispettato=bool(fits)),
        flusso=dict(
            mach_max=summary["mach_max"], celle_flusso_invertito=summary["reversed_cells"],
            margine_separazione=summary["separation_margin"],
            salto_p0_disco_Pa=F["disk"]["salto_p0"],
            y_plus_max=float(np.max(F["wall"]["y_plus"])),
            V_getto_ideale_m_s=case.V_jet_ideal, V_uscita_media_m_s=summary["V_exit"]),
        numerica=dict(
            griglia=f"{case.Nz}x{case.Nr}", turbolenza=case.turbulence_model,
            griglie_studio=", ".join(est.get("grids", [])),
            esponente_T_dp=info.get("exponent", float("nan")),
            ciclo_dp_convergito=bool(info.get("converged", False)),
            STL_chiusi=all(v for k, v in ck.items() if k.endswith("_chiuso")),
            triangoli_tubo=ck["tubo_triangoli"], triangoli_fluido=ck["fluido_triangoli"]),
    )


def write_report(results: Dict, path: str) -> str:
    v, s, g, f, n = (results[k] for k in ("ventola", "spinta", "geometria", "flusso", "numerica"))
    warn = []
    if not s["affidabile"]:
        warn.append(f"- **Studio di griglia non affidabile**: {s['problemi']}.")
    if not g["ingombro_rispettato"]:
        warn.append("- **Il tubo esce dall'ingombro massimo.**")
    if f["celle_flusso_invertito"] > 0 or f["margine_separazione"] < 0:
        warn.append(f"- Flusso invertito in {f['celle_flusso_invertito']} celle, margine di "
                    f"separazione {f['margine_separazione']:+.3f}.")
    if not n["ciclo_dp_convergito"]:
        warn.append("- Il ciclo su Δp ha raggiunto il numero massimo di cicli.")
    lines = [
        "# Venturi: dalla spinta al salto di pressione", "",
        "## Per la ventola", "",
        "| grandezza | valore |", "|---|---|",
        f"| **Δp disco** | **{v['dp_disk_Pa']:.4f} ± {v['dp_errore_Pa']:.4f} Pa** |",
        f"| diametro ventola | {v['D_ventola_m'] * 1e3:.2f} mm |",
        f"| centro ventola da ingresso condotto | {v['z_centro_ventola_m'] * 1e3:.2f} mm |",
        f"| spessore assiale ventola | {v['L_ventola_m'] * 1e3:.2f} mm |",
        f"| portata | {v['portata_m3_s'] * 1e3:.4f} L/s ({v['portata_massica_kg_s'] * 1e3:.4f} g/s) |",
        f"| velocità sul disco | {v['V_disco_m_s']:.3f} m/s |",
        f"| potenza data al fluido (Δp·Q) | {v['potenza_fluido_W']:.4f} W |",
        f"| spinta sul rotore (Δp × area disco) | {v['spinta_rotore_N']:.4g} N |", "",
        "Il Δp è assiale, senza swirl: è quello che la ventola deve dare all'aria utile alla spinta.", "",
        "## Spinta", "",
        f"- richiesta per ugello: {s['richiesta_N']:.5g} N (da `{s['sorgente']}`)",
        f"- calcolata sulla griglia fine: {s['calcolata_N']:.5g} N, "
        f"dal bilancio delle forze {s['da_bilancio_forze_N']:.5g} N",
        f"- errore di griglia (GCI): ±{s['errore_griglia_N']:.4g} N "
        f"({s['errore_griglia_pct']:.2f} %), estrapolata {s['estrapolata_N']:.5g} N",
        f"- spinta / potenza: {s['spinta_su_potenza_N_W']:.4f} N/W", "",
        "## Geometria", "",
        f"- condotto: D ingresso {g['D_ingresso_m'] * 1e3:.2f} mm, D ventola "
        f"{g['D_ventola_m'] * 1e3:.2f} mm, D uscita {g['D_uscita_m'] * 1e3:.2f} mm, "
        f"L {g['L_condotto_m'] * 1e3:.2f} mm, A_uscita/A_disco {g['rapporto_aree_uscita_disco']:.3f}",
        f"- tubo: D esterno {g['D_esterno_tubo_mm']:.2f} mm (max {g['D_esterno_max_mm']:.2f}), "
        f"L {g['L_tubo_mm']:.2f} mm (max {g['L_max_mm']:.2f}), parete {g['spessore_parete_mm']:.2f} mm, "
        f"condotto interno max {g['D_interno_max_mm']:.2f} mm",
        f"- ingombro rispettato: {'sì' if g['ingombro_rispettato'] else 'NO'}", "",
        "## Flusso", "",
        f"- Mach massimo {f['mach_max']:.4f}, y+ massimo {f['y_plus_max']:.2f}",
        f"- salto di pressione totale sul disco (media pesata sulla portata): "
        f"{f['salto_p0_disco_Pa']:.3f} Pa",
        f"- getto ideale {f['V_getto_ideale_m_s']:.3f} m/s, velocità media d'uscita "
        f"{f['V_uscita_media_m_s']:.3f} m/s", "",
        "## Numerica", "",
        f"- griglia del risultato {n['griglia']}, studio di griglia su {n['griglie_studio']}, "
        f"modello `{n['turbolenza']}`",
        f"- esponente T ~ Δp^k: k = {n['esponente_T_dp']:.4f}",
        f"- STL chiusi: {'sì' if n['STL_chiusi'] else 'NO'}", "",
        "## Avvertenze", "",
        *(warn or ["- nessuna"]), "",
        "## Cartelle", "",
        "- `01_grafici/`: geometria, mappe del campo, profili assiali, parete, profili radiali, "
        "convergenza",
        "- `02_excel/venturi_risultati.xlsx`: tutti i numeri, foglio per argomento",
        "- `03_cad/`: `tubo`, `fluido`, `zona_disco` in STEP e STL (mm, asse x), patch STL del "
        "fluido per la CFD, profilo DXF e CSV",
        "- `04_cfd/`: campi per ParaView (2D e 3D) e nuvola di punti",
        "- `05_convergenza/`: `design.json`, storie SLSQP, ciclo su Δp, studio di griglia", "",
        "Nota: la spinta è quella interna netta; la resistenza esterna della gondola non è "
        "calcolata. Con disco ideale la spinta statica vale 2·Δp·A_uscita: a spinta data il Δp "
        "minimo chiede l'uscita più larga possibile. Con diametro e posizione della ventola "
        "liberi, l'ottimo tende quindi a un condotto dritto al diametro interno massimo, corto "
        "quanto i limiti permettono (meno attrito); i limiti di lunghezza minima e le perdite "
        "reali della ventola (mozzo, gioco di estremità) non sono nel modello.", "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def _json_safe(x):
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def export_duct_results(problem, design, summary: Dict, dirs: Dict[str, str],
                        info: Dict) -> Dict:
    """Write every output file; returns the results dictionary and the files."""
    case = problem.case
    geom = cad_geometry(problem, design)
    files: List[str] = []

    print("      CAD")
    cad = export_duct_cad(geom, case.L_disk, dirs["cad"])
    files += cad["files"]

    F = duct_fields(problem, design)
    results = build_results(problem, design, summary, F, cad, info)

    print("      grafici")
    tube = sample(tube_pieces(geom), 0.002, 0.5)
    histories = load_histories(dirs["convergenza"])
    grid = None
    est_file = os.path.join(dirs["convergenza"], "thrust_estimate.json")
    if os.path.isfile(est_file):
        with open(est_file, encoding="utf-8") as fh:
            grid = json.load(fh)
    steps = info.get("steps", [])
    files += export_duct_plots(F, tube, design, problem.layout, histories, steps, grid,
                               dirs["grafici"])

    print("      Excel")
    files.append(export_duct_xlsx(F, results, design, histories, steps, grid,
                                  os.path.join(dirs["excel"], "venturi_risultati.xlsx")))

    print("      CFD")
    c = F["cells"]
    extra = {"Total_Pressure": c["p0"], "Mach": c["mach"], "Turbulent_Viscosity_Ratio": c["nu_ratio"]}
    p_abs = c["p"] + case.p_amb
    mesh = problem.solve(design).system.mesh
    files += [export_paraview_2d(mesh, c["uz"], c["ur"], p_abs, dirs["cfd"], extra),
              export_paraview_3d(mesh, c["uz"], c["ur"], p_abs, dirs["cfd"], extra=extra),
              *export_pointcloud(mesh, c["uz"], c["ur"], p_abs, dirs["cfd"])]

    results = _json_safe(results)
    path = os.path.join(dirs["sintesi"], "risultati.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, ensure_ascii=False)
    files += [path, write_report(results, os.path.join(dirs["sintesi"], "RISULTATO.md"))]
    return dict(results=results, files=[f for f in files if f and os.path.isfile(f)])
