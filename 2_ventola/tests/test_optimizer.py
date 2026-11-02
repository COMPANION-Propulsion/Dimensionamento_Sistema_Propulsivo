import copy
from pathlib import Path
import unittest
from ventola_designer.config import load_case
from ventola_designer.geometry import initial_design
from ventola_designer.polars import PolarGrid
from ventola_designer.optimizer import evaluate, optimize_pair

ROOT = Path(__file__).resolve().parents[1]


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(ROOT/'input_esempio.json')
        self.design = initial_design(self.case,'NACA4412',2)
        self.design.update(pitch_deg=[22,15.7,9.4,4],rpm_by_point=[15000,15000])
        self.polar = PolarGrid.load(ROOT/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')

    def test_duration_weights_energy_not_thrust(self):
        energy, _, results = evaluate(self.case,self.design,self.polar)
        self.case['operating_points'][1]['duration_s'] *= 2
        updated, _, same = evaluate(self.case,self.design,self.polar)
        self.assertAlmostEqual(updated-energy,results[1]['shaft_power_W']*600)
        self.assertEqual(results,same)

    def test_missing_operating_speed_rejected(self):
        self.design['rpm_by_point'].pop()
        with self.assertRaises(ValueError):
            evaluate(self.case,self.design,self.polar)

    def test_unreachable_requirement_does_not_return_design(self):
        case = copy.deepcopy(self.case)
        for p in case['operating_points']:
            p['minimum_rotor_thrust_N'] = 1e6
        result = optimize_pair(case,'NACA4412',2,maxiter=1)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['status'],'no_feasible_seed_found')


if __name__ == '__main__':
    unittest.main()
