import unittest
from pathlib import Path
from ventola_designer.config import load_case
from ventola_designer.reporting import render_report


class ReportingTests(unittest.TestCase):
    def test_no_solution_is_not_physical_infeasibility(self):
        case = load_case(Path(__file__).resolve().parents[1]/'input_esempio.json')
        text = render_report({'input_case':case,'best':None,'runs':[
            {'profile':'NACA4412','blades':2,'accepted':False,'status':'no_feasible_seed_found'}]})
        self.assertIn('non dimostra impossibilita fisica',text)
        self.assertNotIn('## Risultato',text)

    def test_margin_and_local_air_are_explicit(self):
        case = load_case(Path(__file__).resolve().parents[1]/'input_esempio.json')
        case['operating_points']=case['operating_points'][:1]
        case['operating_points'][0]['air']={'static_pressure_Pa':90000}
        best={'energy_J':123,'design':{'profile':'NACA4412','blade_count':2,
              'hub_diameter_m':.02,'span_nodes':[0,1],'chord_m':[.01,.02],'pitch_deg':[20,10]},
              'cases':[{'thrust_rotor_N':.7,'shaft_power_W':5,'torque_Nm':.01,'rpm':5000}]}
        text=render_report({'input_case':case,'best':best,'runs':[]})
        self.assertIn('0.100000',text)
        self.assertIn('90000',text)
        self.assertIn('minimo globale non garantito',text)
        best['cases']=[]
        with self.assertRaises(ValueError):
            render_report({'input_case':case,'best':best,'runs':[]})
