"""Controlli sui dati reali generati e limite energetico ideale indipendente."""
import math
from pathlib import Path
import unittest

from ventola_designer.bemt import solve
from ventola_designer.config import load_case, load_catalog
from ventola_designer.geometry import initial_design
from ventola_designer.polars import PolarGrid, PolarDomainError

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "ventola_designer" / "airfoils" / "polars_neuralfoil"


class BemtTests(unittest.TestCase):
    def test_catalog_tables_match_generated_profiles(self):
        for profile in load_catalog():
            polar = PolarGrid.load(TABLES / f"{profile}.json")
            polar.validate_profile(profile)
            cl, cd, confidence = polar.coefficients(4, 30000, .1)
            self.assertTrue(math.isfinite(cl))
            self.assertGreater(cd, 0)
            self.assertGreaterEqual(confidence, .5)

    def test_static_power_above_ideal_actuator_disk_bound(self):
        case = load_case(ROOT / "input_esempio.json")
        design = initial_design(case, "NACA4412", 2)
        design.update(rpm=15000, pitch_deg=[22, 15.7, 9.4, 4])
        point = dict(case["operating_points"][0], axial_inlet_velocity_m_s=0)
        polar = PolarGrid.load(TABLES / "NACA4412.json")
        result = solve(case, design, point, polar)
        # Independent actuator-disk energy bound: no swirl or profile drag.
        rho = case["air"]["static_pressure_Pa"] / (287.05 * case["air"]["temperature_K"])
        area = math.pi / 4 * (design["outer_diameter_m"]**2-design["hub_diameter_m"]**2)
        ideal_power = result["thrust_rotor_N"]**1.5 / math.sqrt(2*rho*area)
        self.assertGreaterEqual(result["shaft_power_W"], ideal_power)
        self.assertLess(result["momentum_residual_max"], 1e-5)

    def test_solver_rejects_wrong_profile_table(self):
        case = load_case(ROOT / "input_esempio.json")
        design = initial_design(case, "NACA0012", 2)
        with self.assertRaises(PolarDomainError):
            solve(case, design, case["operating_points"][0],
                  PolarGrid.load(TABLES / "NACA4412.json"))


if __name__ == "__main__":
    unittest.main()
