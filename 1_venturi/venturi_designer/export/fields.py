"""
fields.py
=========
Everything the flow solution of a duct tells, in physical units, ready for
plots and tables:

    cells     uz, ur, |V|, static and total pressure (gauge), Mach, nu_t/nu
    sections  area-weighted static pressure, mass-weighted total pressure,
              mean speed Q/A, axis and wall values, largest Mach
    wall      pressure, wall shear stress, friction coefficient, y+
    radial    profiles across the duct at five stations

Gauge pressures are relative to p_amb. The total pressure of a section is
weighted by the mass flow through each cell, the one that enters the
energy balance of the fan.
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np

from ..solver.turbulence import wall_y_plus

RADIAL_STATIONS = {"ingresso": 0.02, "metà imbocco": None, "disco": None,
                   "metà diffusore": None, "uscita": 0.98}


def duct_fields(problem, design) -> Dict[str, Dict[str, np.ndarray]]:
    sol = problem.solve(design)
    s, case = sol.system, problem.case
    m = s.mesh
    geom = problem.geometry(design)
    rho, mu = case.rho, case.mu
    _, _, p_k, Q = s.unpack(sol.x)
    uz, ur = (a.copy() for a in s.velocities(sol.x))
    p = p_k * rho
    V = np.hypot(uz, ur)
    p0 = p + 0.5 * rho * V ** 2
    mach = V / case.speed_of_sound if math.isfinite(case.speed_of_sound) else np.zeros_like(V)
    cells = dict(z=m.z_cc, r=m.r_c, uz=uz, ur=ur, V=V, p=p, p0=p0, mach=mach,
                 nu_ratio=sol.nu_t / case.nu, vol=m.vol)

    w = m.vol
    flux = np.maximum(uz, 0.0) * w
    A = math.pi * m.R_c ** 2
    sections = dict(
        z=m.z_c, R=m.R_c, A=A, V_mean=Q / A,
        p_mean=(p * w).sum(1) / w.sum(1),
        p0_mean=(p0 * flux).sum(1) / np.maximum(flux.sum(1), 1e-300),
        p_axis=p[:, 0], p_wall=p[:, -1], V_axis=uz[:, 0], mach_max=mach.max(1),
        nu_ratio_max=cells["nu_ratio"].max(1))

    # wall cell: speed along the wall, its shear and friction coefficient
    tz, tr = m.nr_rad[:, -1], -m.nz_rad[:, -1]
    us = uz[:, -1] * tz + ur[:, -1] * tr
    tau = mu * us / m.wall_distance[:, -1]
    q = 0.5 * rho * sections["V_mean"] ** 2
    wall = dict(z=m.z_c, R=m.R_c, p=p[:, -1], tau_w=tau, cf=tau / q,
                y_plus=wall_y_plus(uz, ur, m, case.nu), u_wall=us)

    zc = 0.5 * (geom.z_a + geom.z_b)
    where = dict(RADIAL_STATIONS)
    where["metà imbocco"] = 0.5 * geom.z_a / geom.L_total
    where["disco"] = zc / geom.L_total
    where["metà diffusore"] = (geom.z_b + 0.5 * geom.L_down) / geom.L_total
    radial = {}
    for name, frac in where.items():
        i = int(np.argmin(np.abs(m.z_c - frac * geom.L_total)))
        radial[name] = dict(z=float(m.z_c[i]), eta=m.r_c[i] / m.R_c[i], r=m.r_c[i],
                            uz=uz[i], ur=ur[i], p=p[i], p0=p0[i], nu_ratio=cells["nu_ratio"][i])

    # total-pressure rise across the disk band
    band = (m.z_c > zc - case.L_disk) & (m.z_c < zc + case.L_disk)
    i_in, i_out = int(np.argmax(band)), int(len(band) - np.argmax(band[::-1]) - 1)
    disk = dict(p0_monte=float(sections["p0_mean"][max(i_in - 1, 0)]),
                p0_valle=float(sections["p0_mean"][min(i_out + 1, m.Nz - 1)]))
    disk["salto_p0"] = disk["p0_valle"] - disk["p0_monte"]
    return dict(cells=cells, sections=sections, wall=wall, radial=radial, disk=disk,
                geom=geom, case=case, Q=Q)
