"""Tabelle numeriche: interpolazione in alpha, log(Re), Mach, senza extrapolazione."""
import bisect
import hashlib
import json
import math
from pathlib import Path


class PolarDomainError(ValueError):
    pass


def coordinate_hash(coordinates):
    text = "\n".join(f"{x:.12g},{y:.12g}" for x, y in coordinates)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def bracket(axis, value, name):
    if not math.isfinite(value) or value < axis[0] or value > axis[-1]:
        raise PolarDomainError(f"{name}={value:g} fuori [{axis[0]:g}, {axis[-1]:g}]")
    i = min(max(bisect.bisect_right(axis, value)-1, 0), len(axis)-2)
    return i, (value-axis[i])/(axis[i+1]-axis[i])


class PolarGrid:
    def __init__(self, data, min_confidence=0.5):
        self.data = data
        self.profile = data["profile"]
        self.min_confidence = min_confidence
        self.axes = [data[k] for k in ("reynolds", "mach", "alpha_deg")]
        for axis in self.axes:
            if len(axis) < 2 or any(not math.isfinite(x) for x in axis) or any(b <= a for a,b in zip(axis,axis[1:])):
                raise ValueError("Assi polari non validi.")
        if self.axes[0][0] <= 0 or not 0 <= min_confidence <= 1:
            raise ValueError("Reynolds o soglia confidence non validi.")
        self.log_re = [math.log(x) for x in self.axes[0]]
        for field in ("cl", "cd", "confidence"):
            grid = data[field]
            if len(grid) != len(self.axes[0]):
                raise ValueError("Forma polare non valida.")
            for plane in grid:
                if len(plane) != len(self.axes[1]) or any(len(row) != len(self.axes[2]) for row in plane):
                    raise ValueError("Forma polare non valida.")
                if any(not math.isfinite(x) or (field == "cd" and x <= 0) or (field == "confidence" and not 0 <= x <= 1) for row in plane for x in row):
                    raise ValueError("Coefficienti polari non validi.")

    @classmethod
    def load(cls, path, **kwargs):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), **kwargs)

    def validate_profile(self, profile):
        from .geometry import naca4
        if self.profile != profile or coordinate_hash(naca4(profile)) != self.data["coordinates_sha256"]:
            raise PolarDomainError("Profilo o coordinate diversi da quelli della polare.")

    def coefficients(self, alpha, reynolds, mach):
        if not math.isfinite(reynolds) or reynolds <= 0:
            raise PolarDomainError("Reynolds non positivo o non finito.")
        # Controllare sul Re originale per includere esattamente gli estremi.
        bracket(self.axes[0], reynolds, "Re")
        ir, wr = bracket(self.log_re, math.log(reynolds), "log(Re)")
        im, wm = bracket(self.axes[1], mach, "Mach")
        ia, wa = bracket(self.axes[2], alpha, "alpha")
        cl = cd = 0.0
        confidence = 1.0
        for dr in (0,1):
            for dm in (0,1):
                for da in (0,1):
                    weight = (wr if dr else 1-wr)*(wm if dm else 1-wm)*(wa if da else 1-wa)
                    if weight <= 0:
                        continue
                    conf = self.data["confidence"][ir+dr][im+dm][ia+da]
                    confidence = min(confidence, conf)
                    cl += weight*self.data["cl"][ir+dr][im+dm][ia+da]
                    cd += weight*self.data["cd"][ir+dr][im+dm][ia+da]
        if confidence < self.min_confidence:
            raise PolarDomainError(f"Confidence dei nodi polari {confidence:.3f} < {self.min_confidence:g}")
        return cl, cd, confidence
