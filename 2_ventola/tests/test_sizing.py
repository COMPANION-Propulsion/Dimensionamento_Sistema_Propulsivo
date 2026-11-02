import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from ventola_designer.config import load_case
from ventola_designer.settings import sizing_settings
from ventola_designer.optimizer import seed_designs, optimize_pair, variable_bounds, encode

ROOT = Path(__file__).resolve().parents[1]


class SizingTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(ROOT/'input_esempio.json')

    def test_invalid_configuration(self):
        for key,value in [('starts',True),('seed_samples',0),('max_Mach',float('nan')),
                          ('pitch_deg_bounds',[40,20]),('chord_over_D_bounds',[0,.2]),
                          ('stations_final',32),('unknown_option',1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                sizing_settings({'sizing':{key:value}})

    def test_defaults_do_not_share_mutable_values(self):
        cfg=sizing_settings({})
        cfg['pitch_deg_bounds'][0]=12
        self.assertEqual(sizing_settings({})['pitch_deg_bounds'][0],0)

    def test_seed_generation_respects_new_user_limits_and_is_reproducible(self):
        self.case['rotor']['outer_diameter_m']=.3
        self.case['rotor']['shaft_speed_bounds_rpm']=[1200,2500]
        self.case['sizing'].update(chord_over_D_bounds=[.02,.03],pitch_deg_bounds=[5,15])
        seeds=list(seed_designs(self.case,'NACA2412',3))
        self.assertEqual(seeds,list(seed_designs(self.case,'NACA2412',3)))
        for design in seeds:
            self.assertTrue(all(1200<=r<=2500 for r in design['rpm_by_point']))
            self.assertTrue(all(.006<=c<=.009 for c in design['chord_m']))
            self.assertTrue(all(5<=p<=15 for p in design['pitch_deg']))
            x=encode(self.case,design,design['rpm_by_point'])
            self.assertTrue(np.all((x>=0)&(x<=1)))

    def test_multiple_starts_select_only_accepted_results(self):
        # Aerodinamica sostituita solo per isolare la selezione degli avvii.
        outcomes=[{'accepted':False,'energy_J':1,'status':'not_accepted'},
                  {'accepted':True,'energy_J':3,'status':'converged_feasible'},
                  {'accepted':True,'energy_J':2,'status':'converged_feasible'}]
        with patch('ventola_designer.optimizer.evaluate',return_value=(10,np.array([1.]),[])), \
             patch('ventola_designer.optimizer._optimize_start',side_effect=outcomes) as start:
            result=optimize_pair(self.case,'NACA4412',2)
        self.assertEqual(start.call_count,3)
        self.assertEqual(result['energy_J'],2)
        self.assertEqual(len(result['attempts']),3)
        self.assertTrue(result['accepted'])

    def test_failed_starts_remain_failed(self):
        with patch('ventola_designer.optimizer.evaluate',return_value=(10,np.array([1.]),[])), \
             patch('ventola_designer.optimizer._optimize_start',return_value={'accepted':False,'status':'not_accepted'}):
            result=optimize_pair(self.case,'NACA4412',2)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['starts_executed'],3)


if __name__=='__main__':
    unittest.main()
