import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ventola_designer.venturi_input import latest_venturi_result
from ventola_designer.config import load_case

ROOT = Path(__file__).resolve().parents[1]
# Input with "venturi_result": "auto" (the file input_venturi.json of the past)
AUTO_INPUT = {'description': "Importazione automatica dell'export Venturi piu recente in ../risultati. Aria, durata e limiti sono impostazioni modificabili.", 'design_mode': 'pressure_flow', 'velocity_reference': 'full_disk_flow', 'air': {'temperature_K': 293.15, 'static_pressure_Pa': 101325.0, 'relative_humidity': None}, 'rotor': {'hub_diameter_bounds_m': [0.012, 0.024], 'blade_count_candidates': [2, 3, 4, 5, 6, 7, 8], 'airfoil_candidates': ['NACA0012', 'NACA2412', 'NACA4412', 'NACA4415'], 'profile_constant_along_span': True, 'shaft_speed_bounds_rpm': [5000.0, 30000.0]}, 'operating_points': [{'name': 'venturi', 'venturi_result': 'auto', 'duration_s': 1.0}], 'sizing': {'loss_model': 'none', 'pressure_numerical_margin': 0.002, 'max_pressure_grid_change': 0.01}}


class AutoVenturiTests(unittest.TestCase):
    def test_latest_export_ignores_intermediate_and_other_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root/'old/2_venturi/00_sintesi/risultati.json'
            new = root/'new/2_venturi/00_sintesi/risultati.json'
            unrelated = root/'new/1_spinta/00_sintesi/risultati.json'
            for path in (old, new, unrelated):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{}')
            os.utime(old, ns=(100,100))
            os.utime(new, ns=(200,200))
            self.assertEqual(latest_venturi_result(root), new.resolve())

    def test_missing_exports_have_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Completare il calcolo Venturi'):
                latest_venturi_result(tmp)

    def test_auto_uses_current_export_and_rejects_corrupt_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export = root/'source.json'
            export.write_text(json.dumps({'ventola':{
                'D_ventola_m':.06, 'dp_disk_Pa':100., 'portata_m3_s':.01,
                'V_disco_m_s':.01/(3.141592653589793*.06**2/4), 'densita_kg_m3':1.204}}))
            case_file = root/'input_auto.json'
            case_file.write_text(json.dumps(AUTO_INPUT))
            with patch('ventola_designer.venturi_input.latest_venturi_result', return_value=export):
                data = load_case(case_file)
                self.assertEqual(data['rotor']['outer_diameter_m'], .06)
                self.assertEqual(data['operating_points'][0]['minimum_total_pressure_rise_Pa'], 100.)
                self.assertEqual(data['operating_points'][0]['venturi_source']['selection'],
                                 'latest_export_by_modification_time')
                export.write_text('{')
                with self.assertRaises(ValueError):
                    load_case(case_file)
