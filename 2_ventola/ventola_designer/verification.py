"""Accettazione finale dei tentativi; nessuna nuova ottimizzazione."""
from copy import deepcopy
import math
from .polars import PolarDomainError
from .settings import sizing_settings


def finalize_attempt(case, attempt, polar, evaluator):
    result=deepcopy(attempt)
    if not result['accepted']:
        result['final_verification']={'status':'not_run_prior_checks_failed'}
        return result
    cfg=sizing_settings(case)
    check={'status':'failed','stations':cfg['stations_final'],
           'reference_stations':cfg['stations_verification']}
    result['final_verification']=check
    result['accepted_before_final_verification']=True
    result['accepted']=False
    result['status']='final_verification_failed'
    try:
        energy, constraints, cases=evaluator(case,result['design'],polar,stations=cfg['stations_final'])
        reference=result['cases']
        n=len(case['operating_points'])
        if len(cases)!=n or len(reference)!=n or not len(constraints):
            raise PolarDomainError('Verifica finale incompleta.')
        if not math.isfinite(energy) or energy<=0 or any(not math.isfinite(float(c)) for c in constraints):
            raise PolarDomainError('Valori non finiti o energia non positiva nella verifica finale.')
        changes=[]
        for coarse,fine in zip(reference,cases):
            thrust=fine['thrust_rotor_N']
            if not math.isfinite(thrust) or thrust<=0 or coarse['thrust_rotor_N']<=0:
                raise PolarDomainError('Spinta non valida nella verifica finale.')
            changes.append(abs(thrust/coarse['thrust_rotor_N']-1))
        check.update(energy_J=float(energy),min_constraint=float(min(constraints)),
                     thrust_grid_change=changes)
        if min(constraints)<-cfg['constraint_tolerance']:
            raise PolarDomainError('Vincoli violati sulla griglia finale.')
        if max(changes)>=cfg['max_thrust_grid_change']:
            raise PolarDomainError('Sensibilita alla griglia finale superiore al limite.')
        result['verification_grid_energy_J']=result['energy_J']
        result['verification_grid_cases']=reference
        result.update(accepted=True,status='converged_final_verified',energy_J=float(energy),
                      min_constraint=float(min(constraints)),
                      cases=[{k:v for k,v in c.items() if k!='local'} for c in cases])
        check['status']='passed'
    except PolarDomainError as exc:
        result['verification_error']=str(exc)
        check['error']=str(exc)
    return result
