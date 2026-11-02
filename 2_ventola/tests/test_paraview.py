import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from ventola_designer.config import load_case
from ventola_designer.geometry import initial_design
from ventola_designer.paraview import export_paraview_results


ROOT = Path(__file__).resolve().parents[1]


class ParaViewExportTests(unittest.TestCase):
    def test_exports_full_geometry_and_a_radial_dataset_per_operating_point(self):
        case = load_case(ROOT / 'input_esempio.json')
        design = initial_design(case, 'NACA4412', 2)
        design.update(pitch_deg=[22, 15.7, 9.4, 4], rpm_by_point=[15000, 15000])
        run = {'profile': 'NACA4412', 'blades': 2, 'design': design,
               'accepted': True, 'status': 'converged_final_verified'}
        with tempfile.TemporaryDirectory() as temporary:
            manifest = export_paraview_results(temporary, case, [run], run)
            folder = Path(temporary) / 'paraview'
            self.assertEqual(len(manifest['datasets']), len(case['operating_points']))
            self.assertTrue((folder / 'fan_geometry.vtp').exists())
            self.assertTrue((folder / 'results.pvd').exists())
            for dataset in manifest['datasets']:
                root = ET.parse(folder / dataset['file']).getroot()
                names = {node.attrib.get('Name') for node in root.iter('DataArray')}
                self.assertTrue({'alpha_deg', 'Re', 'Mach', 'induced_axial_m_s'} <= names)
            stored = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            self.assertIn('non volume CFD', stored['field_description'])


if __name__ == '__main__':
    unittest.main()
