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
    z, r, v = c["z"] * MM, c["r"] * MM, c[key] * scale
    fig, ax = plt.subplots(figsize=(13, 5))
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
        ax.quiver(z[I, J], r[I, J], c["uz"][I, J] / sp, c["ur"][I, J] / sp, angles="xy",
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
                capsize=6, label=f"banda GCI ±{est['error_pct']:.2f} %")
    ax.plot([0.0], [est["extrapolated"]], "r*", ms=10, label="estrapolata (h → 0)")
    ax.set_xlim(left=-0.05)
    ax.set_xlabel("h / h_fine [-]")
    ax.set_ylabel("spinta [N]")
    ax.set_title("Studio di griglia " + ("(affidabile)" if est.get("reliable") else
                                         "(NON affidabile)"))
    ax.grid(True, ls=":", alpha=0.6)
    ax.legend()
    return _save(fig, path)


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
