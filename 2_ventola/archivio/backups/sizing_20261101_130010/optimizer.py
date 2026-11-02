"""Ottimizzazione locale SLSQP del modello rotorico preliminare.

Variabili normalizzate: mozzo, quattro corde, quattro calettamenti, rpm per punto.
Profilo e numero intero di pale sono enumerati esternamente. Nessuna CFD.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from .bemt import solve, ModelDomainError
from .config import load_case, load_catalog
from .geometry import initial_design, blade_sections, interpolate
from .polars import PolarGrid
from .export import export_geometry


def variable_bounds(case):
    d = case['rotor']['outer_diameter_m']
    return np.array([case['rotor']['hub_diameter_bounds_m']]
                    + [[.04*d, .22*d]]*4 + [[0.,45.]]*4
                    + [case['rotor']['shaft_speed_bounds_rpm']]*len(case['operating_points']))


def decode(case, profile, blades, x):
    limits = variable_bounds(case)
    values = limits[:,0] + np.asarray(x)*(limits[:,1]-limits[:,0])
    design = initial_design(case, profile, blades)
    design.update(hub_diameter_m=float(values[0]), chord_m=values[1:5].tolist(),
                  pitch_deg=values[5:9].tolist(), rpm_by_point=values[9:].tolist(),
                  status='SLSQP_candidate', note='Geometria parametrica; integrita meccanica non verificata.')
    return design


def encode(case, design, rpm):
    limits = variable_bounds(case)
    values = np.array([design['hub_diameter_m'], *design['chord_m'],
                       *design['pitch_deg'], *rpm])
    return (values-limits[:,0])/(limits[:,1]-limits[:,0])


def evaluate(case, design, polar, stations=32):
    if len(design['rpm_by_point']) != len(case['operating_points']):
        raise ValueError('Richiesto un regime per ogni punto operativo.')
    results = [solve(case, {**design,'rpm':rpm}, point, polar, stations=stations)
               for point,rpm in zip(case['operating_points'],design['rpm_by_point'])]
    energy = sum(r['shaft_power_W']*p['duration_s'] for r,p in zip(results,case['operating_points']))
    # Margine numerico 0.2% sulla spinta; non margine di sicurezza fisico.
    constraints = [r['thrust_rotor_N']/(p['minimum_rotor_thrust_N']*1.002)-1
                   for r,p in zip(results,case['operating_points'])]
    constraints += [.3-r['Mach_max'] for r in results]
    # Solidita locale B*c/(2*pi*r), controllo su griglia indipendente dai pannelli BEMT.
    hub, tip = design['hub_diameter_m']/2, design['outer_diameter_m']/2
    for s in np.linspace(0,1,65):
        chord = interpolate(design['span_nodes'],design['chord_m'],float(s))
        constraints.append(.8-design['blade_count']*chord/(2*math.pi*(hub+s*(tip-hub))))
    return energy, np.asarray(constraints), results


def optimize_pair(case, profile, blades, maxiter=80):
    polar = PolarGrid.load(Path(__file__).parent/'airfoils'/'polars_neuralfoil'/f'{profile}.json')
    seeds = []
    limits = case['rotor']['shaft_speed_bounds_rpm']
    # Ricerca iniziale riproducibile; assenza di semi non prova l'infattibilita.
    for rpm in sorted(set([float(np.clip(r, *limits)) for r in (10000,15000,20000,25000)])):
        for root,tip in ((22,4),(18,16),(30,12)):
            design = initial_design(case,profile,blades)
            design['pitch_deg'] = [root+(tip-root)*s for s in design['span_nodes']]
            design['rpm_by_point'] = [rpm]*len(case['operating_points'])
            try:
                energy, constraints, _ = evaluate(case,design,polar)
                if min(constraints) >= 0:
                    seeds.append((energy,design))
            except ModelDomainError:
                pass
    if not seeds:
        return {'profile':profile,'blades':blades,'status':'no_feasible_seed_found','accepted':False}
    seed_energy, seed = min(seeds,key=lambda item:item[0])
    x0 = encode(case,seed,seed['rpm_by_point'])
    cache = {}
    rejected = 0
    ncons = 2*len(case['operating_points'])+65
    def sample(x):
        nonlocal rejected
        key = tuple(x)
        if key not in cache:
            try:
                e,c,r = evaluate(case,decode(case,profile,blades,x),polar)
                cache[key] = (e/seed_energy,c,r)
            except ModelDomainError:
                rejected += 1
                # Punto non utilizzabile; nessun coefficiente viene estrapolato.
                cache[key] = (1e3+float(np.sum((x-x0)**2)),np.full(ncons,-1.),None)
        return cache[key]
    result = minimize(lambda x:sample(x)[0],x0,method='SLSQP',bounds=[(0.,1.)]*len(x0),
                      constraints=[{'type':'ineq','fun':lambda x:sample(x)[1]}],
                      options={'maxiter':maxiter,'ftol':1e-6,'eps':1e-5})
    design = decode(case,profile,blades,result.x)
    report = {'profile':profile,'blades':blades,'accepted':False,'status':'not_accepted',
              'solver_success':bool(result.success),'solver_message':str(result.message),
              'iterations':int(result.nit),'invalid_evaluations':rejected,
              'seed_energy_J':seed_energy,'design':design}
    try:
        energy, cons, cases = evaluate(case,design,polar)
        fine_energy, fine_cons, fine_cases = evaluate(case,design,polar,stations=64)
        changes = [abs(f['thrust_rotor_N']/c['thrust_rotor_N']-1) for c,f in zip(cases,fine_cases)]
        bounds_ok = bool(np.all(result.x >= -1e-9) and np.all(result.x <= 1+1e-9))
        accepted = bool(result.success and bounds_ok and min(cons)>=-1e-6
                        and min(fine_cons)>=-1e-6 and max(changes)<.01
                        and energy<=seed_energy*(1+1e-6))
        report.update(accepted=accepted,status='converged_feasible' if accepted else 'not_accepted',
                      energy_J=fine_energy,coarse_energy_J=energy,
                      min_constraint=float(min(fine_cons)),thrust_refinement_changes=changes,
                      cases=[{k:v for k,v in r.items() if k!='local'} for r in fine_cases],
                      polar_coordinates_sha256=polar.data['coordinates_sha256'])
    except ModelDomainError as exc:
        report['verification_error'] = str(exc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('input_esempio.json'))
    parser.add_argument('--profiles',nargs='+')
    parser.add_argument('--blades',nargs='+',type=int)
    parser.add_argument('--maxiter',type=int,default=80)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    case = load_case(args.input)
    profiles = args.profiles or case['rotor']['airfoil_candidates']
    blades = args.blades or case['rotor']['blade_count_candidates']
    if not set(profiles)<=set(case['rotor']['airfoil_candidates']) or not set(blades)<=set(case['rotor']['blade_count_candidates']):
        parser.error('Profili e pale devono appartenere ai candidati del caso.')
    if args.maxiter < 1:
        parser.error('--maxiter deve essere positivo.')
    out = args.output or Path('ventola_output')/datetime.now().strftime('slsqp_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True,exist_ok=False)
    report = {'method':'SLSQP_local_discrete_enumeration','input_case':case,'runs':[],
              'scope':{'profiles':profiles,'blade_counts':blades},'best':None,
              'settings':{'chord_over_D_bounds':[.04,.22],'pitch_deg_bounds':[0,45],
                          'max_solidity':.8,'max_Mach':.3,'thrust_numerical_margin':.002,
                          'stations_optimization':32,'stations_verification':64,'maxiter':args.maxiter},
              'limitations':['Rotor-only preliminary BEMT; no duct or tip/hub losses.',
                             'Velocity input interpreted as far-upstream axial speed.',
                             'Numerical polars, no experimental validation or structural verification.',
                             'Local optimization from one selected feasible seed per pair; global optimum not guaranteed.',
                             'Chord, pitch, solidity and Mach bounds are provisional project choices.',
                             'Invalid BEMT points rejected with discontinuous penalty; may obstruct convergence.']}
    for profile in profiles:
        for b in blades:
            print(f'SLSQP {profile}, {b} pale...',flush=True)
            run = optimize_pair(case,profile,b,args.maxiter)
            report['runs'].append(run)
            accepted = [r for r in report['runs'] if r['accepted']]
            report['best'] = min(accepted,key=lambda r:r['energy_J']) if accepted else None
            (out/'optimization.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
            print(f"  {run['status']}: {run.get('energy_J')} J",flush=True)
    if report['best']:
        best = report['best']
        best['design']['status'] = 'SLSQP_converged_feasible_preliminary'
        (out/'optimization.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        export_geometry(out,case,best['design'],blade_sections(best['design']),load_catalog())
        # L'export geometrico ha metadati per il vecchio seme: sostituirli col report effettivo.
        (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        svg = (out/'preview.svg').read_text(encoding='utf-8').replace('geometria iniziale','geometria SLSQP').replace('Non ottimizzata — spinta e potenza ancora da calcolare','Ottimizzazione locale BEMT — modello preliminare')
        (out/'preview.svg').write_text(svg,encoding='utf-8')
        obj = out/'blade_surface.obj'
        obj.write_text(obj.read_text(encoding='utf-8').replace('Initial blade surface','SLSQP blade surface'),encoding='utf-8')
    print(f'Report: {out.resolve()}')
    return 0 if report['best'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
