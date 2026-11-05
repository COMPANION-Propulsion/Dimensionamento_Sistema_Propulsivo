"""
fan_coupled.py
==============
The final duct solved again with the real fan instead of the uniform disk.

The fan sizing gives, ring by ring, the axial total-pressure rise dp(r) (swirl
removed by the stator, or lost without it) and a hub where nothing is added.
That profile replaces the uniform dp of the actuator disk; the duct shape is the
one of design.json, the grid one level of the grid study. Out of it come the
fields with the fan (pressure, speed, total pressure, Mach, nu_t), the thrust
the real fan gives, and the wall friction, to see where the flow may separate.

Limits: axisymmetric; the swirl and the hub body are not in the flow (the blade
annulus is spread over the disk at equal area, see radial_profile); the profile
comes from the BEMT, not from a coupled solve.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Sequence

import numpy as np

from ..export.fields import duct_fields
from ..export.paraview import export_paraview_2d, export_paraview_3d
from ..export.plots_duct import plot_axial, plot_map, plot_wall
from ..optimization.shape_opt import DuctProblem, for_grid, report
from ..optimization.target_thrust import load_design

GRID = (90, 36)        # one level of the grid study: fast, enough for the comparison


def radial_profile(r_over_R: Sequence[float], dp: Sequence[float], dp_ref: float,
                   hub_over_R: float):
    """eta (of the duct disk) -> dp / dp_ref of the fan ring with the same area fraction.

    The hub is a solid body: all the air crosses the blade annulus. The duct here
    has no hub, so the annulus is spread over the whole disk at equal area,
    r_fan^2 = r_hub^2 + eta^2 (R^2 - r_hub^2): every stream tube gets the dp of
    the ring it really crosses, and no core of air passes the fan without energy.
    """
    x = np.asarray(r_over_R, float)
    y = np.asarray(dp, float) / dp_ref
    h2 = hub_over_R ** 2

    def profile(eta: np.ndarray) -> np.ndarray:
        r_fan = np.sqrt(h2 + np.asarray(eta) ** 2 * (1.0 - h2))
        return np.interp(r_fan, x, y)
    return profile


def solve_with_fan(design_file: str, r_over_R: Sequence[float], dp_axial: Sequence[float],
                   hub_over_R: float, cfd_dir: str, graph_dir: str, grid=GRID) -> Dict:
    """Solve, write the files and return the comparison with the uniform disk."""
    case, layout, design = load_design(design_file)
    case = for_grid(case, *grid)
    uniform = DuctProblem(case, layout)
    T_uniform = report(uniform, design)["thrust"]
    # area-weighted mean of the fan profile over the whole disk = the mean dp it gives
    eta = np.linspace(0.0, 1.0, 2001)
    prof = radial_profile(r_over_R, dp_axial, case.dp_disk, hub_over_R)
    mean = float(np.trapezoid(prof(eta) * 2 * eta, eta))
    fan = DuctProblem(case, layout, disk_profile=prof)
    fan.warm_start(uniform.sol)
    summary = report(fan, design)
    F = duct_fields(fan, design)
    os.makedirs(cfd_dir, exist_ok=True)
    os.makedirs(graph_dir, exist_ok=True)
    c = F["cells"]
    extra = {"Total_Pressure": c["p0"], "Mach": c["mach"],
             "Turbulent_Viscosity_Ratio": c["nu_ratio"]}
    mesh = fan.solve(design).system.mesh
    files = [export_paraview_2d(mesh, c["uz"], c["ur"], c["p"] + case.p_amb, cfd_dir, extra,
                                name="condotto_con_ventola_2d.vts"),
             export_paraview_3d(mesh, c["uz"], c["ur"], c["p"] + case.p_amb, cfd_dir, n_theta=48,
                                extra=extra, name="condotto_con_ventola_3d.vts")]
    j = lambda n: os.path.join(graph_dir, n)
    files += [
        plot_map(F, "p0", "p0 - p_amb [Pa]", "Con la ventola vera: pressione totale",
                 j("condotto_con_ventola_pressione_totale.svg")),
        plot_map(F, "p", "p - p_amb [Pa]", "Con la ventola vera: pressione statica",
                 j("condotto_con_ventola_pressione_statica.svg")),
        plot_map(F, "V", "|V| [m/s]", "Con la ventola vera: velocità",
                 j("condotto_con_ventola_velocita.svg"), arrows=True),
        plot_axial(F, j("condotto_con_ventola_profili_assiali.svg")),
        plot_wall(F, j("condotto_con_ventola_parete.svg")),
    ]
    wall = F["wall"]
    result = dict(
        griglia=f"{grid[0]}x{grid[1]}", dp_disco_uniforme_Pa=case.dp_disk,
        dp_medio_ventola_Pa=mean * case.dp_disk,
        spinta_disco_uniforme_N=T_uniform, spinta_con_ventola_N=summary["thrust"],
        scarto_spinta_pct=100.0 * (summary["thrust"] / T_uniform - 1.0),
        portata_m3_s=summary["Q"], celle_flusso_invertito=summary["reversed_cells"],
        margine_separazione=summary["separation_margin"],
        tau_parete_min_Pa=float(np.min(wall["tau_w"])),
        z_tau_min_mm=float(1e3 * wall["z"][int(np.argmin(wall["tau_w"]))]),
        mach_max=summary["mach_max"], files=[os.path.basename(f) for f in files if f],
        nota=("Stesso condotto, dp della ventola anello per anello invece del disco "
              "uniforme; l'anello delle pale e ridistribuito sul disco a pari area (il mozzo "
              "blocca il centro). tau_parete < 0 = flusso invertito a parete (separazione). "
              "Swirl e corpo del mozzo non simulati."))
    with open(os.path.join(cfd_dir, "condotto_con_ventola.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
    return result
