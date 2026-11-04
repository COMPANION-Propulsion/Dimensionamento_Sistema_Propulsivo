import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ventola_designer.venturi_input import latest_venturi_result
from ventola_designer.config import load_case

ROOT = Path(__file__).resolve().parents[1]


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
            with patch('ventola_designer.venturi_input.latest_venturi_result', return_value=export):
                data = load_case(ROOT/'input_venturi.json')
                self.assertEqual(data['rotor']['outer_diameter_m'], .06)
                self.assertEqual(data['operating_points'][0]['minimum_total_pressure_rise_Pa'], 100.)
                self.assertEqual(data['operating_points'][0]['venturi_source']['selection'],
                                 'latest_export_by_modification_time')
                export.write_text('{')
                with self.assertRaises(ValueError):
                    load_case(ROOT/'input_venturi.json')
