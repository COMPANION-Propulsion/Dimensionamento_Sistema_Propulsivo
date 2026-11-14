"""
duct.py
=======
All the output of an optimised duct, in risultati/<caso>/2_venturi/:

    00_sintesi/      RISULTATO.md, risultati.json  (dp for the fan, thrust, size)
    01_grafici/      .svg figures (plots_duct.py)
    02_excel/        venturi_risultati.xlsx (excel_duct.py)
    03_cad/          STEP, STL, DXF, CSV (cad_duct.py)
    04_cfd/          ParaView .vts of the meridional plane, point cloud .csv
                     (the 3D field is the plane revolved: Rotational Extrusion in ParaView)
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


def _nd(x, fmt: str) -> str:
    """x formatted, or "n.d." when it is missing (None/NaN): e.g. no grid study in an
    intermediate band pass."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n.d."
    return format(x, fmt)

from ..core.config import VenturiConfig
from ..geometry import MorphedGeometry
from .cad_duct import export_duct_cad, sample, tube_pieces
from .excel_duct import export_duct_xlsx
from .fields import duct_fields
from .paraview import export_paraview_2d
from .plots_duct import (area_ratio_of, export_duct_plots, plot_alternatives, plot_exit_sweep,
                         plot_history)
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
                           wall_thickness=case.spessore_parete,
                           bell_radius_ratio=case.raggio_bocca_su_D)
    return MorphedGeometry(problem.layout, design, config)


def total_pressure_losses(case, F: Dict, Q: float) -> Dict:
    """Total-pressure losses of the duct, from the mass-weighted p0 of the sections.

    Far upstream p0 = rho V0^2 / 2 (gauge). With no losses the jet would leave with
    p0 = that + dp_disk; what is missing is split by where it is lost:

        imbocco    far upstream -> just before the disk band (intake, wall friction)
        disco      across the band: dp_disk - measured jump (friction in the band)
        valle      just after the band -> exit plane (diffuser or nozzle, friction)

    The bell mouth of the CAD is outside the flow domain: its loss (about 4 % of the
    inlet dynamic pressure for a rounded inlet) is not included.
    """
    d = F["disk"]
    p0_inf = 0.5 * case.rho * case.V0 ** 2
    parts = dict(imbocco_Pa=p0_inf - d["p0_monte"], disco_Pa=case.dp_disk - d["salto_p0"],
                 valle_Pa=d["p0_valle"] - d["p0_uscita"])
    total = p0_inf + case.dp_disk - d["p0_uscita"]
    return dict(**parts, totale_Pa=total, totale_su_dp_disco=total / case.dp_disk,
                potenza_persa_W=total * Q, p0_uscita_Pa=d["p0_uscita"],
                nota="Perdite di pressione totale media pesata sulla portata; bocca d'imbocco "
                     "del CAD non inclusa (fuori dal dominio di calcolo).")


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
            scarto_bilancio_forze_pct=summary.get("thrust_check_pct", float("nan")),
            beta_spinta_su_mdot_v=summary.get("beta", float("nan")),
            errore_griglia_N=est.get("error", float("nan")),
            errore_griglia_pct=est.get("error_pct", float("nan")),
            estrapolata_N=est.get("extrapolated", float("nan")),
            affidabile=bool(est.get("reliable", False)),
            problemi="; ".join(est.get("problems", [])) or "-",
            metodo_banda_griglia=est.get("method", "GCI"),
            note_griglia="; ".join(est.get("notes", [])) or "-",
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
        perdite=total_pressure_losses(case, F, summary["Q"]),
        numerica=dict(
            griglia=f"{case.Nz}x{case.Nr}", turbolenza=case.turbulence_model,
            griglie_studio=", ".join(est.get("grids", [])),
            esponente_T_dp=info.get("exponent", float("nan")),
            ciclo_dp_convergito=bool(info.get("converged", False)),
            curva_ventola=("fittizia" if (info.get("curve") or {}).get("fittizia")
                           else ("da input" if info.get("curve") else "nessuna (dp fisso per la spinta)")),
            STL_chiusi=all(v for k, v in ck.items() if k.endswith("_chiuso")),
            triangoli_tubo=ck["tubo_triangoli"], triangoli_fluido=ck["fluido_triangoli"]),
    )


def scan_lines(scan):
    if not scan:
        return []
    b = scan["migliore"]
    ok = [c for c in scan["casi"] if c.get("stato") == "ok"]
    lines = ["## Scansione della forma", "",
             f"Criterio: {scan['criterio']}. D ventola fisso {scan['D_ventola_mm']:.1f} mm, "
             f"{len(ok)} casi risolti su {len(scan['casi'])} (gli altri: semiangolo, ingombro o non "
             f"convergenti, vedi `05_convergenza/scansione.json` e `01_grafici/scansione.svg`).", "",
             "| D uscita [mm] | L diffusore [mm] | semiangolo [°] | spinta [N] | dp [Pa] | τ_w min diffusore [Pa] |",
             "|---|---|---|---|---|---|"]
    for c in ok:
        star = " ★" if c is b or (c["D_uscita_mm"] == b["D_uscita_mm"] and c["L_diffusore_mm"] == b["L_diffusore_mm"]) else ""
        lines.append(f"| {c['D_uscita_mm']:.1f}{star} | {c['L_diffusore_mm']:.1f} | {c['semiangolo_deg']:.2f} | "
                     f"{c['spinta_N']:.5f} | {c['dp_Pa']:.2f} | {c['tau_w_min_diffusore_Pa']:+.4f} |")
    if scan.get("curva_ventola") and scan["curva_ventola"].get("fittizia"):
        lines += ["", "**La curva della ventola usata è un ESEMPIO FITTIZIO: i numeri non valgono per il progetto.**"]
    return lines + [""]


PROFILE_KEYS = ("profilo_z_mm", "profilo_R_mm")


def _alternative_summary(alt: Dict) -> Dict:
    """The alternatives without the wall profiles (results.json is read by the fan script)."""
    out = {k: v for k, v in alt.items() if k != "casi"}
    out["casi"] = [{k: v for k, v in row.items() if k not in PROFILE_KEYS} for row in alt["casi"]]
    return out


def _num(v, fmt: str) -> str:
    return "-" if v is None else format(v, fmt)


def alternative_lines(alt):
    if not alt or not alt.get("casi"):
        return []
    ref = alt.get("riferimento", "ottimo")
    casi = sorted(alt["casi"], key=lambda c: c["L_tubo_mm"] if c.get("L_tubo_mm") is not None
                  else math.inf)
    lines = ["## Confronto alternative di lunghezza", "",
             f"Griglia {alt.get('griglia', '-')}, spinta richiesta {_num(alt.get('T_target_N'), '.5g')} N. "
             "Confronto relativo sulla stessa griglia di ottimizzazione; studio di griglia, CAD e "
             "risultati per la ventola solo per l'ottimo; per un'alternativa: `python -m "
             "venturi_designer.analysis.grid_study --duct 05_convergenza/alternative/<id>/design.json`.",
             "", "Δp richiesto: Δp della ventola per la spinta voluta, a parità di spinta.", "",
             "| L tubo [mm] | D ingresso [mm] | D ventola [mm] | D uscita [mm] | "
             "semiangolo imbocco / diffusore [°] | Δp richiesto [Pa] | Δ Δp [%] | potenza [W] | "
             "Δ potenza [%] | area parete [cm²] | stato |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in casi:
        star = " ★" if c.get("id") == ref else ""
        lines.append(
            f"| {_num(c.get('L_tubo_mm'), '.2f')}{star} | {_num(c.get('D_ingresso_mm'), '.2f')} | "
            f"{_num(c.get('D_ventola_mm'), '.2f')} | {_num(c.get('D_uscita_mm'), '.2f')} | "
            f"{_num(c.get('semiangolo_imbocco_deg'), '.2f')} / {_num(c.get('semiangolo_diffusore_deg'), '.2f')} | "
            f"{_num(c.get('dp_Pa'), '.2f')} | {_num(c.get('delta_dp_pct'), '+.2f')} | "
            f"{_num(c.get('potenza_W'), '.4f')} | {_num(c.get('delta_potenza_pct'), '+.2f')} | "
            f"{_num(c.get('area_parete_cm2'), '.2f')} | {str(c.get('stato', '-')).replace('|', '/')} |")
    lines += ["", "Perdite di pressione totale (Δp = p0 uscita + perdita totale):", "",
              "| L tubo [mm] | p0 uscita [Pa] | perdita imbocco [Pa] | perdita disco [Pa] | "
              "perdita valle [Pa] | perdita totale [Pa] | perdita totale [% di Δp] | potenza persa [W] |",
              "|---|---|---|---|---|---|---|---|"]
    for c in casi:
        star = " ★" if c.get("id") == ref else ""
        lines.append(
            f"| {_num(c.get('L_tubo_mm'), '.2f')}{star} | {_num(c.get('p0_uscita_Pa'), '.2f')} | "
            f"{_num(c.get('perdita_imbocco_Pa'), '.3f')} | {_num(c.get('perdita_disco_Pa'), '.3f')} | "
            f"{_num(c.get('perdita_valle_Pa'), '.3f')} | {_num(c.get('perdita_totale_Pa'), '.3f')} | "
            f"{_num(c.get('perdita_totale_pct'), '.2f')} | {_num(c.get('potenza_persa_W'), '.4f')} |")
    return lines + [""]


def _sino(v) -> str:
    return "-" if v is None else ("sì" if v else "no")


def _sweep_summary(sw: Dict) -> Dict:
    """La scansione senza le liste di profilo (results.json è letto dalla ventola)."""
    out = {k: v for k, v in sw.items() if k != "punti"}
    out["punti"] = [{k: v for k, v in row.items() if k not in PROFILE_KEYS} for row in sw["punti"]]
    return out


def _sweep_angle(c: Dict):
    return c.get("semiangolo_convergente_deg") if c.get("tipo") == "convergente" \
        else c.get("semiangolo_diffusore_deg")


def _sweep_verdict(sw: Dict, rows: List[Dict]) -> str:
    """Una frase: qual è il Δp minimo entro i limiti e perché l'ottimo non va oltre."""
    ref_id = sw.get("riferimento", "ottimo")
    ref = next((c for c in rows if c.get("id") == ref_id), None)
    valid = [c for c in rows if c.get("dp_Pa") is not None and c.get("entro_limite_angolo", True)
             and not c.get("separato")]
    if not valid:
        return "Nessun punto della scansione è entro i limiti d'angolo e non separato."
    best = min(valid, key=lambda c: c["dp_Pa"])
    txt = (f"Il Δp minimo fra i punti entro i limiti d'angolo e non separati è al punto "
           f"s = {best['s']:.2f} (D uscita {_num(best.get('D_uscita_mm'), '.2f')} mm, "
           f"Δp {best['dp_Pa']:.2f} Pa)")
    if ref is None:
        return txt + "."
    if best.get("id") == ref_id:
        txt += ", cioè l'ottimo."
    else:
        txt += (f", diverso dall'ottimo `{ref_id}` (Δp {_num(ref.get('dp_Pa'), '.2f')} Pa): la "
                "scansione è campionata, il minimo può stare fra due punti.")
    more = sorted([c for c in rows if c["s"] > ref["s"]], key=lambda c: c["s"])
    if not more:
        dmax = max((c["D_uscita_mm"] for c in rows if c.get("D_uscita_mm") is not None), default=None)
        if dmax is not None and ref.get("D_uscita_mm") is not None and ref["D_uscita_mm"] >= dmax - 1e-3:
            why = (f"è già al diametro interno massimo della scansione (D_int_max = {dmax:.2f} mm, "
                   "ingombro del tubo)")
        else:
            why = "non ci sono punti più aperti nella scansione"
    else:
        nxt = more[0]
        where = f"al punto successivo (s = {nxt['s']:.2f}, D uscita {_num(nxt.get('D_uscita_mm'), '.2f')} mm)"
        if nxt.get("dp_Pa") is None:
            why = f"oltre, {where}, il solver non converge"
        elif nxt.get("separato"):
            why = (f"oltre, {where}, il diffusore separa (τ_w min "
                   f"{_num(nxt.get('tau_w_min_diffusore_Pa'), '+.4f')} Pa): è il limite")
        elif not nxt.get("entro_limite_angolo", True):
            why = (f"oltre, {where}, il semiangolo {_num(_sweep_angle(nxt), '.2f')}° supera il "
                   f"limite di {_num(sw.get('limite_semiangolo_deg'), '.1f')}°: è il limite d'angolo")
        else:
            why = (f"oltre, {where}, il Δp sale a {nxt['dp_Pa']:.2f} Pa: l'ottimo è un minimo interno")
    return f"{txt} L'ottimo non va oltre: {why}."


def exit_sweep_lines(sw: Optional[Dict]) -> List[str]:
    if not sw or not sw.get("punti"):
        return []
    rows = sorted(sw["punti"], key=lambda c: c["s"])
    ref = sw.get("riferimento", "ottimo")
    lines = ["## Uscita convergente / divergente", "",
             f"Scansione dell'apertura del diffusore sull'ottimo, con imbocco, ventola e lunghezza "
             f"fissi: s = 1 è l'ottimo, s = 0 uscita dritta, s < 0 convergente. Griglia "
             f"{sw.get('griglia', '-')}, spinta richiesta {_num(sw.get('T_target_N'), '.5g')} N. "
             f"Limiti: semiangolo divergente {_num(sw.get('limite_semiangolo_deg'), '.1f')}°, "
             f"convergente {_num(sw.get('limite_convergente_deg'), '.1f')}°, τ_w minimo non negativo.", "",
             "| s | tipo | D uscita [mm] | A uscita / A ventola [-] | semiangolo [°] | Δp [Pa] | "
             "Δ Δp [%] | potenza [W] | perdita totale [Pa] | τ_w min [Pa] | entro limiti | "
             "separato | stato |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in rows:
        star = " ★" if c.get("id") == ref else ""
        lines.append(
            f"| {c['s']:+.2f}{star} | {c.get('tipo', '-')} | {_num(c.get('D_uscita_mm'), '.2f')} | "
            f"{_num(area_ratio_of(c), '.3f')} | {_num(_sweep_angle(c), '.2f')} | "
            f"{_num(c.get('dp_Pa'), '.2f')} | {_num(c.get('delta_dp_pct'), '+.2f')} | "
            f"{_num(c.get('potenza_W'), '.4f')} | {_num(c.get('perdita_totale_Pa'), '.3f')} | "
            f"{_num(c.get('tau_w_min_diffusore_Pa'), '+.4f')} | {_sino(c.get('entro_limite_angolo'))} | "
            f"{_sino(c.get('separato'))} | {str(c.get('stato', '-')).replace('|', '/')} |")
    return lines + ["", _sweep_verdict(sw, rows), ""]


def history_lines(history: Optional[Dict]) -> List[str]:
    if not history or not history.get("scelta"):
        return []
    passi = history["passi"] if isinstance(history.get("passi"), list) else []
    n_passi = len(passi) or history.get("n_passi", "-")
    lines = ["## Come si è arrivati alla scelta", "",
             f"Percorso dell'ottimizzatore in {n_passi} passi: scansione, ottimizzazione SLSQP, secante "
             "su Δp. Grafico in `01_grafici/storico_ottimizzazione.svg`, foglio `Storico` in Excel.", "",
             "| punto | passo | fase | D uscita [mm] | D ventola [mm] | L condotto [mm] | spinta [N] | "
             "Δp [Pa] |",
             "|---|---|---|---|---|---|---|---|"]
    marks = []
    if passi:
        marks.append((f"partenza ({passi[0].get('fase', '-')})", passi[0]))
        cicli = sorted({p.get("ciclo") for p in passi
                        if p.get("fase") == "ottimizzazione" and p.get("ciclo") is not None})
        for ciclo in cicli:
            last = [p for p in passi if p.get("fase") == "ottimizzazione" and p.get("ciclo") == ciclo][-1]
            marks.append((f"fine ciclo {ciclo} di ottimizzazione", last))
    marks.append(("**scelta finale**", history["scelta"]))
    for label, p in marks:
        lines.append(
            f"| {label} | {_num(p.get('n'), '.0f')} | {p.get('fase', '-')} | "
            f"{_num(p.get('D_uscita_mm'), '.2f')} | {_num(p.get('D_ventola_mm'), '.2f')} | "
            f"{_num(p.get('L_condotto_mm'), '.2f')} | {_num(p.get('spinta_N'), '.5g')} | "
            f"{_num(p.get('dp_Pa'), '.2f')} |")
    return lines + [""]


_BAND_METHOD = {"assente": "nessuno studio in questa passata", "GCI": "GCI", "flat": "griglie coincidenti, 1.25 x dispersione",
                "oscillatory": "risultato oscillante, 1.25 x dispersione",
                "reference order": "GCI con ordine di riferimento p = 1"}


def write_report(results: Dict, path: str, history: Optional[Dict] = None) -> str:
    """RISULTATO.md. history: lo storico completo (passi); senza, solo la scelta di results."""
    v, s, g, f, n = (results[k] for k in ("ventola", "spinta", "geometria", "flusso", "numerica"))
    pl = results["perdite"]
    warn = []
    if not s["affidabile"]:
        warn.append(f"- **Studio di griglia non affidabile**: {s['problemi']}.")
    elif s.get("metodo_banda_griglia") == "reference order":
        warn.append("- Studio di griglia: ordine osservato non plausibile ma differenze piccole; "
                    f"banda dalla GCI con ordine di riferimento p = 1 ({s['note_griglia']}).")
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
        f"| **Δp disco** | **{v['dp_disk_Pa']:.4f} ± {_nd(v['dp_errore_Pa'], '.4f')} Pa** |",
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
        f"dal bilancio delle forze {s['da_bilancio_forze_N']:.5g} N "
        f"(scarto {s['scarto_bilancio_forze_pct']:+.2f} %, deve stare entro ±1 %)",
        f"- β = spinta / (ṁ v_media,uscita) = {s['beta_spinta_su_mdot_v']:.3f} "
        f"(1 = getto uniforme; > 1 profilo non uniforme)",
        f"- errore di griglia ({_BAND_METHOD.get(s.get('metodo_banda_griglia', 'GCI'), 'GCI')}): "
        f"±{_nd(s['errore_griglia_N'], '.4g')} N "
        f"({_nd(s['errore_griglia_pct'], '.2f')} %), estrapolata {_nd(s['estrapolata_N'], '.5g')} N"
        + (f"; nota: {s['note_griglia']}" if s.get("note_griglia", "-") != "-" else ""),
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
        "## Perdite di pressione totale del condotto", "",
        "| tratto | perdita [Pa] | % del Δp disco |", "|---|---|---|",
        *[f"| {name} | {pl[k]:.3f} | {100 * pl[k] / v['dp_disk_Pa']:.2f} % |"
          for name, k in (("imbocco → disco", "imbocco_Pa"), ("banda del disco", "disco_Pa"),
                          ("disco → uscita", "valle_Pa"), ("**totale**", "totale_Pa"))],
        "",
        f"Potenza persa {pl['potenza_persa_W']:.4f} W su {v['potenza_fluido_W']:.4f} W date "
        f"all'aria. La bocca d'imbocco del CAD è fuori dal dominio di calcolo e non è inclusa.", "",
        *(scan_lines(results.get("scansione"))),
        *(alternative_lines(results.get("alternative"))),
        *(exit_sweep_lines(results.get("uscita"))),
        *(history_lines(history or results.get("storico"))),
        "## Numerica", "",
        f"- griglia del risultato {n['griglia']}, studio di griglia su {n['griglie_studio']}, "
        f"modello `{n['turbolenza']}`",
        f"- esponente T ~ Δp^k: k = {n['esponente_T_dp']:.4f}",
        f"- STL chiusi: {'sì' if n['STL_chiusi'] else 'NO'}", "",
        "## Avvertenze", "",
        *(warn or ["- nessuna"]), "",
        "## Cartelle", "",
        "- `01_grafici/`: geometria, mappe del campo, profili assiali, parete, profili radiali, "
        "convergenza, alternative, uscita, storico dell'ottimizzazione",
        "- `02_excel/venturi_risultati.xlsx`: tutti i numeri, foglio per argomento",
        "- `03_cad/`: `tubo`, `fluido`, `zona_disco` in STEP e STL (mm, asse x), patch STL del "
        "fluido per la CFD, profilo DXF e CSV",
        "- `04_cfd/`: campo sul piano meridiano per ParaView (per il 3D: filtro Rotational "
        "Extrusion attorno all'asse x) e nuvola di punti CSV",
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
    alt = info.get("alternatives") or None
    if alt:
        files += plot_alternatives(alt, dirs["grafici"])
    sweep = info.get("exit_sweep") or None
    if sweep:
        files += plot_exit_sweep(sweep, dirs["grafici"])
    history = info.get("history") or None
    if history and history.get("passi"):
        files += plot_history(history, dirs["grafici"])

    print("      Excel")
    files.append(export_duct_xlsx(F, results, design, histories, steps, grid,
                                  os.path.join(dirs["excel"], "venturi_risultati.xlsx"),
                                  alternative=alt, exit_sweep=sweep, history=history))

    print("      CFD")
    c = F["cells"]
    extra = {"Total_Pressure": c["p0"], "Mach": c["mach"], "Turbulent_Viscosity_Ratio": c["nu_ratio"]}
    p_abs = c["p"] + case.p_amb
    mesh = problem.solve(design).system.mesh
    files += [export_paraview_2d(mesh, c["uz"], c["ur"], p_abs, dirs["cfd"], extra),
              *export_pointcloud(mesh, c["uz"], c["ur"], p_abs, dirs["cfd"], ply=False)]

    if info.get("scan"):
        results["scansione"] = info["scan"]
    if alt:
        results["alternative"] = _alternative_summary(alt)
    if sweep:
        results["uscita"] = _sweep_summary(sweep)
    if history and history.get("scelta"):
        results["storico"] = dict(scelta=history["scelta"], n_passi=len(history.get("passi") or []))
    results = _json_safe(results)
    path = os.path.join(dirs["sintesi"], "risultati.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, ensure_ascii=False)
    files += [path, write_report(results, os.path.join(dirs["sintesi"], "RISULTATO.md"),
                                 history=history)]
    return dict(results=results, files=[f for f in files if f and os.path.isfile(f)])
