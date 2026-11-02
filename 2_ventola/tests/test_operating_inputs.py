import contextlib
import copy
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from ventola_designer.config import load_case, operating_air, velocity_reference
from ventola_designer.bemt import solve, air_properties
from ventola_designer.geometry import initial_design
from ventola_designer.polars import PolarGrid
from ventola_designer.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


class OperatingInputsTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(ROOT/'input_esempio.json')

    def test_override_is_local_and_partial(self):
        original = copy.deepcopy(self.case)
        point = {'air':{'static_pressure_Pa':90000}}
        self.assertEqual(operating_air(self.case,point)['static_pressure_Pa'],90000)
        self.assertEqual(operating_air(self.case,point)['temperature_K'],self.case['air']['temperature_K'])
        self.assertEqual(self.case, original)
        self.assertEqual(operating_air(self.case,{})['static_pressure_Pa'],101325)

    def test_bad_air_and_reference_rejected(self):
        for air in ({'temperature_K':0},{'static_pressure_Pa':float('nan')},
                    {'relative_humidity':True},{'relative_humidity':.1},{'pressure':90000},None):
            with self.subTest(air=air), self.assertRaises(ValueError):
                operating_air(self.case,{'air':air})
        with self.assertRaises(ValueError):
            velocity_reference({**self.case,'velocity_reference':'rotor_plane'})

    def test_bemt_uses_point_air(self):
        design = initial_design(self.case,'NACA4412',2)
        design.update(rpm=15000,pitch_deg=[22,15.7,9.4,4])
        polar = PolarGrid.load(ROOT/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')
        point = copy.deepcopy(self.case['operating_points'][0])
        base = solve(self.case,design,point,polar)
        point['air'] = {'temperature_K':305.15,'static_pressure_Pa':95000}
        with patch('ventola_designer.bemt.air_properties',wraps=air_properties) as properties:
            changed = solve(self.case,design,point,polar)
        properties.assert_called_once_with(305.15,95000)
        self.assertNotEqual(changed['thrust_rotor_N'],base['thrust_rotor_N'])
        self.assertEqual(changed['air_conditions']['static_pressure_Pa'],95000)

    def test_size_validate_does_not_optimize_or_create_output(self):
        with patch('ventola_designer.optimizer.optimize_pair') as optimize, \
             patch('ventola_designer.optimizer.Path.mkdir') as mkdir, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(['size','--input',str(ROOT/'input_esempio.json'),'--validate-only'])
        self.assertEqual(code,0)
        optimize.assert_not_called()
        mkdir.assert_not_called()
        self.assertIn('far_upstream',output.getvalue())


if __name__ == '__main__':
    unittest.main()
