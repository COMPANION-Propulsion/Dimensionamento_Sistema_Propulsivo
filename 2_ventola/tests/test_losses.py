import math
from pathlib import Path
import unittest
from ventola_designer.losses import prandtl_factors
from ventola_designer.settings import sizing_settings
from ventola_designer.config import load_case
from ventola_designer.geometry import initial_design
from ventola_designer.bemt import solve
from ventola_designer.polars import PolarGrid

ROOT = Path(__file__).resolve().parents[1]


class LossTests(unittest.TestCase):
    def test_known_angle_and_scale_invariance(self):
        r,h,t = 2.,2/(1+math.log(2)),2*(1+math.log(2))
        factors = prandtl_factors(2,r,h,t,math.pi/2)
        for f in factors:
            self.assertAlmostEqual(f,2/3,places=12)
        for a,b in zip(factors,prandtl_factors(2,r*10,h*10,t*10,math.pi/2)):
            self.assertAlmostEqual(a,b,places=12)

    def test_endpoints_and_zero_angle(self):
        self.assertEqual(prandtl_factors(3,1,1,4,.2)[1],0)
        self.assertEqual(prandtl_factors(3,4,1,4,.2)[0],0)
        self.assertEqual(prandtl_factors(3,2,1,4,0),(1,1))
        self.assertGreater(prandtl_factors(8,2,1,4,.4)[0],prandtl_factors(2,2,1,4,.4)[0])

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError):
            prandtl_factors(2,.5,1,4,.2)
        with self.assertRaises(ValueError):
            sizing_settings({'sizing':{'loss_model':'ducted'}})

    def test_bemt_couples_losses_at_static_and_forward_points(self):
        case=load_case(ROOT/'input_esempio.json')
        design=initial_design(case,'NACA4412',2)
        design.update(rpm=15000,pitch_deg=[22,15.7,9.4,4])
        polar=PolarGrid.load(ROOT/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')
        for point in case['operating_points']:
            case['sizing']['loss_model']='none'
            baseline=solve(case,design,point,polar)
            self.assertEqual(baseline['loss_factor_min'],1)
            case['sizing']['loss_model']='prandtl_free_rotor'
            result=solve(case,design,point,polar)
            fine=solve(case,design,point,polar,stations=64)
            self.assertLess(result['thrust_rotor_N'],baseline['thrust_rotor_N'])
            self.assertLess(result['momentum_residual_max'],1e-5)
            self.assertLess(fine['momentum_residual_max'],1e-5)
            self.assertLess(abs(fine['thrust_rotor_N']/result['thrust_rotor_N']-1),.02)
            for row in result['local']:
                self.assertGreater(row['F'],0)
                self.assertLessEqual(row['F'],1)


if __name__=='__main__':
    unittest.main()
