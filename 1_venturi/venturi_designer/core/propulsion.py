"""
propulsion.py
=============
The duct as a propulsor: inputs of the case, actuator disk and thrust.

A duct alone produces no thrust. With no energy added the total pressure
cannot rise, so at ambient exit pressure Ve <= V0 and T = mdot*(Ve - V0) <= 0.
The energy comes from an actuator disk, a total-pressure rise dp_disk spread
uniformly over a band of cells of the straight disk section. The disk stands
in for the fan. The thrust per nozzle is the input; dp_disk is what the dp
loop (optimization/target_thrust.py) finds, and it goes to the fan sizing.

Size limits: the tube must fit in an outer diameter D_ext_max and a length
L_max. The inner duct, fan included, stays gap_parete inside the outer edge:

    R_int_max = D_ext_max / 2 - gap_parete

Boundary conditions, all of them gauge pressures relative to ambient:

    inlet    total pressure p0 = rho*V0^2/2  (flight dynamic pressure)
    disk     axial force per unit mass  dp_disk / (rho * band length)
    exit     static pressure 0

The flow rate is not imposed: it is what makes these three agree.

Thrust, from a control volume going from far upstream to the exit plane:

    T = integral(rho * uz^2 + p - p_amb) dA - rho * Q * V0

The exit boundary condition fixes p = p_amb on the exit face, so the pressure
term is zero there by construction; it is written out (p_out) so that the
formula is the complete one. The independent check is the sum of the axial
forces on walls and disk (momentum_balance in adjoint.py); the two must agree
within 1 %.

This is the net internal thrust. The external flow over the nacelle is not
solved, so its drag is not included.

LIMITS of the actuator disk, to keep in mind when comparing with a test bench:
the disk has no hub body, no tip clearance and no swirl. The real fan gives
less: the tip gap leaks, the hub blocks part of the section, the swirl that no
stator removes carries energy out with the jet. Two first-order parameters
(both 0 by default) bring some of it in:

    mozzo_su_D_disco   no dp inside this fraction of the disk radius (hub); the
                       air there gets no energy (the hub body itself is not in
                       the flow, so this is pessimistic: see fan_coupled.py)
    perdita_swirl      fraction of dp lost as swirl, the disk gives (1 - it) dp
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .config import GAMMA_AIR, R_AIR
from .fluids import FLUIDS
from ..solver.fvmesh import FVMesh

# Grid choice of input.py. "optimise" lists the grids of the shape optimisation,
# coarse first. "verify" lists the three grids, a factor sqrt(2) apart, that
# solve the final shape: the last one gives the value, all three its error.
GRID_LEVELS = {
    "coarse": dict(optimise=[(64, 26)], verify=[(64, 26), (90, 36), (128, 51)]),
    "medium": dict(optimise=[(64, 26), (90, 36)], verify=[(90, 36), (128, 51), (180, 72)]),
    "fine": dict(optimise=[(64, 26), (90, 36), (128, 51)],
                 verify=[(128, 51), (180, 72), (256, 102)]),
}


@dataclass
class PropulsionCase:
    """Operating point and limits of the duct (see input.py)."""
    fluid: str
    V0: float                    # flight speed [m/s]
    p_amb: float                 # ambient pressure [Pa]
    D_ext_max: float             # largest outer diameter of the tube [m]
    L_max: float                 # largest overall length of the tube [m]
    L_disk: float                # axial length of the disk band [m]
    gap_parete: float = 0.005    # outer edge to inner duct [m]
    spessore_parete: float = 0.002   # wall of the CAD tube [m]
    raggio_bocca_su_D: float = 0.2   # bell-mouth radius / inlet diameter of the CAD tube
    D_disk_min_ratio: float = 0.4    # smallest duct radius / R_int_max
    dp_disk: float = 100.0       # total-pressure rise of the disk [Pa], set by the dp loop
    T_target: Optional[float] = None # thrust per nozzle wanted [N]
    P_max: Optional[float] = None    # largest power allowed [W], None = free
    L_min: Optional[float] = None    # smallest overall length of the tube [m], None = free
    L_target: Optional[float] = None # tube length to hold (+/- a small window) [m], None = free
    semiangolo_max_deg: float = 4.0  # steepest diffuser wall (half angle) [deg]
    mozzo_su_D_disco: float = 0.0    # hub / disk diameter: no dp inside it (see docstring)
    perdita_swirl: float = 0.0       # fraction of dp lost as swirl (see docstring)
    turbulence_model: str = "baldwin_lomax"
    Nz: int = 64
    Nr: int = 26
    wall_clustering: float = 3.5     # keeps y+ below 5 on every grid level
    throat_refine: float = 3.0

    rho: float = field(init=False)
    mu: float = field(init=False)
    p_vap: float = field(init=False)
    is_gas: bool = field(init=False)
    speed_of_sound: float = field(init=False)

    def __post_init__(self) -> None:
        if self.fluid not in FLUIDS:
            raise ValueError(f"Unknown fluid '{self.fluid}'. Known: {', '.join(FLUIDS)}.")
        for name in ("dp_disk", "L_disk", "D_ext_max", "L_max", "p_amb", "gap_parete",
                     "spessore_parete"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive, got {getattr(self, name)}.")
        if self.V0 < 0.0:
            raise ValueError(f"V0 cannot be negative, got {self.V0}.")
        if self.spessore_parete > self.gap_parete:
            raise ValueError(f"spessore_parete ({self.spessore_parete}) must not exceed "
                             f"gap_parete ({self.gap_parete}).")
        if not 0.05 <= self.raggio_bocca_su_D <= 0.5:
            raise ValueError(f"raggio_bocca_su_D must be between 0.05 and 0.5, got "
                             f"{self.raggio_bocca_su_D}.")
        if self.R_int_max <= 0.0:
            raise ValueError(f"gap_parete ({self.gap_parete}) leaves no room inside "
                             f"D_ext_max ({self.D_ext_max}).")
        if not 0.0 < self.D_disk_min_ratio < 1.0:
            raise ValueError(f"D_disk_min_ratio must be between 0 and 1, got "
                             f"{self.D_disk_min_ratio}.")
        if self.T_target is not None and self.T_target <= 0.0:
            raise ValueError(f"The thrust per nozzle must be positive, got {self.T_target}.")
        if self.L_min is not None and not 0.0 < self.L_min < self.L_max:
            raise ValueError(f"L_min ({self.L_min}) must be between 0 and L_max ({self.L_max}).")
        if self.L_target is not None and not 0.0 < self.L_target <= self.L_max:
            raise ValueError(f"L_target ({self.L_target}) must be between 0 and L_max "
                             f"({self.L_max}).")
        if 4.0 * self.L_disk >= self.L_max:
            raise ValueError(f"L_disk ({self.L_disk}) is too long for L_max ({self.L_max}).")
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
    def R_ext(self) -> float:
        return 0.5 * self.D_ext_max

    @property
    def R_int_max(self) -> float:
        """Largest radius of the inner duct [m]."""
        return 0.5 * self.D_ext_max - self.gap_parete

    @property
    def R_min(self) -> float:
        """Smallest radius of the duct and of the fan [m]."""
        return self.D_disk_min_ratio * self.R_int_max

    @property
    def V_jet_ideal(self) -> float:
        """Exit speed with no losses [m/s]."""
        return math.sqrt(2.0 * self.dp_disk / self.rho + self.V0 ** 2)

    def dp_ideal(self, A_exit: float, T: float) -> float:
        """dp of a lossless disk that gives thrust T through exit area A_exit [Pa].

        T = rho A Ve (Ve - V0) solved for Ve, then dp = rho (Ve^2 - V0^2) / 2;
        static, it is T / (2 A).
        """
        Ve = 0.5 * (self.V0 + math.sqrt(self.V0 ** 2 + 4.0 * T / (self.rho * A_exit)))
        return 0.5 * self.rho * (Ve ** 2 - self.V0 ** 2)


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
                       rho: float, p_out: float = 0.0) -> float:
    """Net thrust [N] from the exit face: momentum flux + (p - p_amb) A - rho Q V0.

    p_out is the gauge pressure on the exit face (kinematic p / rho would be wrong:
    this is in Pa); the exit condition makes it 0.
    """
    return float(rho * np.sum(F_out ** 2 / A_out) + p_out * np.sum(A_out) - rho * Q * V0)
