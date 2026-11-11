"""
cad_duct.py
===========
CAD files of the optimised duct, in millimetres with the axis along x.

    tubo.step / .stl            the hollow tube with bell mouth and lips
    fluido.step / .stl          the air inside it, closed, ready to mesh
    fluido_ingresso/parete/uscita.stl   the same surface split into patches
                                (snappyHexMesh and the like)
    zona_disco.step / .stl      the band of the fan, for an actuator-disk zone
    profilo.dxf, profilo.csv    the wall line

STEP: the duct wall is the EXACT B-spline of the design (see
MorphedGeometry.bspline_curves), the bell mouth an exact arc, so each piece
is one smooth face. The outer wall of the tube is an offset of the spline,
interpolated through N_OFFSET points: far below a micron off.

STL: every piece is sampled so that no chord leaves the true profile by more
than CHORD_TOL_MM, and no facet is longer than it is wide; the rings share
their vertices, so the files are closed.
"""

from __future__ import annotations

import csv
import math
import os
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.interpolate import BSpline

from ..geometry import Segment, arc_segment
from .cad import BELL_SWEEP_DEG, _lip, _offset_segment, bell_radius, cq, ezdxf

CHORD_TOL_MM = 0.005     # largest distance between an STL facet and the true surface
N_DENSE = 4001           # samples of a piece before thinning
N_OFFSET = 400           # interpolation points of an offset spline in the STEP
MIN_THETA = 180          # fewest facets around the axis

Curve = Callable[[np.ndarray], np.ndarray]   # u in 0..1 -> (n, 2) points (z, r) [mm]


class Piece:
    """One piece of a (z, r) profile [mm]: its points and its CAD edge."""

    def __init__(self, f: Curve, edge: Callable[[], object]):
        self.f, self._edge = f, edge

    @property
    def start(self) -> Tuple[float, float]:
        return tuple(self.f(np.array([0.0]))[0])

    @property
    def end(self) -> Tuple[float, float]:
        return tuple(self.f(np.array([1.0]))[0])

    def edge(self):
        return self._edge()

    def reversed(self) -> "Piece":
        return Piece(lambda u: self.f(1.0 - np.asarray(u)), self._edge)


def _v(p) -> "cq.Vector":
    return cq.Vector(float(p[0]), float(p[1]), 0.0)


def line(a, b) -> Piece:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return Piece(lambda u: a + np.asarray(u)[:, None] * (b - a),
                 lambda: cq.Edge.makeLine(_v(a), _v(b)))


def arc(s: Segment) -> Piece:
    cz, cr = s.centre
    a0 = math.atan2(s.start[1] - cr, s.start[0] - cz)
    half = math.atan2(s.mid[1] - cr, s.mid[0] - cz) - a0
    half = (half + math.pi) % (2 * math.pi) - math.pi
    Ra = math.dist(s.start, s.centre)

    def f(u):
        a = a0 + 2.0 * half * np.asarray(u)
        return np.column_stack((cz + Ra * np.cos(a), cr + Ra * np.sin(a)))
    return Piece(f, lambda: cq.Edge.makeThreePointArc(_v(s.start), _v(s.mid), _v(s.end)))


def bspline(knots: np.ndarray, poles: np.ndarray) -> Piece:
    """Exact cubic B-spline curve; poles in mm."""
    curve = BSpline(knots, poles, 3)

    def edge():
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.Geom import Geom_BSplineCurve
        from OCP.gp import gp_Pnt
        from OCP.TColgp import TColgp_Array1OfPnt
        from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
        P = TColgp_Array1OfPnt(1, len(poles))
        for i, (z, r) in enumerate(poles, 1):
            P.SetValue(i, gp_Pnt(float(z), float(r), 0.0))
        k, m = np.unique(knots, return_counts=True)
        K, M = TColStd_Array1OfReal(1, k.size), TColStd_Array1OfInteger(1, k.size)
        for i, (a, b) in enumerate(zip(k, m), 1):
            K.SetValue(i, float(a))
            M.SetValue(i, int(b))
        return cq.Edge(BRepBuilderAPI_MakeEdge(Geom_BSplineCurve(P, K, M, 3)).Edge())
    return Piece(lambda u: curve(np.clip(np.asarray(u), 0.0, 1.0)), edge)


def offset_bspline(knots: np.ndarray, poles: np.ndarray, t: float) -> Piece:
    """The B-spline moved by t along its left normal (outwards for a +z wall)."""
    curve = BSpline(knots, poles, 3)
    d = curve.derivative()

    def f(u):
        u = np.clip(np.asarray(u), 0.0, 1.0)
        p, dp = curve(u), d(u)
        n = np.column_stack((-dp[:, 1], dp[:, 0])) / np.linalg.norm(dp, axis=1)[:, None]
        return p + t * n
    return Piece(f, lambda: cq.Edge.makeSpline([_v(p) for p in f(np.linspace(0, 1, N_OFFSET))]))


# ---------------------------------------------------------------------------
# Profiles [mm]
# ---------------------------------------------------------------------------
def _bell(geom) -> Segment:
    R = geom.R_inlet * 1e3
    Rb = bell_radius(2.0 * R, geom.config.wall_thickness * 1e3, geom.config.bell_radius_ratio)
    a = math.radians(BELL_SWEEP_DEG)
    centre = (0.0, R + Rb)
    start = (-Rb * math.sin(a), centre[1] - Rb * math.cos(a))
    return arc_segment(start, (0.0, R), centre)


def inner_pieces(geom) -> List[Piece]:
    """Wetted wall: bell mouth, intake spline, disk section, diffuser spline."""
    (k_up, p_up), (k_dn, p_dn) = geom.bspline_curves()
    Rd = geom.R_disk * 1e3
    return [arc(_bell(geom)), bspline(k_up, p_up * 1e3),
            line((geom.z_a * 1e3, Rd), (geom.z_b * 1e3, Rd)), bspline(k_dn, p_dn * 1e3)]


def outer_pieces(geom) -> List[Piece]:
    t = geom.config.wall_thickness * 1e3
    (k_up, p_up), (k_dn, p_dn) = geom.bspline_curves()
    Rd = geom.R_disk * 1e3 + t
    return [arc(_offset_segment(_bell(geom), t)), offset_bspline(k_up, p_up * 1e3, t),
            line((geom.z_a * 1e3, Rd), (geom.z_b * 1e3, Rd)), offset_bspline(k_dn, p_dn * 1e3, t)]


def tube_pieces(geom) -> List[Piece]:
    """Closed section of the tube wall."""
    inner, outer = inner_pieces(geom), outer_pieces(geom)
    lip_out = _lip(inner[-1].end, outer[-1].end, 1)
    lip_in = _lip(outer[0].start, inner[0].start, 1)
    return inner + [arc(lip_out)] + [p.reversed() for p in reversed(outer)] + [arc(lip_in)]


def fluid_patches(geom) -> Dict[str, List[Piece]]:
    """Section of the fluid, split into inlet, wall and outlet (axis left open)."""
    wall = inner_pieces(geom)
    (z0, r0), (z1, r1) = wall[0].start, wall[-1].end
    return {"ingresso": [line((z0, 0.0), (z0, r0))], "parete": wall,
            "uscita": [line((z1, r1), (z1, 0.0))]}


def fluid_pieces(geom) -> List[Piece]:
    p = fluid_patches(geom)
    (z0, _), (z1, _) = p["ingresso"][0].start, p["uscita"][0].end
    return p["ingresso"] + p["parete"] + p["uscita"] + [line((z1, 0.0), (z0, 0.0))]


def disk_pieces(geom, L_disk: float) -> List[Piece]:
    zc = 0.5 * (geom.z_a + geom.z_b) * 1e3
    a, b, R = zc - 0.5 * L_disk * 1e3, zc + 0.5 * L_disk * 1e3, geom.R_disk * 1e3
    return [line((a, 0.0), (a, R)), line((a, R), (b, R)), line((b, R), (b, 0.0)),
            line((b, 0.0), (a, 0.0))]


# ---------------------------------------------------------------------------
# STEP
# ---------------------------------------------------------------------------
def write_step(pieces: List[Piece], path: str) -> Optional[str]:
    """Revolve a closed profile about x into a solid and save it."""
    name = os.path.basename(path)
    if cq is None:
        print(f"      Warning: cadquery is not installed; skipping {name}.")
        return None
    try:
        wire = cq.Wire.assembleEdges([p.edge() for p in pieces])
        solid = cq.Solid.revolve(wire, [], 360.0, (0, 0, 0), (1, 0, 0))
        if not solid.isValid():
            print(f"      Warning: {name} not written, the solid is not valid.")
            return None
        solid.exportStep(path)
        return path
    except Exception as e:     # cadquery raises many different types
        print(f"      Warning: STEP export of {name} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# STL
# ---------------------------------------------------------------------------
def _thin(pts: np.ndarray, tol: float, ds_max: float) -> np.ndarray:
    """Fewest points whose chords stay within tol of pts and are at most ds_max long."""
    keep, i, n = [0], 0, len(pts)
    while i < n - 1:
        j = i + 1
        while j + 1 < n:
            k = j + 1
            a, b = pts[i], pts[k]
            ab = b - a
            L = float(np.hypot(*ab))
            if L > ds_max:
                break
            mid = pts[i + 1:k]
            dev = np.abs(ab[0] * (mid[:, 1] - a[1]) - ab[1] * (mid[:, 0] - a[0])) / max(L, 1e-30)
            if dev.size and dev.max() > tol:
                break
            j = k
        keep.append(j)
        i = j
    return pts[keep]


def sample(pieces: List[Piece], tol: float, ds_max: float) -> np.ndarray:
    """Points of a profile, each joint included once."""
    u = np.linspace(0.0, 1.0, N_DENSE)
    out = []
    for p in pieces:
        pts = _thin(p.f(u), tol, ds_max)
        out.append(pts if not out else pts[1:])
    return np.vstack(out)


def _theta_count(r_max: float) -> Tuple[int, float]:
    dtheta = 2.0 * math.acos(1.0 - CHORD_TOL_MM / max(r_max, 10 * CHORD_TOL_MM))
    n = max(MIN_THETA, math.ceil(2.0 * math.pi / dtheta))
    n += (-n) % 4
    return n, 2.0 * math.pi * r_max / n


def _rings(profile: np.ndarray, n_theta: int, closed: bool) -> np.ndarray:
    """Triangles (n, 3, 3) of a profile spun about x, rings sharing vertices."""
    theta = 2.0 * np.pi * np.arange(n_theta) / n_theta
    rings, verts, count = [], [], 0
    for z, r in profile:
        if r < 1e-9:
            verts.append([[z, 0.0, 0.0]])
            rings.append(np.full(n_theta, count))
            count += 1
        else:
            verts.append(np.column_stack((np.full(n_theta, z), r * np.cos(theta),
                                          r * np.sin(theta))))
            rings.append(np.arange(count, count + n_theta))
            count += n_theta
    verts = np.vstack(verts)
    faces = []
    pairs = zip(rings, rings[1:] + rings[:1]) if closed else zip(rings, rings[1:])
    for a, b in pairs:
        a1, b1 = np.roll(a, -1), np.roll(b, -1)
        if b[0] != b1[0]:
            faces.append(np.column_stack((a, b, b1)))
        if a[0] != a1[0]:
            faces.append(np.column_stack((a, b1, a1)))
    return verts[np.vstack(faces)]


def _orient(tris: np.ndarray, outward: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """Flip every triangle whose normal points against outward(centroid)."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    flip = np.einsum("ij,ij->i", n, outward(tris.mean(axis=1))) < 0.0
    tris = tris.copy()
    tris[flip] = tris[flip][:, ::-1]
    return tris


def _orient_closed(tris: np.ndarray) -> np.ndarray:
    signed = np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum()
    return tris[:, ::-1] if signed < 0.0 else tris


def write_stl(tris: np.ndarray, path: str, title: str) -> str:
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-300)
    data = np.zeros(len(tris), dtype=[("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")])
    data["n"] = normals
    data["v"] = tris.reshape(-1, 9)
    with open(path, "wb") as f:
        f.write(title.encode("ascii", "replace")[:80].ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        data.tofile(f)
    return path


def closed_mesh(pieces: List[Piece], r_max: float) -> np.ndarray:
    n_theta, ds = _theta_count(r_max)
    prof = sample(pieces, CHORD_TOL_MM, ds)
    closed = np.allclose(prof[0], prof[-1])
    if closed:
        prof = prof[:-1]
    return _orient_closed(_rings(prof, n_theta, closed))


def watertight(tris: np.ndarray) -> Optional[bool]:
    """True when every edge is shared by exactly two triangles (None without pyvista)."""
    try:
        import pyvista as pv
    except ImportError:
        return None
    flat = tris.reshape(-1, 3)
    pts, idx = np.unique(np.round(flat, 9), axis=0, return_inverse=True)
    faces = np.column_stack((np.full(len(tris), 3), idx.reshape(-1, 3))).ravel()
    mesh = pv.PolyData(pts, faces)
    return bool(mesh.n_open_edges == 0 and mesh.is_manifold)


# ---------------------------------------------------------------------------
# All the CAD files
# ---------------------------------------------------------------------------
def export_duct_cad(geom, L_disk: float, out_dir: str) -> Dict[str, object]:
    """Write the files of the module docstring; returns paths and checks."""
    os.makedirs(out_dir, exist_ok=True)
    t = geom.config.wall_thickness * 1e3
    tube, fluid, disk = tube_pieces(geom), fluid_pieces(geom), disk_pieces(geom, L_disk)
    r_tube = float(sample(tube, 0.01, 1.0)[:, 1].max())
    r_fluid = float(sample(fluid, 0.01, 1.0)[:, 1].max())
    files: List[str] = []
    checks: Dict[str, object] = {}

    for name, pieces, r in (("tubo", tube, r_tube), ("fluido", fluid, r_fluid),
                            ("zona_disco", disk, geom.R_disk * 1e3)):
        step = write_step(pieces, os.path.join(out_dir, f"{name}.step"))
        if step:
            files.append(step)
        tris = closed_mesh(pieces, r)
        files.append(write_stl(tris, os.path.join(out_dir, f"{name}.stl"), f"{name}, mm"))
        checks[f"{name}_triangoli"] = int(len(tris))
        checks[f"{name}_chiuso"] = watertight(tris)

    # patches of the fluid, same rings as fluido.stl, normals out of the fluid
    n_theta, ds = _theta_count(r_fluid)
    outward = {"ingresso": lambda c: np.tile([-1.0, 0.0, 0.0], (len(c), 1)),
               "uscita": lambda c: np.tile([1.0, 0.0, 0.0], (len(c), 1)),
               "parete": lambda c: np.column_stack((np.zeros(len(c)), c[:, 1], c[:, 2]))}
    for name, pieces in fluid_patches(geom).items():
        tris = _orient(_rings(sample(pieces, CHORD_TOL_MM, ds), n_theta, False), outward[name])
        files.append(write_stl(tris, os.path.join(out_dir, f"fluido_{name}.stl"),
                               f"fluido {name}, mm"))

    prof = sample(inner_pieces(geom), CHORD_TOL_MM / 5, ds)
    csv_path = os.path.join(out_dir, "profilo.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["z_mm", "r_mm"])
        w.writerows(np.round(prof, 6).tolist())
    files.append(csv_path)

    dxf = _write_dxf(geom, tube, L_disk, os.path.join(out_dir, "profilo.dxf"))
    if dxf:
        files.append(dxf)
    pts = sample(tube, 0.001, 0.5)
    checks.update(diametro_esterno_mm=2.0 * float(pts[:, 1].max()),
                  lunghezza_mm=float(np.ptp(pts[:, 0])), spessore_mm=t)
    return dict(files=files, checks=checks)


def _write_dxf(geom, tube: List[Piece], L_disk: float, path: str) -> Optional[str]:
    if ezdxf is None:
        print("      Warning: ezdxf is not installed; skipping profilo.dxf.")
        return None
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    doc.layers.add("PARETE_INTERNA", color=1)
    doc.layers.add("TUBO", color=5)
    doc.layers.add("DISCO", color=3)
    doc.layers.add("ASSE", color=8, linetype="CENTER")
    inner = sample(inner_pieces(geom), 0.001, 0.5)
    for sign in (1.0, -1.0):
        msp.add_lwpolyline([(z, sign * r) for z, r in inner], dxfattribs={"layer": "PARETE_INTERNA"})
        msp.add_lwpolyline([(z, sign * r) for z, r in sample(tube, 0.001, 0.5)],
                           close=True, dxfattribs={"layer": "TUBO"})
    d = [p.start for p in disk_pieces(geom, L_disk)]
    msp.add_lwpolyline([(z, r) for z, r in d] + [(z, -r) for z, r in reversed(d)],
                       close=True, dxfattribs={"layer": "DISCO"})
    z = [p[0] for p in sample(tube, 0.01, 1.0)]
    msp.add_line((min(z), 0), (max(z), 0), dxfattribs={"layer": "ASSE"})
    doc.saveas(path)
    return path
