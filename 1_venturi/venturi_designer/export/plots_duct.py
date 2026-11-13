"""
plots_duct.py
=============
Figures (.svg) of an optimised duct, one subject per file:

    geometria            wall, tube, size limits, fan, control points
    campo_*              maps of |V|, u_z, u_r, static and total pressure,
                         Mach and nu_t/nu, on the whole section (mirrored)
    profili_assiali      section values along the axis
    parete               pressure, shear, friction coefficient and y+ on the wall
    profili_radiali      u_z and total pressure across the duct at five stations
    ottimizzazione       thrust and fan diameter along the shape optimisation
    iterazioni_dp        dp and thrust along the dp loop
    studio_griglia       thrust against cell size, with the error band
    alternative_*        fixed-length alternatives: dp and power, losses, wall profiles,
                         weight front, geometry, losses in %, separation, thrust per power
                         (plot_alternatives, only if there are alternatives)
    uscita_*             exit sweep against the area ratio: dp and power, losses, limits,
                         profiles (plot_exit_sweep, only if there is a sweep)
    storico_ottimizzazione  path of the optimiser, by phase (plot_history)
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

CMAP = "RdYlBu_r"
LEVELS = 24
MM = 1e3


def _save(fig, path: str) -> str:
    fig.tight_layout()
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return path


def _disk_band(ax, geom, L_disk: float, **kw) -> None:
    zc = 0.5 * (geom.z_a + geom.z_b)
    ax.axvspan((zc - 0.5 * L_disk) * MM, (zc + 0.5 * L_disk) * MM, color="0.5", alpha=0.18,
               label=kw.pop("label", None), **kw)


def plot_geometry(F: Dict, tube: np.ndarray, design: np.ndarray, layout, path: str) -> str:
    geom, case = F["geom"], F["case"]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    z, r = geom.profile_points(800)
    ax.fill(tube[:, 0], tube[:, 1], color="0.75", label="tubo")
    ax.fill(tube[:, 0], -tube[:, 1], color="0.75")
    ax.plot(z * MM, r * MM, "b-", lw=1.8, label="parete interna")
    ax.plot(z * MM, -r * MM, "b-", lw=1.8)
    z0 = tube[:, 0].min()
    ax.add_patch(Rectangle((z0, -case.R_ext * MM), case.L_max * MM, case.D_ext_max * MM,
                           fill=False, ls="--", ec="r", lw=1.2, label="ingombro massimo"))
    for s in (1, -1):
        ax.axhline(s * case.R_int_max * MM, color="m", ls=":", lw=1,
                   label="condotto interno massimo" if s > 0 else None)
    zc = 0.5 * (geom.z_a + geom.z_b)
    ax.add_patch(Rectangle(((zc - 0.5 * case.L_disk) * MM, -geom.R_disk * MM),
                           case.L_disk * MM, 2 * geom.R_disk * MM, color="g", alpha=0.35,
                           label=f"ventola D = {2 * geom.R_disk * MM:.1f} mm"))
    (_, p_up), (_, p_dn) = geom.bspline_curves()
    for p in (p_up, p_dn):
        ax.plot(p[:, 0] * MM, p[:, 1] * MM, "ko--", ms=3, lw=0.6, alpha=0.6)
    ax.plot([], [], "ko--", ms=3, lw=0.6, label="punti di controllo")
    ax.axhline(0, color="k", lw=0.5, ls="-.")
    ax.set_aspect("equal")
    ax.set_xlabel("z [mm]")
    ax.set_ylabel("r [mm]")
    ax.set_title(f"Geometria: L tubo {np.ptp(tube[:, 0]):.1f} mm, D esterno "
                 f"{2 * tube[:, 1].max():.1f} mm, D ingresso {2 * geom.R_inlet * MM:.1f} mm, "
                 f"D uscita {2 * geom.R_exit * MM:.1f} mm")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=9)
    ax.grid(True, ls=":", alpha=0.5)
    return _save(fig, path)


def plot_map(F: Dict, key: str, label: str, title: str, path: str,
             arrows: bool = False, scale: float = 1.0) -> str:
    c, geom = F["cells"], F["geom"]
    # a row on the axis with the values of the first cells, so the two halves meet
    z = np.column_stack((c["z"][:, :1], c["z"])) * MM
    r = np.column_stack((np.zeros(len(c["r"])), c["r"])) * MM
    v = np.column_stack((c[key][:, :1], c[key])) * scale
    aspect = geom.L_total / (2.0 * geom.R_inlet)
    fig, ax = plt.subplots(figsize=(float(np.clip(4.2 * aspect + 3.0, 7.0, 15.0)), 5.5))
    lev = np.linspace(v.min(), v.max(), LEVELS + 1) if np.ptp(v) > 0 else LEVELS
    for s in (1, -1):
        cs = ax.contourf(z, s * r, v, levels=lev, cmap=CMAP)
        ax.contour(z, s * r, v, levels=cs.levels, colors="k", linewidths=0.15, alpha=0.4)
    fig.colorbar(cs, ax=ax, label=label, shrink=0.9)
    zw, rw = geom.profile_points(600)
    ax.plot(zw * MM, rw * MM, "k-", lw=1.2)
    ax.plot(zw * MM, -rw * MM, "k-", lw=1.2)
    zc = 0.5 * (geom.z_a + geom.z_b) * MM
    for zz in (zc - 0.5 * F["case"].L_disk * MM, zc + 0.5 * F["case"].L_disk * MM):
        ax.plot([zz, zz], [-geom.R_disk * MM, geom.R_disk * MM], "g--", lw=1)
    if arrows:
        nz, nr = c["uz"].shape
        i = np.unique(np.linspace(0, nz - 1, 40).astype(int))
        j = np.unique(np.linspace(1, nr - 2, 7).astype(int))
        I, J = np.ix_(i, j)
        sp = np.maximum(c["V"][I, J], 1e-12)
        ax.quiver(c["z"][I, J] * MM, c["r"][I, J] * MM, c["uz"][I, J] / sp, c["ur"][I, J] / sp,
                  angles="xy",
                  color="k", width=0.0015, scale=60, pivot="mid")
    ax.set_aspect("equal")
    ax.set_xlabel("z [mm]")
    ax.set_ylabel("r [mm]")
    ax.set_title(title + " (linee verdi: banda della ventola)")
    return _save(fig, path)


def plot_axial(F: Dict, path: str) -> str:
    s, geom, case = F["sections"], F["geom"], F["case"]
    z = s["z"] * MM
    fig, axs = plt.subplots(4, 1, figsize=(11, 13), sharex=True)
    ax = axs[0]
    ax.plot(z, s["p_mean"], "b-", lw=2, label="media di sezione")
    ax.plot(z, s["p_axis"], "c--", label="asse")
    ax.plot(z, s["p_wall"], "k:", label="parete")
    ax.set_ylabel("pressione statica [Pa]\n(relativa a p_amb)")
    ax = axs[1]
    ax.plot(z, s["p0_mean"], "r-", lw=2, label="media pesata sulla portata")
    ax.axhline(case.dp_disk, color="r", ls=":", lw=1, label=f"Δp disco = {case.dp_disk:.2f} Pa")
    ax.set_ylabel("pressione totale [Pa]\n(relativa a p_amb)")
    ax = axs[2]
    ax.plot(z, s["V_mean"], "b-", lw=2, label="media Q/A")
    ax.plot(z, s["V_axis"], "c--", label="asse")
    ax.axhline(case.V_jet_ideal, color="k", ls=":", lw=1, label="getto ideale")
    ax.set_ylabel("velocità [m/s]")
    ax = axs[3]
    ax.plot(z, s["mach_max"], "m-", lw=2, label="Mach massimo della sezione")
    ax2 = ax.twinx()
    ax2.plot(z, s["R"] * MM, "k-", lw=1, alpha=0.5, label="raggio parete")
    ax2.set_ylabel("R [mm]")
    ax.set_ylabel("Mach [-]")
    ax.set_xlabel("z [mm]")
    for a in axs:
        _disk_band(a, geom, case.L_disk, label="ventola")
        a.grid(True, ls=":", alpha=0.6)
        a.legend(fontsize=9, loc="best")
    axs[0].set_title(f"Profili lungo l'asse: salto di pressione totale sul disco "
                     f"{F['disk']['salto_p0']:.2f} Pa")
    return _save(fig, path)


def plot_wall(F: Dict, path: str) -> str:
    w, geom, case = F["wall"], F["geom"], F["case"]
    z = w["z"] * MM
    fig, axs = plt.subplots(4, 1, figsize=(11, 12), sharex=True)
    panels = [("p", "pressione a parete [Pa]"), ("tau_w", "sforzo a parete τ_w [Pa]"),
              ("cf", "coefficiente d'attrito c_f [-]"), ("y_plus", "y+ prima cella [-]")]
    for a, (k, lab) in zip(axs, panels):
        a.plot(z, w[k], "b-", lw=1.8)
        a.set_ylabel(lab)
        a.grid(True, ls=":", alpha=0.6)
        _disk_band(a, geom, case.L_disk)
    axs[1].axhline(0, color="r", lw=0.8)
    axs[2].axhline(0, color="r", lw=0.8)
    axs[3].axhline(5, color="r", ls="--", lw=0.8, label="limite y+ = 5")
    axs[3].legend(fontsize=9)
    axs[0].set_title("Parete: τ_w < 0 indica flusso invertito (separazione)")
    axs[-1].set_xlabel("z [mm]")
    return _save(fig, path)


def plot_radial(F: Dict, path: str) -> str:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    for name, d in F["radial"].items():
        lab = f"{name} (z = {d['z'] * MM:.1f} mm)"
        a1.plot(d["uz"], d["eta"], lw=1.8, label=lab)
        a2.plot(d["p0"], d["eta"], lw=1.8, label=lab)
    a1.set_xlabel("u_z [m/s]")
    a2.set_xlabel("pressione totale [Pa] (relativa)")
    a1.set_ylabel("r / R [-]")
    for a in (a1, a2):
        a.grid(True, ls=":", alpha=0.6)
    a1.legend(fontsize=8)
    a1.set_title("Velocità assiale attraverso il condotto")
    a2.set_title("Pressione totale attraverso il condotto")
    return _save(fig, path)


def plot_optimisation(histories: Dict[str, List[dict]], path: str) -> str:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    offset = 0
    for name, rows in histories.items():
        if not rows:
            continue
        it = offset + np.array([r["iteration"] for r in rows])
        a1.plot(it, [r["thrust"] for r in rows], "o-", ms=3, label=name)
        a2.plot(it, [r["D_disk"] * MM for r in rows], "s-", ms=3, label=f"{name} D ventola")
        a2.plot(it, [r["D_exit"] * MM for r in rows], "^:", ms=3, label=f"{name} D uscita")
        offset = int(it[-1])
    a1.set_ylabel("spinta [N]")
    a2.set_ylabel("diametro [mm]")
    a2.set_xlabel("iterazione SLSQP (cumulata)")
    for a in (a1, a2):
        a.grid(True, ls=":", alpha=0.6)
        if a.get_legend_handles_labels()[0]:   # nothing to label in grid-scan mode
            a.legend(fontsize=8)
    a1.set_title("Ottimizzazione di forma: ogni tratto è una griglia o un ciclo su Δp")
    return _save(fig, path)


def plot_dp_loop(steps: List[dict], T_target: float, path: str) -> str:
    k = np.arange(1, len(steps) + 1)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    a1.plot(k, [s["dp_disk"] for s in steps], "o-")
    a2.plot(k, [s["spinta"] for s in steps], "s-")
    a2.axhline(T_target, color="r", ls="--", label=f"spinta richiesta {T_target:.4g} N")
    for i, s in enumerate(steps):
        a2.annotate(f"{s['tipo'][:3]} {s['griglia']}", (k[i], s["spinta"]), fontsize=7,
                    rotation=30, xytext=(3, 3), textcoords="offset points")
    a1.set_ylabel("Δp disco [Pa]")
    a2.set_ylabel("spinta per ugello [N]")
    a2.set_xlabel("passo")
    for a in (a1, a2):
        a.grid(True, ls=":", alpha=0.6)
    a2.legend()
    a1.set_title("Ciclo su Δp: ottimizzazione di forma e secante sulla spinta")
    return _save(fig, path)


def plot_grid_study(grid: Optional[dict], path: str) -> Optional[str]:
    if not grid:
        return None
    rows, est = grid["grids"], grid["estimate"]
    h = np.array([r["cells"] ** -0.5 for r in rows])
    h = h / h.min()
    T = np.array([r["thrust"] for r in rows])
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(h, T, "o-", label="spinta sulle griglie")
    for hi, r in zip(h, rows):
        ax.annotate(f"{r['Nz']}x{r['Nr']}", (hi, r["thrust"]), xytext=(4, 4),
                    textcoords="offset points", fontsize=8)
    ax.errorbar([h.min()], [est["value"]], yerr=[est["error"]], fmt="none", ecolor="r",
                capsize=6, label=(f"banda GCI (ordine di riferimento p = 1) ±{est['error_pct']:.2f} %"
                                  if est.get("method") == "reference order"
                                  else f"banda ±{est['error_pct']:.2f} %"))
    ax.plot([0.0], [est["extrapolated"]], "r*", ms=10, label="estrapolata (h → 0)")
    ax.set_xlim(left=-0.05)
    ax.set_xlabel("h / h_fine [-]")
    ax.set_ylabel("spinta [N]")
    ax.set_title("Studio di griglia " + ("(affidabile)" if est.get("reliable") else
                                         "(NON affidabile)"))
    ax.grid(True, ls=":", alpha=0.6)
    ax.legend()
    return _save(fig, path)


def _alt_cases(alt: Dict) -> List[dict]:
    """Converged alternatives, by tube length (the failed ones have no numbers to plot)."""
    rows = [c for c in alt.get("casi") or [] if c.get("convergito") and c.get("dp_Pa") is not None]
    return sorted(rows, key=lambda c: c["L_tubo_mm"])


def _alt_dp(ok: List[dict], ref: str, T: Optional[float], path: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax2 = ax.twinx()
    L = [c["L_tubo_mm"] for c in ok]
    ax.plot(L, [c["dp_Pa"] for c in ok], "o-", color="tab:blue", label="Δp richiesto")
    ax2.plot(L, [c["potenza_W"] for c in ok], "s--", color="tab:orange", label="potenza")
    for c in ok:
        if c["id"] == ref:
            ax.plot(c["L_tubo_mm"], c["dp_Pa"], "r*", ms=16, zorder=5, label="ottimo")
            ax2.plot(c["L_tubo_mm"], c["potenza_W"], "r*", ms=16, zorder=5)
    ax.set_xlabel("L tubo [mm]")
    ax.set_ylabel("Δp richiesto [Pa]")
    ax2.set_ylabel("potenza [W]")
    t_txt = f"{T:.4g} N" if T is not None else "-"
    ax.set_title(f"Alternative a lunghezza fissata, spinta {t_txt} (falliti esclusi)")
    ax.grid(True, ls=":", alpha=0.6)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=9, loc="best")
    return _save(fig, path)


def _alt_losses(ok: List[dict], ref: str, path: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(ok))
    bottom = np.zeros(len(ok))
    series = [("p0 uscita (getto)", "p0_uscita_Pa", "tab:green"),
              ("perdita imbocco", "perdita_imbocco_Pa", "tab:orange"),
              ("perdita disco", "perdita_disco_Pa", "tab:red"),
              ("perdita valle", "perdita_valle_Pa", "tab:purple")]
    for label, key, color in series:
        v = np.array([c[key] for c in ok], dtype=float)
        ax.bar(x, v, bottom=bottom, width=0.6, color=color, label=label)
        bottom = bottom + v
    ax.plot(x, [c["dp_Pa"] for c in ok], "kD--", ms=6, lw=1, label="Δp richiesto")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{c['L_tubo_mm']:.1f}" + (" ★" if c["id"] == ref else "") for c in ok])
    ax.set_xlabel("L tubo [mm]")
    ax.set_ylabel("pressione [Pa]")
    ax.set_title("Δp = p0 uscita + perdite di pressione totale, per lunghezza del tubo")
    ax.grid(True, axis="y", ls=":", alpha=0.6)
    ax.legend(fontsize=9)
    return _save(fig, path)


def _alt_profiles(ok: List[dict], ref: str, path: str) -> Optional[str]:
    ok = [c for c in ok if c.get("profilo_z_mm") and c.get("profilo_R_mm")]
    if not ok:
        return None
    fig, ax = plt.subplots(figsize=(11, 5))
    cmap = plt.get_cmap("viridis")
    for i, c in enumerate(ok):
        z = np.asarray(c["profilo_z_mm"], dtype=float)
        R = np.asarray(c["profilo_R_mm"], dtype=float)
        if c["id"] == ref:
            kw = dict(color="k", lw=3.2, zorder=5)
            lab = f"L {c['L_tubo_mm']:.1f} mm, Δp {c['dp_Pa']:.2f} Pa (ottimo)"
        else:
            kw = dict(color=cmap(i / max(len(ok) - 1, 1)), lw=1.6)
            lab = f"L {c['L_tubo_mm']:.1f} mm, Δp {c['dp_Pa']:.2f} Pa"
        ax.plot(z, R, label=lab, **kw)
        ax.plot(z, -R, **kw)
    ax.axhline(0, color="k", lw=0.5, ls="-.")
    ax.set_xlabel("z [mm]")
    ax.set_ylabel("R [mm]")
    ax.set_title("Profili della parete delle alternative a lunghezza fissata")
    ax.grid(True, ls=":", alpha=0.6)
    ax.legend(fontsize=8, loc="best")
    return _save(fig, path)


def _f(v) -> float:
    """Numero per il grafico: None diventa NaN (il punto non si disegna)."""
    return np.nan if v is None else float(v)


def area_ratio_of(c: Dict) -> Optional[float]:
    """Rapporto d'area A_uscita / A_ventola di una riga (rapporto_aree, o da D_uscita e D_ventola)."""
    if c.get("rapporto_aree") is not None:
        return float(c["rapporto_aree"])
    if c.get("D_uscita_mm") and c.get("D_ventola_mm"):
        return (c["D_uscita_mm"] / c["D_ventola_mm"]) ** 2
    return None


def _alt_panels(ok: List[dict], ref: str, path: str, panels, title: str,
                x: str = "L_tubo_mm", xlabel: str = "L tubo [mm]", hlines=(),
                etichette_L: bool = False) -> Optional[str]:
    """Pannelli con le stesse ascisse. panels = [(ylabel, [(chiave, etichetta, stile)])]: una
    curva per chiave; l'ottimo è una stella rossa sulla sua ascissa (linea verticale)."""
    rows = sorted([c for c in ok if c.get(x) is not None], key=lambda c: c[x])
    if not rows:
        return None
    fig, axs = plt.subplots(len(panels), 1, figsize=(9, 3.4 * len(panels) + 1.2), sharex=True)
    axs = np.atleast_1d(axs)
    xs = [_f(c[x]) for c in rows]
    best = next((c for c in rows if c.get("id") == ref), None)
    for ax, (ylab, series) in zip(axs, panels):
        for key, lab, style in series:
            ax.plot(xs, [_f(c.get(key)) for c in rows], style, label=lab)
            if best is not None and best.get(key) is not None:
                ax.plot(_f(best[x]), _f(best[key]), "r*", ms=14, zorder=5)
        for y, lab, color in hlines:
            ax.axhline(y, color=color, ls="--", lw=1, label=lab)
        if best is not None:
            ax.axvline(_f(best[x]), color="r", ls=":", lw=1)
        ax.set_ylabel(ylab)
        ax.grid(True, ls=":", alpha=0.6)
        ax.legend(fontsize=8, loc="best")
    if etichette_L:
        key = panels[0][1][0][0]
        for c in rows:
            if c.get(key) is not None:
                axs[0].annotate(f"L {c['L_tubo_mm']:.0f}", (_f(c[x]), _f(c[key])), xytext=(4, 4),
                                textcoords="offset points", fontsize=8)
    axs[-1].set_xlabel(xlabel)
    axs[0].set_title(title)
    return _save(fig, path)


def _con_pct(c: Dict) -> Dict:
    """Copia della riga con le perdite di imbocco, disco e valle in % del Δp richiesto."""
    out = dict(c)
    dp = c.get("dp_Pa")
    for k, src in (("imbocco_pct", "perdita_imbocco_Pa"), ("disco_pct", "perdita_disco_Pa"),
                   ("valle_pct", "perdita_valle_Pa")):
        out[k] = 100.0 * c[src] / dp if dp and c.get(src) is not None else None
    return out


def _alt_peso(ok: List[dict], ref: str, path: str) -> Optional[str]:
    return _alt_panels(ok, ref, path,
                       [("Δp richiesto [Pa]", [("dp_Pa", "Δp richiesto", "o-")]),
                        ("potenza [W]", [("potenza_W", "potenza", "s--")])],
                       "Fronte peso/prestazioni: area di parete contro Δp e potenza",
                       x="area_parete_cm2", xlabel="area di parete [cm²]", etichette_L=True)


def _alt_geometria(ok: List[dict], ref: str, path: str) -> Optional[str]:
    return _alt_panels(ok, ref, path,
                       [("diametri [mm]", [("D_ventola_mm", "D ventola", "s-"),
                                           ("D_uscita_mm", "D uscita", "^-"),
                                           ("D_ingresso_mm", "D ingresso", "o-")]),
                        ("posizione ventola [mm]", [("z_ventola_mm", "centro ventola da ingresso", "D-")])],
                       "Geometria contro lunghezza del tubo")


def _alt_perdite_pct(ok: List[dict], ref: str, path: str) -> Optional[str]:
    return _alt_panels([_con_pct(c) for c in ok], ref, path,
                       [("perdite [% di Δp]", [("imbocco_pct", "imbocco", "o-"),
                                               ("disco_pct", "disco", "s-"),
                                               ("valle_pct", "valle", "^-"),
                                               ("perdita_totale_pct", "totale", "k-")])],
                       "Perdite di pressione totale in % del Δp richiesto")


def _alt_separazione(ok: List[dict], ref: str, path: str) -> Optional[str]:
    return _alt_panels(ok, ref, path,
                       [("τ_w minimo nel diffusore [Pa]", [("tau_w_min_diffusore_Pa", "τ_w minimo", "o-")])],
                       "Margine di separazione: τ_w minimo nel diffusore (sotto 0 si separa)",
                       hlines=[(0.0, "separazione (τ_w = 0)", "r")])


def _alt_efficienza(ok: List[dict], ref: str, path: str) -> Optional[str]:
    return _alt_panels(ok, ref, path,
                       [("spinta / potenza [N/W]", [("spinta_su_potenza_N_W", "spinta / potenza", "o-")])],
                       "Efficienza di spinta: spinta per watt contro lunghezza del tubo")


def _sw_zone(ax, xs: List[float]) -> None:
    """Zona convergente (rapporto d'area < 1) in grigio, e limiti dell'asse."""
    lo, hi = min(min(xs), 1.0), max(max(xs), 1.0)
    pad = 0.05 * (hi - lo) if hi > lo else 0.05
    ax.set_xlim(lo - pad, hi + pad)
    ax.axvspan(lo - pad, 1.0, color="0.85", alpha=0.6, zorder=0)


def _sw_mark(ax, x: float, y, color: str, mk: str, c: Dict) -> None:
    """Punto della scansione: vuoto se oltre il limite d'angolo, rosso se separato."""
    if y is None or not np.isfinite(y):
        return
    col = "red" if c.get("separato") else color
    hollow = c.get("entro_limite_angolo") is False
    ax.plot(x, y, marker=mk, ls="none", ms=8, color=col, mfc="white" if hollow else col, zorder=4)


def _sw_legend_items(ax) -> None:
    ax.plot([], [], "o", color="k", mfc="white", label="oltre il limite d'angolo")
    ax.plot([], [], "o", color="red", label="separato")
    ax.plot([], [], "k*", ms=12, label="ottimo")


def _sw_dp(rows: List[dict], ref: str, path: str) -> str:
    xs = [area_ratio_of(c) for c in rows]
    fig, ax = plt.subplots(figsize=(10, 5.8))
    ax2 = ax.twinx()
    ax.plot(xs, [c["dp_Pa"] for c in rows], "-", color="tab:blue", lw=1, alpha=0.6)
    ax2.plot(xs, [_f(c.get("potenza_W")) for c in rows], "-", color="tab:orange", lw=1, alpha=0.6)
    for c, x in zip(rows, xs):
        _sw_mark(ax, x, _f(c["dp_Pa"]), "tab:blue", "o", c)
        _sw_mark(ax2, x, _f(c.get("potenza_W")), "tab:orange", "s", c)
        if c.get("id") == ref:
            ax.plot(x, c["dp_Pa"], "k*", ms=16, zorder=6)
            ax2.plot(x, _f(c.get("potenza_W")), "k*", ms=16, zorder=6)
    _sw_zone(ax, xs)
    ax.set_xlabel("rapporto d'area A_uscita / A_ventola [-]")
    ax.set_ylabel("Δp richiesto [Pa]")
    ax2.set_ylabel("potenza [W]")
    ax.set_title("Scansione dell'uscita: zona grigia = convergente, 1 = dritto")
    ax.grid(True, ls=":", alpha=0.6)
    ax.plot([], [], "o-", color="tab:blue", label="Δp richiesto")
    ax.plot([], [], "s-", color="tab:orange", label="potenza")
    _sw_legend_items(ax)
    h1, l1 = ax.get_legend_handles_labels()
    ax.legend(h1, l1, fontsize=9, loc="best")
    return _save(fig, path)


_SWEEP_LOSS_SERIES = [("p0 uscita (getto)", "p0_uscita_Pa", "tab:green"),
                      ("perdita imbocco", "perdita_imbocco_Pa", "tab:orange"),
                      ("perdita disco", "perdita_disco_Pa", "tab:red"),
                      ("perdita valle", "perdita_valle_Pa", "tab:purple")]


def _sw_perdite(rows: List[dict], ref: str, path: str) -> str:
    x = np.array([area_ratio_of(c) for c in rows], dtype=float)
    d = np.diff(np.sort(x))
    w = 0.6 * d[d > 0].min() if np.any(d > 0) else 0.05
    fig, ax = plt.subplots(figsize=(10, 5.8))
    bottom = np.zeros(len(rows))
    for label, key, color in _SWEEP_LOSS_SERIES:
        v = np.nan_to_num(np.array([_f(c.get(key)) for c in rows]))
        ax.bar(x, v, bottom=bottom, width=w, color=color, label=label)
        bottom = bottom + v
    ax.plot(x, [c["dp_Pa"] for c in rows], "kD--", ms=6, lw=1, label="Δp richiesto")
    for c, xi in zip(rows, x):
        if c.get("id") == ref:
            ax.annotate("ottimo", (xi, c["dp_Pa"]), xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=9)
    ax.set_xlabel("rapporto d'area A_uscita / A_ventola [-]")
    ax.set_ylabel("pressione [Pa]")
    ax.set_title("Δp = p0 uscita + perdite di pressione totale, per apertura del diffusore")
    ax.grid(True, axis="y", ls=":", alpha=0.6)
    ax.legend(fontsize=9)
    return _save(fig, path)


def _sw_limiti(sw: Dict, rows: List[dict], path: str) -> str:
    xs = [area_ratio_of(c) for c in rows]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    a1.plot(xs, [_f(c.get("tau_w_min_diffusore_Pa")) for c in rows], "o-", color="tab:blue",
            label="τ_w minimo nel diffusore")
    for c, x in zip(rows, xs):
        _sw_mark(a1, x, _f(c.get("tau_w_min_diffusore_Pa")), "tab:blue", "o", c)
    a1.axhline(0.0, color="r", lw=1, label="separazione (τ_w = 0)")
    a1.set_ylabel("τ_w minimo [Pa]")
    a1.set_title("Limiti della scansione: separazione e semiangolo")
    div = [c for c in rows if c.get("tipo") != "convergente" and c.get("semiangolo_diffusore_deg") is not None]
    conv = [c for c in rows if c.get("tipo") == "convergente" and c.get("semiangolo_convergente_deg") is not None]
    a2.plot([area_ratio_of(c) for c in div], [c["semiangolo_diffusore_deg"] for c in div], "^-",
            color="tab:red", label="semiangolo divergente")
    a2.plot([area_ratio_of(c) for c in conv], [abs(c["semiangolo_convergente_deg"]) for c in conv],
            "v-", color="tab:green", label="semiangolo convergente (modulo)")
    lim_d, lim_c = sw.get("limite_semiangolo_deg"), sw.get("limite_convergente_deg")
    if lim_d is not None:
        a2.axhline(lim_d, color="tab:red", ls="--", lw=1, label=f"limite divergente {lim_d:g}°")
    if lim_c is not None:
        a2.axhline(abs(lim_c), color="tab:green", ls="--", lw=1, label=f"limite convergente {abs(lim_c):g}°")
    a2.set_ylabel("semiangolo [°]")
    a2.set_xlabel("rapporto d'area A_uscita / A_ventola [-]")
    for a in (a1, a2):
        a.axvline(1.0, color="0.4", ls=":", lw=1)
        _sw_zone(a, xs)
        a.grid(True, ls=":", alpha=0.6)
        a.legend(fontsize=8, loc="best")
    return _save(fig, path)


def _sw_profili(rows: List[dict], ref: str, path: str) -> Optional[str]:
    rows = [c for c in rows if c.get("profilo_z_mm") and c.get("profilo_R_mm")]
    if not rows:
        return None
    smin, smax = min(c["s"] for c in rows), max(c["s"] for c in rows)
    cmap = plt.get_cmap("RdBu")
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in rows:
        z = np.asarray(c["profilo_z_mm"], dtype=float)
        R = np.asarray(c["profilo_R_mm"], dtype=float)
        t = (c["s"] - smin) / (smax - smin) if smax > smin else 0.5
        if c.get("id") == ref:
            kw = dict(color="k", lw=3.2, zorder=5)
            lab = f"s = {c['s']:.2f} (ottimo), D uscita {c['D_uscita_mm']:.1f} mm"
        else:
            kw = dict(color=cmap(t), lw=1.6, ls="--" if c.get("separato") else "-")
            lab = f"s = {c['s']:.2f}, D uscita {c['D_uscita_mm']:.1f} mm" + (" (separato)" if c.get("separato") else "")
        ax.plot(z, R, label=lab, **kw)
        ax.plot(z, -R, **kw)
    ax.axhline(0, color="k", lw=0.5, ls="-.")
    ax.set_xlabel("z [mm]")
    ax.set_ylabel("R [mm]")
    ax.set_title("Profili della parete con l'uscita scalata: blu divergente, rosso convergente, nero ottimo")
    ax.grid(True, ls=":", alpha=0.6)
    ax.legend(fontsize=8, loc="best")
    return _save(fig, path)


def plot_exit_sweep(sweep: Optional[Dict], out_dir: str) -> List[str]:
    """uscita_dp, uscita_perdite, uscita_limiti e uscita_profili (.svg), contro il rapporto d'area."""
    if not sweep or not sweep.get("punti"):
        return []
    rows = sorted([c for c in sweep["punti"]
                   if c.get("dp_Pa") is not None and area_ratio_of(c) is not None], key=lambda c: c["s"])
    if not rows:
        return []
    os.makedirs(out_dir, exist_ok=True)
    j = lambda n: os.path.join(out_dir, n)
    ref = sweep.get("riferimento", "ottimo")
    files = [_sw_dp(rows, ref, j("uscita_dp.svg")),
             _sw_perdite(rows, ref, j("uscita_perdite.svg")),
             _sw_limiti(sweep, rows, j("uscita_limiti.svg")),
             _sw_profili(rows, ref, j("uscita_profili.svg"))]
    return [f for f in files if f]


PHASE_COLOR = {"scansione": "tab:gray", "ottimizzazione": "tab:blue", "secante": "tab:green"}


def _phase_points(ax, n: np.ndarray, y: np.ndarray, fase: List[str]) -> None:
    for f in dict.fromkeys(fase):
        m = np.array([v == f for v in fase]) & np.isfinite(y)
        ax.plot(n[m], y[m], "o", ms=5, color=PHASE_COLOR.get(f, "k"))


def plot_history(history: Optional[Dict], out_dir: str) -> List[str]:
    """storico_ottimizzazione.svg: forma, lunghezza, spinta e Δp contro il passo, per fase."""
    passi = (history or {}).get("passi") or []
    if not passi:
        return []
    os.makedirs(out_dir, exist_ok=True)
    n = np.array([p.get("n") if p.get("n") is not None else i + 1 for i, p in enumerate(passi)],
                 dtype=float)
    fase = [p.get("fase") or "" for p in passi]
    ratio = [(p["D_uscita_mm"] / p["D_ventola_mm"]) if p.get("D_uscita_mm") and p.get("D_ventola_mm")
             else None for p in passi]
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 10.5), sharex=True)
    for ax, y, lab in ((a1, ratio, "D uscita / D ventola [-]"),
                       (a2, [p.get("L_condotto_mm") for p in passi], "L condotto [mm]")):
        y = np.array([_f(v) for v in y])
        ax.plot(n, y, "-", color="0.6", lw=1)
        _phase_points(ax, n, y, fase)
        ax.set_ylabel(lab)
    spinta = np.array([_f(p.get("spinta_N")) for p in passi])
    dp = np.array([_f(p.get("dp_Pa")) for p in passi])
    _phase_points(a3, n, spinta, fase)
    a3.plot(n, spinta, "-", color="0.6", lw=1)
    a3.set_ylabel("spinta [N]")
    a3b = a3.twinx()
    a3b.plot(n, dp, "s--", color="tab:orange", ms=4, label="Δp")
    a3b.set_ylabel("Δp [Pa]")
    for i in range(1, len(fase)):
        if fase[i] != fase[i - 1]:
            for ax in (a1, a2, a3):
                ax.axvline(n[i] - 0.5, color="0.4", ls=":", lw=1)
    for i in range(len(fase)):
        if i == 0 or fase[i] != fase[i - 1]:
            a1.annotate(fase[i], xy=(n[i], 1.0), xycoords=("data", "axes fraction"), xytext=(3, -4),
                        textcoords="offset points", fontsize=8, va="top",
                        color=PHASE_COLOR.get(fase[i], "k"))
    sc = (history.get("scelta") or {}).get("n")
    for ax in (a1, a2, a3):
        if sc is not None:
            ax.axvline(sc, color="r", ls="--", lw=1, label="scelta finale" if ax is a1 else None)
    for f in dict.fromkeys(fase):
        a1.plot([], [], "o", color=PHASE_COLOR.get(f, "k"), label=f)
    a1.legend(fontsize=8, loc="upper right")
    a1.set_title("Storico dell'ottimizzazione: scansione → ottimizzazione → secante")
    a3.set_xlabel("passo n")
    for ax in (a1, a2, a3):
        ax.grid(True, ls=":", alpha=0.6)
    return [_save(fig, os.path.join(out_dir, "storico_ottimizzazione.svg"))]


def plot_alternatives(alt: Optional[Dict], out_dir: str) -> List[str]:
    """alternative_dp, alternative_perdite, alternative_profili, alternative_peso,
    alternative_geometria, alternative_perdite_pct, alternative_separazione e
    alternative_efficienza (.svg) in out_dir."""
    if not alt or not alt.get("casi"):
        return []
    ok = _alt_cases(alt)
    if not ok:
        return []
    os.makedirs(out_dir, exist_ok=True)
    j = lambda n: os.path.join(out_dir, n)
    ref = alt.get("riferimento", "ottimo")
    files = [_alt_dp(ok, ref, alt.get("T_target_N"), j("alternative_dp.svg")),
             _alt_losses(ok, ref, j("alternative_perdite.svg")),
             _alt_profiles(ok, ref, j("alternative_profili.svg")),
             _alt_peso(ok, ref, j("alternative_peso.svg")),
             _alt_geometria(ok, ref, j("alternative_geometria.svg")),
             _alt_perdite_pct(ok, ref, j("alternative_perdite_pct.svg")),
             _alt_separazione(ok, ref, j("alternative_separazione.svg")),
             _alt_efficienza(ok, ref, j("alternative_efficienza.svg"))]
    return [f for f in files if f]


def export_duct_plots(F: Dict, tube: np.ndarray, design: np.ndarray, layout,
                      histories: Dict[str, List[dict]], steps: List[dict],
                      grid: Optional[dict], out: str) -> List[str]:
    os.makedirs(out, exist_ok=True)
    j = lambda n: os.path.join(out, n)
    files = [
        plot_geometry(F, tube, design, layout, j("geometria.svg")),
        plot_map(F, "V", "|V| [m/s]", "Modulo della velocità, frecce: direzione",
                 j("campo_velocita.svg"), arrows=True),
        plot_map(F, "uz", "u_z [m/s]", "Velocità assiale", j("campo_velocita_assiale.svg")),
        plot_map(F, "ur", "u_r [m/s]", "Velocità radiale", j("campo_velocita_radiale.svg")),
        plot_map(F, "p", "p - p_amb [Pa]", "Pressione statica", j("campo_pressione_statica.svg")),
        plot_map(F, "p0", "p0 - p_amb [Pa]", "Pressione totale (di ristagno)",
                 j("campo_pressione_totale.svg")),
        plot_map(F, "mach", "Mach [-]", "Numero di Mach", j("campo_mach.svg")),
        plot_map(F, "nu_ratio", "ν_t / ν [-]", "Viscosità turbolenta (Baldwin-Lomax)",
                 j("campo_viscosita_turbolenta.svg")),
        plot_axial(F, j("profili_assiali.svg")),
        plot_wall(F, j("parete.svg")),
        plot_radial(F, j("profili_radiali.svg")),
        plot_optimisation(histories, j("ottimizzazione.svg")),
        plot_dp_loop(steps, F["case"].T_target, j("iterazioni_dp.svg")),
        plot_grid_study(grid, j("studio_griglia.svg")),
    ]
    return [f for f in files if f]
