import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from ventola_designer.verification import finalize_attempt
from ventola_designer.polars import PolarDomainError


class FinalVerificationTests(unittest.TestCase):
    def setUp(self):
        self.case={'operating_points':[{}]}
        self.attempt={'accepted':True,'status':'converged_feasible','design':{},
                      'cases':[{'thrust_rotor_N':1.}], 'energy_J':100.}

    def test_success_uses_final_energy_without_mutating_prior_results(self):
        original=copy.deepcopy(self.attempt)
        evaluate=Mock(return_value=(101.,[.1],[{'thrust_rotor_N':1.001,'local':[1]}]))
        result=finalize_attempt(self.case,self.attempt,None,evaluate)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['energy_J'],101.)
        self.assertEqual(result['verification_grid_energy_J'],100.)
        self.assertNotIn('local',result['cases'][0])
        self.assertEqual(self.attempt,original)
        self.assertEqual(evaluate.call_args.kwargs['stations'],128)

    def test_failed_grid_constraints_and_nonfinite_values_reject_candidate(self):
        for energy,cons,thrust in ((100.,[-.1],1.),(100.,[.1],1.1),(float('nan'),[.1],1.),(100.,[float('nan')],1.)):
            with self.subTest(energy=energy,cons=cons,thrust=thrust):
                result=finalize_attempt(self.case,self.attempt,None,
                    Mock(return_value=(energy,cons,[{'thrust_rotor_N':thrust}])))
                self.assertFalse(result['accepted'])
                self.assertIn('verification_error',result)

    def test_domain_failure_and_incomplete_points_are_rejected(self):
        for evaluate in (Mock(side_effect=PolarDomainError('fuori polare')),
                         Mock(return_value=(100.,[.1],[]))):
            self.assertFalse(finalize_attempt(self.case,self.attempt,None,evaluate)['accepted'])

    def test_previous_failure_is_never_promoted(self):
        self.attempt['accepted']=False
        evaluate=Mock()
        result=finalize_attempt(self.case,self.attempt,None,evaluate)
        self.assertFalse(result['accepted'])
        evaluate.assert_not_called()

    def test_fixed_design_passes_full_pipeline_without_optimization_search(self):
        from ventola_designer.config import load_case
        from ventola_designer.geometry import initial_design
        from ventola_designer.polars import PolarGrid
        from ventola_designer.optimizer import evaluate, encode, _optimize_start
        root=Path(__file__).resolve().parents[1]
        case=load_case(root/'input_esempio.json')
        design=initial_design(case,'NACA4412',2)
        design.update(pitch_deg=[22,15.7,9.4,4],rpm_by_point=[15000,15000])
        polar=PolarGrid.load(root/'ventola_designer/airfoils/polars_neuralfoil/NACA4412.json')
        energy,_,_=evaluate(case,design,polar)
        result=SimpleNamespace(x=encode(case,design,design['rpm_by_point']),success=True,message='test fixed design',nit=0)
        with patch('ventola_designer.optimizer.minimize',return_value=result):
            verified=_optimize_start(case,'NACA4412',2,polar,energy,design,1)
        self.assertTrue(verified['accepted'])
        self.assertEqual(verified['final_verification']['status'],'passed')

    def test_cli_writes_failure_report_but_no_geometry(self):
        from ventola_designer.optimizer import main
        root=Path(__file__).resolve().parents[1]
        failed={'profile':'NACA4412','blades':2,'accepted':False,
                'status':'final_verification_failed','verification_error':'Vincoli violati'}
        with tempfile.TemporaryDirectory() as tmp, \
             patch('ventola_designer.optimizer.optimize_pair',return_value=failed), \
             patch('ventola_designer.optimizer.export_geometry') as export, \
             contextlib.redirect_stdout(io.StringIO()):
            out=Path(tmp)/'result'
            code=main(['--input',str(root/'input_esempio.json'),'--profiles','NACA4412',
                       '--blades','2','--output',str(out)])
            report=json.loads((out/'00_sintesi'/'report.json').read_text())
            self.assertEqual(code,2)
            self.assertIsNone(report['best'])
            self.assertTrue(report['complete'])
            self.assertTrue((out/'00_sintesi'/'RISULTATO.md').exists())
            export.assert_not_called()

    def test_broken_pool_falls_back_to_sequential_pairs(self):
        from concurrent.futures import Future
        from concurrent.futures.process import BrokenProcessPool
        from ventola_designer.optimizer import main

        class BrokenPool:                    # every worker died (e.g. paging file full)
            def __init__(self,*a,**k): pass
            def submit(self,*a,**k):
                f=Future(); f.set_exception(BrokenProcessPool('worker died')); return f
            def shutdown(self,*a,**k): pass

        root=Path(__file__).resolve().parents[1]
        def failed(case,profile,blades,maxiter=None):
            return {'profile':profile,'blades':blades,'accepted':False,
                    'status':'final_verification_failed','verification_error':'Vincoli violati'}
        with tempfile.TemporaryDirectory() as tmp, \
             patch('ventola_designer.optimizer.ProcessPoolExecutor',BrokenPool), \
             patch('ventola_designer.optimizer.optimize_pair',side_effect=failed) as opt, \
             patch('ventola_designer.optimizer.export_geometry'), \
             contextlib.redirect_stdout(io.StringIO()) as log:
            out=Path(tmp)/'result'
            code=main(['--input',str(root/'input_esempio.json'),'--profiles','NACA4412',
                       '--blades','2','3','4','--output',str(out),'--jobs','3'])
            report=json.loads((out/'00_sintesi'/'report.json').read_text())
        self.assertEqual(code,2)
        self.assertEqual(opt.call_count,3)
        self.assertEqual([r['blades'] for r in report['runs']],[2,3,4])
        self.assertTrue(report['complete'])
        self.assertIn('in sequenza',log.getvalue())

    def test_default_jobs_is_bounded(self):
        from ventola_designer.optimizer import default_jobs, MAX_DEFAULT_JOBS
        self.assertTrue(1<=default_jobs()<=MAX_DEFAULT_JOBS)


if __name__=='__main__':
    unittest.main()
