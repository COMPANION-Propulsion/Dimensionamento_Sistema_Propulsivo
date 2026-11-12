"""Controlli fisici/geometrici indipendenti, non verifica delle prestazioni."""
import copy
import math
from pathlib import Path
import tempfile
import json
import unittest
from ventola_designer.config import load_case
from ventola_designer.geometry import naca4, initial_design, blade_sections

CASE = Path(__file__).resolve().parents[1] / "input_esempio.json"


class GeometryTests(unittest.TestCase):
    def test_symmetric_airfoil_and_thickness(self):
        points = naca4("NACA0012", 200)
        for a,b in zip(points, reversed(points)):
            self.assertAlmostEqual(a[0], b[0], places=12)
            self.assertAlmostEqual(a[1], -b[1], places=12)
        thickness = max(y for x,y in points)-min(y for x,y in points)
        self.assertAlmostEqual(thickness, 0.12, delta=0.0002)

    def test_camber_reference(self):
        points = naca4("NACA4412", 100)
        # Upper/lower are offsets normal to camber: midpoint recovers camber.
        upper = list(reversed(points[:101]))
        lower = [points[100]]+points[101:]
        i = 40
        x,y = ((upper[i][j]+lower[i][j])/2 for j in (0,1))
        self.assertAlmostEqual(y, .04/.4**2*(.8*x-x*x), places=12)

    def test_diameter_envelope_and_scaling(self):
        case = load_case(CASE)
        design = initial_design(case, "NACA4412", 4)
        sections = blade_sections(design)
        for section in sections:
            for x,y,z in section["points"]:
                self.assertAlmostEqual(math.hypot(x,y), section["radius_m"], places=12)
                self.assertLessEqual(math.hypot(x,y), .05+1e-12)
        scaled = copy.deepcopy(design)
        for key in ("outer_diameter_m", "hub_diameter_m"):
            scaled[key] *= 2
        scaled["chord_m"] = [2*c for c in scaled["chord_m"]]
        for a,b in zip(sections, blade_sections(scaled)):
            for pa,pb in zip(a["points"], b["points"]):
                for v,w in zip(pa,pb):
                    self.assertAlmostEqual(2*v,w,places=12)

    def test_dorso_a_monte(self):
        # Dorso (y > 0) a monte (z minore) e in coda nel verso di rotazione (-theta).
        case = load_case(CASE)
        design = initial_design(case, "NACA4412", 4)
        section = blade_sections(design, panels=80)[2]
        pts = section["points"]
        self.assertEqual(len(pts), 161)
        upper, lower = pts[40], pts[120]
        self.assertLess(upper[2], lower[2])
        self.assertGreater(math.atan2(upper[1], upper[0]), math.atan2(lower[1], lower[0]))
        self.assertLess(pts[80][2], pts[0][2])

    def test_invalid_pressure_and_hub_rejected(self):
        original = json.loads(CASE.read_text(encoding="utf-8"))
        for bad in ("pressure", "hub", "boolean", "nan"):
            data = copy.deepcopy(original)
            if bad == "hub":
                data["rotor"]["hub_diameter_bounds_m"] = [.03,.12]
            else:
                data["air"]["static_pressure_Pa"] = {"pressure": -1, "boolean": True, "nan": float("nan")}[bad]
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/"case.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_case(path)


if __name__ == "__main__":
    unittest.main()
