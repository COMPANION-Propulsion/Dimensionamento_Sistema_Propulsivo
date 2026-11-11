"""
profilo.py
==========
Thrust needed to cover a distance in a given time, starting and ending at rest.

Motion profiles, with t the time available and s the distance:

    bang_bang   accelerate for t/2, brake for t/2: the smallest thrust
                a = 4 s / t^2
    trapezio    accelerate, coast for a fraction f_c of t, brake
                t_a = t (1 - f_c) / 2,   a = s / (t_a (t - t_a))

Thrust, with m the mass of the cube and n the nozzles of one face:

    T = m k (a + a_d)  (k = margin factor, a_d = residual disturbance)
    T_nozzle = T / n

Braking uses the nozzles of the opposite face, with the same thrust.

The experiment flies on parabolic flights, not in perfect free fall: a residual
acceleration (about 0.01 g) acts on the cube in an unknown direction. The thrust
is sized to overcome it on top of the kinematic acceleration, a_d = disturbo_residuo_g g
(0 = ideal free fall). a and v_max stay the kinematic ones.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

PROFILES = ("bang_bang", "trapezio")
COAST_MAX = 0.9
G0 = 9.80665    # [m/s^2]


@dataclass
class Motion:
    """Inputs of input.py (SPINTA) and the thrust that follows from them."""
    distanza: float                 # [m]
    tempo: float                    # [s]
    massa: float                    # [kg]
    n_ugelli: int                   # nozzles of one face
    profilo: str = "bang_bang"
    frazione_crociera: float = 0.0  # [-] trapezio only
    fattore_margine: float = 1.0    # [-]
    disturbo_residuo_g: float = 0.0  # [g] residual acceleration of the flight, 0 = free fall

    def __post_init__(self) -> None:
        for name in ("distanza", "tempo", "massa", "fattore_margine"):
            if not getattr(self, name) > 0.0:
                raise ValueError(f"{name} must be positive, got {getattr(self, name)}.")
        if not self.disturbo_residuo_g >= 0.0:
            raise ValueError(f"disturbo_residuo_g must be >= 0, got {self.disturbo_residuo_g}.")
        if int(self.n_ugelli) != self.n_ugelli or self.n_ugelli < 1:
            raise ValueError(f"n_ugelli must be a whole number >= 1, got {self.n_ugelli}.")
        self.n_ugelli = int(self.n_ugelli)
        if self.profilo not in PROFILES:
            raise ValueError(f"profilo must be one of {', '.join(PROFILES)}, got '{self.profilo}'.")
        if self.profilo == "bang_bang":
            self.frazione_crociera = 0.0
        elif not 0.0 <= self.frazione_crociera <= COAST_MAX:
            raise ValueError(f"frazione_crociera must be in 0..{COAST_MAX}, "
                             f"got {self.frazione_crociera}.")

    @property
    def t_acc(self) -> float:
        """Time of the acceleration, equal to the braking one [s]."""
        return 0.5 * self.tempo * (1.0 - self.frazione_crociera)

    @property
    def acceleration(self) -> float:
        """[m/s^2]"""
        ta = self.t_acc
        return self.distanza / (ta * (self.tempo - ta))

    @property
    def v_max(self) -> float:
        return self.acceleration * self.t_acc

    @property
    def disturbance(self) -> float:
        """Residual acceleration the thrust must overcome [m/s^2]."""
        return self.disturbo_residuo_g * G0

    @property
    def thrust_total(self) -> float:
        """Thrust of one face, margin and residual disturbance included [N]."""
        return self.massa * self.fattore_margine * (self.acceleration + self.disturbance)

    @property
    def thrust_nozzle(self) -> float:
        return self.thrust_total / self.n_ugelli

    def summary(self) -> dict:
        return dict(input=asdict(self), t_accelerazione_s=self.t_acc,
                    t_crociera_s=self.tempo - 2.0 * self.t_acc,
                    accelerazione_m_s2=self.acceleration, v_max_m_s=self.v_max,
                    accelerazione_disturbo_m_s2=self.disturbance,
                    quota_spinta_disturbo=self.disturbance / (self.acceleration + self.disturbance),
                    T_totale_N=self.thrust_total, T_ugello_N=self.thrust_nozzle,
                    impulso_per_ugello_Ns=2.0 * self.thrust_nozzle * self.t_acc)

    def history(self, n: int = 601) -> dict:
        """Time histories, the switching times included as samples.

        T_ugello is signed: + for the face that pushes, - for the one that brakes,
        and is the thrust actually sized (disturbance and margin included, 0 while
        coasting). s, v and a are the kinematic ones, without the disturbance.
        """
        ta, t_end, a = self.t_acc, self.tempo, self.acceleration
        t = np.unique(np.concatenate((np.linspace(0.0, t_end, n), [ta, t_end - ta])))
        acc = np.where(t < ta, a, np.where(t > t_end - ta, -a, 0.0))
        v = np.where(t < ta, a * t,
                     np.where(t > t_end - ta, a * (t_end - t), a * ta))
        s_acc = 0.5 * a * ta ** 2
        s = np.where(t < ta, 0.5 * a * t ** 2,
                     np.where(t > t_end - ta, self.distanza - 0.5 * a * (t_end - t) ** 2,
                              s_acc + a * ta * (t - ta)))
        T = np.sign(acc) * self.thrust_nozzle
        return dict(t=t, s=s, v=v, a=acc, T_ugello=T)
