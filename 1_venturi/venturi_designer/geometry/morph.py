"""
morph.py
========
Wall profile R(z) of the duct as two cubic B-splines joined by a straight
section that holds the actuator disk:

    intake spline  ->  straight disk section  ->  diffuser/nozzle spline

The shape is morphed by moving spline control points and by changing the two
spline lengths. The grid follows on its own: the mesh coordinate is
eta = r / R(z), so a new R(z) only needs build_fvmesh to be called again, with
the same topology and no mesh-deformation algorithm.

Fixed by construction:
    - the disk radius, with R' = R'' = 0 where each spline meets the section,
      because the last three control points of the spline equal R_disk;
    - R' = 0 at inlet and exit (first two control points equal), so the jet
      leaves parallel to the axis and the exit plane can sit at ambient
      pressure.

Design vector x, in metres:
    x[:n_up]            radii of the free intake control points, inlet first
    x[n_up:n_up+n_down] radii of the free diffuser control points, exit last
    x[-2], x[-1]        L_up and L_down, the two spline lengths
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from scipy.interpolate import BSpline

from .venturi import Segment

N_FIXED_DISK = 3     # control points held at R_disk on the disk side
N_WALL_SAMPLES = 400 # straight pieces of the wall handed to the CAD export


def _clamped_knots(n_ctrl: int, degree: int = 3) -> np.ndarray:
    inner = np.linspace(0.0, 1.0, n_ctrl - degree + 1)
    return np.concatenate((np.zeros(degree), inner, np.ones(degree)))


@dataclass(frozen=True)
class MorphLayout:
    """What stays the same for the whole optimisation."""
    R_disk: float        # disk radius [m]
    L_section: float     # length of the straight disk section [m]
    n_up: int = 5        # free control points of the intake
    n_down: int = 8      # free control points of the diffuser

    def __post_init__(self):
        if self.n_up < 1 or self.n_down < 1:
            raise ValueError("Each spline needs at least one free control point.")

    @property
    def n_vars(self) -> int:
        return self.n_up + self.n_down + 2

    def split(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, float]:
        x = np.asarray(x, dtype=float)
        if x.size != self.n_vars:
            raise ValueError(f"Expected {self.n_vars} design variables, got {x.size}.")
        return (x[:self.n_up], x[self.n_up:self.n_up + self.n_down],
                float(x[-2]), float(x[-1]))

    def control_points(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Whole control polygons, each ordered along +z."""
        up, down, _, _ = self.split(x)
        disk = np.full(N_FIXED_DISK, self.R_disk)
        c_up = np.concatenate(([up[0]], up, disk))
        c_down = np.concatenate((disk, down, [down[-1]]))
        return c_up, c_down


class MorphedGeometry:
    """Same interface as VenturiGeometry, so grid and export need no change.

    Attributes:
        z_stations: [0, 0, z_a, z_b, L, L], z_a..z_b being the disk section
        R_inlet, R_exit, R_throat: inlet, exit and disk radius [m]
    """

    def __init__(self, layout: MorphLayout, x: np.ndarray, config=None):
        self.layout = layout
        self.config = config
        self.x = np.array(x, dtype=float)
        c_up, c_down = layout.control_points(self.x)
        _, _, self.L_up, self.L_down = layout.split(self.x)
        if self.L_up <= 0.0 or self.L_down <= 0.0:
            raise ValueError("The spline lengths must be positive.")
        self._up = BSpline(_clamped_knots(c_up.size), c_up, 3)
        self._down = BSpline(_clamped_knots(c_down.size), c_down, 3)
        self._dup = self._up.derivative()
        self._ddown = self._down.derivative()

        self.z_a = self.L_up
        self.z_b = self.z_a + layout.L_section
        self.L_total = self.z_b + self.L_down
        self.z_stations = np.array([0.0, 0.0, self.z_a, self.z_b,
                                    self.L_total, self.L_total])
        self.R_inlet = float(c_up[0])
        self.R_exit = float(c_down[-1])
        self.R_throat = float(layout.R_disk)

    def radius(self, z):
        """Wall radius R(z) [m]. Accepts a number or an array."""
        z = np.asarray(z, dtype=float)
        r = np.full_like(z, self.R_throat)
        lo, hi = z < self.z_a, z > self.z_b
        r = np.where(lo, self._up(np.clip(z / self.L_up, 0.0, 1.0)), r)
        r = np.where(hi, self._down(np.clip((z - self.z_b) / self.L_down, 0.0, 1.0)), r)
        return float(r) if r.ndim == 0 else r

    def radius_derivative(self, z):
        """Slope of the wall dR/dz [-]. Accepts a number or an array."""
        z = np.asarray(z, dtype=float)
        dr = np.zeros_like(z)
        lo, hi = z < self.z_a, z > self.z_b
        dr = np.where(lo, self._dup(np.clip(z / self.L_up, 0.0, 1.0)) / self.L_up, dr)
        dr = np.where(hi, self._ddown(np.clip((z - self.z_b) / self.L_down, 0.0, 1.0))
                      / self.L_down, dr)
        return float(dr) if dr.ndim == 0 else dr

    def profile_points(self, n_points: int = 500) -> Tuple[np.ndarray, np.ndarray]:
        """n_points evenly spaced (z, R(z)) pairs from inlet to outlet."""
        z = np.linspace(0.0, self.L_total, n_points)
        return z, self.radius(z)

    def wall_segments(self) -> List[Segment]:
        """The wall as many short straight pieces [m]."""
        z, r = self.profile_points(N_WALL_SAMPLES + 1)
        pts = [(float(a), float(b)) for a, b in zip(z, r)]
        return [Segment(a, b) for a, b in zip(pts, pts[1:])]


def fit_design(layout: MorphLayout, z, R, z_a: float, z_b: float) -> np.ndarray:
    """Design vector closest, in least squares, to a given profile R(z).

    z_a..z_b is the part of the given profile replaced by the disk section.
    """
    z, R = np.asarray(z, dtype=float), np.asarray(R, dtype=float)
    L_up, L_down = z_a, float(z[-1]) - z_b

    def fit(n_free: int, s: np.ndarray, target: np.ndarray, disk_last: bool) -> np.ndarray:
        n_ctrl = n_free + 1 + N_FIXED_DISK
        t = _clamped_knots(n_ctrl)
        A = BSpline.design_matrix(np.clip(s, 0.0, 1.0), t, 3).toarray()
        if disk_last:      # c = (c0, c0, c1 .. , disk x 3)
            free = np.column_stack([A[:, 0] + A[:, 1]]
                                   + [A[:, k] for k in range(2, 1 + n_free)])
            rhs = target - layout.R_disk * A[:, -N_FIXED_DISK:].sum(axis=1)
        else:              # c = (disk x 3, c0 .. , cN, cN)
            first = N_FIXED_DISK
            free = np.column_stack([A[:, first + k] for k in range(n_free - 1)]
                                   + [A[:, -2] + A[:, -1]])
            rhs = target - layout.R_disk * A[:, :N_FIXED_DISK].sum(axis=1)
        return np.linalg.lstsq(free, rhs, rcond=None)[0]

    m_up, m_down = z <= z_a, z >= z_b
    up = fit(layout.n_up, z[m_up] / L_up, R[m_up], True)
    down = fit(layout.n_down, (z[m_down] - z_b) / L_down, R[m_down], False)
    return np.concatenate((up, down, [L_up, L_down]))
