import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import contextlib
import io
import xml.etree.ElementTree as ET

from ventola_designer.config import load_case
from ventola_designer.geometry import initial_design
from ventola_designer.pressure_bemt import annular_velocity, solve_pressure
from ventola_designer.verification import finalize_attempt
from ventola_designer.optimizer import evaluate
from ventola_designer.polars import PolarGrid
from ventola_designer.reporting import render_report

ROOT = Path(__file__).resolve().parents[1]


class ConstantPolar:
    def __init__(self, drag=0.02):
        self.drag = drag
    def validate_profile(self, profile):
        pass
    def coefficients(self, alpha, reynolds, mach):
        return .6, self.drag, 1.


class PressureFlowTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(ROOT/'input_esempio.json')
        self.case.update(design_mode='pressure_flow', velocity_reference='full_disk_flow')
        self.point = dict(name='pressure', volume_flow_m3_s=.03,
            minimum_total_pressure_rise_Pa=1., duration_s=10.,
            full_disk_velocity_m_s=.03/(math.pi*.1**2/4))
        self.case['operating_points'] = [self.point]
        self.design = initial_design(self.case, 'NACA4412', 2)
        self.design.update(rpm=15000, rpm_by_point=[15000], pitch_deg=[25,20,15,10])

    def test_hub_reduces_area_but_not_flow(self):
        area, velocity = annular_velocity(.1, .06, .02)
        self.assertAlmostEqual(area, math.pi*.0016)
        self.assertAlmostEqual(area*velocity, .02)
        self.assertGreater(velocity, annular_velocity(.1, .02, .02)[1])
        with self.assertRaises(ValueError):
            annular_velocity(.1, .1, .02)

    def test_energy_and_angular_momentum_balance(self):
        result = solve_pressure(self.case, self.design, self.point, ConstantPolar())
        self.assertAlmostEqual(result['volume_flow_m3_s'], .03)
        self.assertAlmostEqual(result['axial_blade_velocity_m_s']*result['annular_area_m2'], .03)
        self.assertAlmostEqual(result['shaft_power_W'],
            .03*result['total_pressure_rise_Pa']+result['profile_loss_power_W'], places=5)
        self.assertGreater(result['total_pressure_rise_Pa'], result['static_pressure_rise_Pa'])
        self.assertLess(result['momentum_residual_max'], 1e-5)
        for row in result['local']:
            expected = 2*math.pi*row['r_m']**2*result['density_kg_m3']*result['axial_blade_velocity_m_s']*row['exit_swirl_m_s']
            self.assertAlmostEqual(row['dtorque_dr_Nm_m'], expected, places=5)

    def test_zero_drag_limit_has_unit_total_efficiency(self):
        result = solve_pressure(self.case, self.design, self.point, ConstantPolar(drag=0.))
        self.assertAlmostEqual(result['total_pressure_efficiency'], 1., places=6)
        self.assertEqual(result['profile_loss_power_W'], 0.)

    def test_real_polar_fixed_geometry_and_pressure_constraint(self):
        polar = PolarGrid.load(ROOT/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')
        energy, constraints, results = evaluate(self.case, self.design, polar)
        dp = results[0]['total_pressure_rise_Pa']
        self.assertAlmostEqual(constraints[0], dp/1.002-1)
        self.point['minimum_total_pressure_rise_Pa'] = dp*2
        changed_energy, changed, _ = evaluate(self.case, self.design, polar)
        self.assertLess(changed[0], 0)
        self.assertEqual(energy, changed_energy)
        report = render_report(dict(input_case=self.case, best=dict(design=self.design,
            cases=results, energy_J=energy), runs=[]))
        self.assertIn('Delta p totale', report)
        self.assertIn('Potenza albero', report)

    def test_final_grid_rejects_pressure_change_with_same_thrust(self):
        attempt = dict(accepted=True, design=self.design, energy_J=10.,
                       cases=[dict(thrust_rotor_N=1., total_pressure_rise_Pa=100.)])
        evaluator = Mock(return_value=(10., [.1],
            [dict(thrust_rotor_N=1., total_pressure_rise_Pa=110.)]))
        result = finalize_attempt(self.case, attempt, None, evaluator)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['final_verification']['metric'], 'total_pressure_rise_Pa')

    def test_import_and_consistency_checks(self):
        data = copy.deepcopy(self.case)
        data['rotor'].pop('outer_diameter_m')
        data['operating_points'] = [dict(name='imported', venturi_result='result.json', duration_s=5)]
        source = dict(ventola=dict(D_ventola_m=.1, dp_disk_Pa=100., portata_m3_s=.03,
            V_disco_m_s=.03/(math.pi*.1**2/4), densita_kg_m3=1.204))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'case.json').write_text(json.dumps(data))
            (folder/'result.json').write_text(json.dumps(source))
            imported = load_case(folder/'case.json')
            self.assertEqual(imported['rotor']['outer_diameter_m'], .1)
            point = imported['operating_points'][0]
            self.assertEqual(point['volume_flow_m3_s'], .03)
            self.assertEqual(point['minimum_total_pressure_rise_Pa'], 100.)
            self.assertEqual(len(point['venturi_source']['sha256']), 64)
            source['ventola']['V_disco_m_s'] *= 2
            (folder/'result.json').write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, 'non coerenti'):
                load_case(folder/'case.json')

    def test_prandtl_and_ambiguous_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'case.json'
            for edit in ('loss', 'thrust'):
                case = copy.deepcopy(self.case)
                if edit == 'loss':
                    case['sizing']['loss_model'] = 'prandtl_free_rotor'
                else:
                    case['operating_points'][0]['minimum_rotor_thrust_N'] = 1.
                path.write_text(json.dumps(case))
                with self.assertRaises(ValueError):
                    load_case(path)

    def test_cli_pressure_reports_and_paraview_without_optimization_search(self):
        from ventola_designer.optimizer import main
        polar = PolarGrid.load(ROOT/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')
        energy, _, cases = evaluate(self.case, self.design, polar, stations=128)
        run = dict(profile='NACA4412', blades=2, accepted=True, status='fixed_design_test',
                   design=self.design, energy_J=energy, cases=cases)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder/'case.json'
            path.write_text(json.dumps(self.case))
            with patch('ventola_designer.optimizer.optimize_pair', return_value=run), contextlib.redirect_stdout(io.StringIO()):
                code = main(['--input',str(path),'--profiles','NACA4412','--blades','2',
                             '--output',str(folder/'output')])
            self.assertEqual(code, 0)
            saved = json.loads((folder/'output/report.json').read_text())
            self.assertEqual(saved['input_case']['design_mode'], 'pressure_flow')
            self.assertAlmostEqual(saved['best']['cases'][0]['volume_flow_m3_s'], .03)
            datasets = saved['paraview']['datasets']
            self.assertEqual(len(datasets), 1)
            xml = ET.parse(folder/'output/paraview'/datasets[0]['file'])
            names = {node.get('Name') for node in xml.iter('DataArray')}
            self.assertIn('total_pressure_rise_Pa', names)
            self.assertIn('volume_flow_m3_s', names)


if __name__ == '__main__':
    unittest.main()
