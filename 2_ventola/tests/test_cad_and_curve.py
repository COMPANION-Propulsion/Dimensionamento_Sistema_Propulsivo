import math
from pathlib import Path
import tempfile
import unittest

from ventola_designer.config import load_case
from ventola_designer.geometry import initial_design
from ventola_designer.polars import PolarGrid
from ventola_designer.power_curve import operating_point, power_curve
from ventola_designer.pressure_bemt import solve_pressure

ROOT = Path(__file__).resolve().parents[1]


class CadAndCurveTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(ROOT/'input_esempio.json')
        self.case.update(design_mode='pressure_flow', velocity_reference='full_disk_flow')
        self.point = dict(name='pressure', volume_flow_m3_s=.03,
            minimum_total_pressure_rise_Pa=1., duration_s=10.,
            full_disk_velocity_m_s=.03/(math.pi*.1**2/4))
        self.case['operating_points'] = [self.point]
        self.design = initial_design(self.case, 'NACA4412', 3)
        self.design.update(rpm=15000, rpm_by_point=[15000], pitch_deg=[25, 20, 15, 10])
        self.polar = PolarGrid.load(ROOT/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')

    def _design_point(self):
        r = solve_pressure(self.case, self.design, self.point, self.polar, stations=64)
        return {k: v for k, v in r.items() if k != 'local'}

    def test_cad_solids_are_valid_closed_and_mirrored(self):
        from ventola_designer import cad_export
        if cad_export.cq is None:
            self.skipTest('cadquery non installato')
        with tempfile.TemporaryDirectory() as directory:
            info = cad_export.export_cad(directory, self.case, self.design)
            for name in ('pala', 'ventola_A', 'ventola_B_speculare'):
                self.assertTrue(info['files'][name]['valid'], name)
                self.assertIn(info['files'][name]['stl_closed'], (True, None), name)
                self.assertTrue((Path(directory)/f'{name}.step').stat().st_size > 0)
            a, b = (info['files'][n]['volume_mm3'] for n in ('ventola_A', 'ventola_B_speculare'))
            self.assertAlmostEqual(a, b, delta=1e-6*a)
            self.assertAlmostEqual(info['diameter_cad_mm'], 100 - 2*0.5)
            self.assertTrue(info['axis'].startswith('X'))

    def test_operating_point_at_design_speed_is_the_design_point(self):
        d = self._design_point()
        duct = dict(dp=d['axial_total_pressure_rise_Pa'], Q=.03)
        q, dp, _ = operating_point(self.case, self.design, self.point, self.polar, duct,
                                   15000, .03, 64)
        self.assertAlmostEqual(q, .03, delta=1e-6)
        self.assertAlmostEqual(dp, duct['dp'], delta=1e-6*duct['dp'])

    def test_stator_recovers_part_of_the_swirl(self):
        free = self._design_point()
        self.case['stator'] = dict(swirl_recovery=0.8)
        with_stator = self._design_point()
        self.case.pop('stator')
        gain = with_stator['axial_total_pressure_rise_Pa'] - free['axial_total_pressure_rise_Pa']
        swirl = free['swirl_power_W']/free['volume_flow_m3_s']
        self.assertAlmostEqual(gain, 0.8*swirl, delta=1e-9*swirl)
        self.assertEqual(with_stator['shaft_power_W'], free['shaft_power_W'])

    def test_power_curve_from_zero_to_p_max(self):
        d = self._design_point()
        report = dict(input_case=self.case, best=dict(design=self.design, cases=[d]))
        venturi = dict(ventola=dict(dp_disk_Pa=d['axial_total_pressure_rise_Pa'], portata_m3_s=.03),
                       spinta=dict(calcolata_N=1.0), numerica=dict(esponente_T_dp=1.0))
        curve = power_curve(report, venturi, p_max=1.5*d['shaft_power_W'], n_points=12)
        rows = curve['righe']
        self.assertEqual(rows[0]['potenza_albero_W'], 0.0)
        self.assertEqual(rows[0]['spinta_ugello_N'], 0.0)
        P = [r['potenza_albero_W'] for r in rows]
        T = [r['spinta_ugello_N'] for r in rows]
        self.assertEqual(P, sorted(P))
        self.assertEqual(T, sorted(T))
        self.assertAlmostEqual(P[-1], 1.5*d['shaft_power_W'], delta=1e-9)
        # sopra il progetto la spinta supera quella di progetto
        self.assertGreater(T[-1], 1.0)


if __name__ == '__main__':
    unittest.main()
