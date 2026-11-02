import copy
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from ventola_designer.geometry_checks import screen_geometry
from ventola_designer.config import load_case
from ventola_designer.settings import sizing_settings
from ventola_designer.optimizer import evaluate

ROOT=Path(__file__).resolve().parents[1]


class GeometryScreenTests(unittest.TestCase):
    def setUp(self):
        self.design={'outer_diameter_m':.1,'hub_diameter_m':.02,'blade_count':4,
                     'profile':'NACA0012','span_nodes':[0,1],'chord_m':[.02,.02],
                     'pitch_deg':[0,0],'rpm_by_point':[10000,10000]}

    def test_projected_gap_known_for_zero_pitch(self):
        margins, report=screen_geometry(self.design)
        expected=2*math.pi*.01/4-.02
        self.assertAlmostEqual(report['min_circumferential_envelope_gap_m'],expected,places=12)
        self.assertLess(min(margins),0)

    def test_positive_gap_does_not_mask_insufficient_thickness(self):
        self.design['chord_m']=[.005,.005]
        margins, report=screen_geometry(self.design,min_thickness=.001)
        self.assertGreater(report['min_circumferential_envelope_gap_m'],0)
        self.assertAlmostEqual(report['min_section_max_thickness_m'],.0006,delta=.000002)
        self.assertLess(min(margins),0)

    def test_scaling_and_invalid_geometry(self):
        _, base=screen_geometry(self.design)
        scaled=copy.deepcopy(self.design)
        for k in ('outer_diameter_m','hub_diameter_m'):
            scaled[k]*=3
        scaled['chord_m']=[3*c for c in scaled['chord_m']]
        _, changed=screen_geometry(scaled)
        self.assertAlmostEqual(changed['min_section_max_thickness_m'],3*base['min_section_max_thickness_m'])
        self.assertAlmostEqual(changed['min_circumferential_envelope_gap_m'],3*base['min_circumferential_envelope_gap_m'])
        scaled['span_nodes']=[1,0]
        with self.assertRaises(ValueError):
            screen_geometry(scaled)
        with self.assertRaises(ValueError):
            sizing_settings({'sizing':{'minimum_section_thickness_m':-1}})

    def test_optimizer_receives_geometry_constraints_and_refines_checks(self):
        case=load_case(ROOT/'input_esempio.json')
        cfg=sizing_settings(case)
        # Prestazioni sintetiche ammissibili: deve restare visibile la violazione geometrica.
        with patch('ventola_designer.optimizer.solve',return_value={
                'thrust_rotor_N':1.,'shaft_power_W':3.,'Mach_max':.1}):
            _, cons, _=evaluate(case,self.design,None)
            _, fine, _=evaluate(case,self.design,None,stations=cfg['stations_verification'])
        n=2*len(case['operating_points'])+cfg['solidity_stations']
        self.assertEqual(len(cons),n+2*cfg['geometry_stations'])
        self.assertEqual(len(fine),n+2*(2*cfg['geometry_stations']-1))
        self.assertLess(min(cons[n:]),0)


if __name__=='__main__':
    unittest.main()
