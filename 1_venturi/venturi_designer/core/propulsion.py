"""
propulsion.py
=============
The duct as a propulsor: inputs of the case, actuator disk and thrust.

A duct alone produces no thrust. With no energy added the total pressure
cannot rise, so at ambient exit pressure Ve <= V0 and T = mdot*(Ve - V0) <= 0.
The energy comes from an actuator disk, a total-pressure rise dp_disk spread
uniformly over a band of cells of the straight disk section. The disk stands
in for the fan: dp_disk is an input that the fan sizing will provide.

Boundary conditions, all of them gauge pressures relative to ambient:

    inlet    total pressure p0 = rho*V0^2/2  (flight dynamic pressure)
    disk     axial force per unit mass  dp_disk / (rho * band length)
    exit     static pressure 0

The flow rate is not imposed: it is what makes these three agree.

Thrust, from a control volume going from far upstream to the exit plane:

    T = integral(rho * uz^2 dA) - rho * Q * V0

This is the net internal thrust. The external flow over the nacelle is not
solved, so its drag is not included.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .config import GAMMA_AIR, R_AIR
from .fluids import FLUIDS
from ..solver.fvmesh import FVMesh


@dataclass
class PropulsionCase:
    """Operating point and limits of the duct (see input.py)."""
    fluid: str
    V0: float                    # flight speed [m/s]
    p_amb: float                 # ambient pressure [Pa]
    dp_disk: float               # total-pressure rise of the disk [Pa]
    D_disk: float                # disk diameter [m]
    L_disk: float                # axial length of the disk band [m]
    D_max: float                 # largest diameter allowed [m]
    L_max: float                 # largest total length allowed [m]
    P_max: Optional[float] = None    # largest power allowed [W], None = free
    z_disk: Optional[float] = None   # disk centre / total length, None = free
    turbulence_model: str = "baldwin_lomax"
    Nz: int = 64
    Nr: int = 26
    wall_clustering: float = 2.7
    throat_refine: float = 3.0

    rho: float = field(init=False)
    mu: float = field(init=False)
    p_vap: float = field(init=False)
    is_gas: bool = field(init=False)
    speed_of_sound: float = field(init=False)

    def __post_init__(self) -> None:
        if self.fluid not in FLUIDS:
            raise ValueError(f"Unknown fluid '{self.fluid}'. Known: {', '.join(FLUIDS)}.")
        for name in ("dp_disk", "D_disk", "L_disk", "D_max", "L_max", "p_amb"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive, got {getattr(self, name)}.")
        if self.V0 < 0.0:
            raise ValueError(f"V0 cannot be negative, got {self.V0}.")
        if self.z_disk is not None and not 0.0 < self.z_disk < 1.0:
            raise ValueError(f"z_disk must be between 0 and 1, got {self.z_disk}.")
        if self.D_disk >= self.D_max:
            raise ValueError(f"D_disk ({self.D_disk}) must be below D_max ({self.D_max}).")
        f = FLUIDS[self.fluid]
        self.rho = f.density_at(self.p_amb)
        self.mu = f.mu
        self.p_vap = f.p_vap
        self.is_gas = f.is_gas
        self.speed_of_sound = (math.sqrt(GAMMA_AIR * R_AIR * (f.temp_C + 273.15))
                               if f.is_gas else float("inf"))

    @property
    def nu(self) -> float:
        return self.mu / self.rho

    @property
    def V_jet_ideal(self) -> float:
        """Exit speed with no losses [m/s]."""
        return math.sqrt(2.0 * self.dp_disk / self.rho + self.V0 ** 2)


def disk_force(mesh: FVMesh, z_a: float, z_b: float, dp: float, rho: float) -> np.ndarray:
    """(Nz, Nr) axial acceleration of the disk band, centred in z_a..z_b.

    The cells in the band are found by position. The force is then scaled so
    that its integral along z is exactly dp/rho, however the cell faces fall
    with respect to the band. That keeps the total-pressure rise independent
    of the grid, and smooth when the grid moves.
    """
    dz = np.diff(mesh.z_f)
    overlap = np.clip(np.minimum(mesh.z_f[1:], z_b) - np.maximum(mesh.z_f[:-1], z_a), 0.0, None)
    if overlap.sum() <= 0.0:
        raise ValueError("The actuator disk band contains no cell.")
    g = dp / rho * (overlap / dz) / overlap.sum()
    return np.repeat(g[:, None], mesh.Nr, axis=1)


def thrust_from_fluxes(F_out: np.ndarray, A_out: np.ndarray, Q: float, V0: float,
                       rho: float) -> float:
    """Net thrust [N] from the exit fluxes."""
    return float(rho * np.sum(F_out ** 2 / A_out) - rho * Q * V0)
