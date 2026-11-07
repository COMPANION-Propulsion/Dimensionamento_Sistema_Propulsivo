"""Ottimizzazione locale SLSQP del modello rotorico preliminare.

Variabili normalizzate: mozzo, n corde, n calettamenti (n = nodi della pala), rpm per punto.
Profilo e numero intero di pale sono enumerati esternamente. Nessuna CFD.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import numpy as np
from scipy.optimize import minimize
from .bemt import solve, ModelDomainError
from .config import load_case, load_catalog
from .geometry import initial_design, blade_sections, blade_nodes, interpolate
from .polars import PolarGrid
from .export import export_geometry
from .settings import sizing_settings
from .geometry_checks import screen_geometry
from .verification import finalize_attempt
from .paraview import export_paraview_results
from .duty import metric_key, target_key, margin_key, grid_limit_key


def variable_bounds(case):
    d = case['rotor']['outer_diameter_m']
    cfg = sizing_settings(case)
    n = len(blade_nodes(case['rotor']))
    return np.array([case['rotor']['hub_diameter_bounds_m']]
                    + [[v*d for v in cfg['chord_over_D_bounds']]]*n + [cfg['pitch_deg_bounds']]*n
                    + [case['rotor']['shaft_speed_bounds_rpm']]*len(case['operating_points']))


def decode(case, profile, blades, x):
    limits = variable_bounds(case)
    values = limits[:,0] + np.asarray(x)*(limits[:,1]-limits[:,0])
    design = initial_design(case, profile, blades)
    n = len(design['span_nodes'])
    design.update(hub_diameter_m=float(values[0]), chord_m=values[1:1+n].tolist(),
                  pitch_deg=values[1+n:1+2*n].tolist(), rpm_by_point=values[1+2*n:].tolist(),
                  status='SLSQP_candidate', note='Geometria parametrica; integrita meccanica non verificata.')
    return design


def encode(case, design, rpm):
    limits = variable_bounds(case)
    values = np.array([design['hub_diameter_m'], *design['chord_m'],
                       *design['pitch_deg'], *rpm])
    return (values-limits[:,0])/(limits[:,1]-limits[:,0])


def evaluate(case, design, polar, stations=None):
    cfg = sizing_settings(case)
    stations = cfg['stations_optimization'] if stations is None else stations
    geometry_count = cfg['geometry_stations'] if stations == cfg['stations_optimization'] else 2*cfg['geometry_stations']-1
    geometric_constraints, _ = screen_geometry(design,geometry_count,
        cfg['minimum_section_thickness_m'],cfg['minimum_circumferential_gap_m'])
    if len(design['rpm_by_point']) != len(case['operating_points']):
        raise ValueError('Richiesto un regime per ogni punto operativo.')
    results = [solve(case, {**design,'rpm':rpm}, point, polar, stations=stations)
               for point,rpm in zip(case['operating_points'],design['rpm_by_point'])]
    energy = sum(r['shaft_power_W']*p['duration_s'] for r,p in zip(results,case['operating_points']))
    # Margine numerico configurabile; non margine di sicurezza fisico.
    constraints = [r[metric_key(case)]/(p[target_key(case)]*(1+cfg[margin_key(case)]))-1
                   for r,p in zip(results,case['operating_points'])]
    constraints += [cfg['max_Mach']-r['Mach_max'] for r in results]
    # Solidita locale B*c/(2*pi*r), controllo su griglia indipendente dai pannelli BEMT.
    hub, tip = design['hub_diameter_m']/2, design['outer_diameter_m']/2
    for s in np.linspace(0,1,cfg['solidity_stations']):
        chord = interpolate(design['span_nodes'],design['chord_m'],float(s))
        constraints.append(cfg['max_solidity']-design['blade_count']*chord/(2*math.pi*(hub+s*(tip-hub))))
    required = cfg['minimum_rotor_stall_margin_deg']
    if required is not None:
        for result in results:
            critical = result['rotor_stall_critical']
            if critical is None:
                raise ModelDomainError('Margine di stallo del rotore indeterminato.')
            constraints.append(critical['rotor_stall_margin_deg'] - required)
    constraints.extend(geometric_constraints)
    return energy, np.asarray(constraints), results


def seed_designs(case, profile, blades):
    cfg = sizing_settings(case)
    rng = np.random.default_rng(cfg['random_seed'])
    nodes = blade_nodes(case['rotor'])
    n = len(nodes)
    size = 1+2*n+len(case['operating_points'])
    seed_s = [0.0, 0.35, 0.7, 1.0]
    for i in range(cfg['seed_samples']):
        x = rng.uniform(.05,.95,size)
        if i<8:
            x[0]=.5
            x[1:1+n]=.5 if i<4 else .75
            pattern = [.65,.5,.35,.25] if i<4 else [.5,.4,.3,.2]
            x[1+n:1+2*n]=[interpolate(seed_s, pattern, s) for s in nodes]
            x[1+2*n:]=(.2,.4,.6,.8)[i%4]
        else:
            x[1+n:1+2*n]=np.sort(x[1+n:1+2*n])[::-1]
        yield decode(case,profile,blades,x)


def optimize_pair(case, profile, blades, maxiter=None):
    cfg = sizing_settings(case)
    polar = PolarGrid.load(Path(__file__).parent/'airfoils'/'polars_neuralfoil'/f'{profile}.json')
    seeds = []
    errors = {}
    for design in seed_designs(case,profile,blades):
        try:
            energy, constraints, _ = evaluate(case,design,polar)
            if min(constraints) >= 0:
                seeds.append((energy,design))
        except ModelDomainError as exc:
            reason = str(exc)
            errors[reason] = errors.get(reason,0)+1
    if not seeds:
        return {'profile':profile,'blades':blades,'status':'no_feasible_seed_found','accepted':False,
                'seed_errors':errors,'seeds_tested':cfg['seed_samples'],'attempts':[]}
    attempts = [_optimize_start(case,profile,blades,polar,energy,seed,
                                cfg['maxiter'] if maxiter is None else maxiter)
                for energy,seed in sorted(seeds,key=lambda item:item[0])[:cfg['starts']]]
    feasible = [a for a in attempts if a['accepted']]
    best = min(feasible,key=lambda a:a['energy_J']) if feasible else attempts[0]
    return {**best,'attempts':attempts,'starts_executed':len(attempts),
            'seeds_feasible':len(seeds),'seeds_tested':cfg['seed_samples'],'seed_errors':errors}


def _optimize_start(case, profile, blades, polar, seed_energy, seed, maxiter):
    cfg = sizing_settings(case)
    x0 = encode(case,seed,seed['rpm_by_point'])
    cache = {}
    rejected = 0
    ncons = 2*len(case['operating_points'])+cfg['solidity_stations']+2*cfg['geometry_stations']
    if cfg['minimum_rotor_stall_margin_deg'] is not None:
        ncons += len(case['operating_points'])
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
                      options={'maxiter':maxiter,'ftol':cfg['ftol'],'eps':cfg['finite_difference_step']})
    design = decode(case,profile,blades,result.x)
    report = {'profile':profile,'blades':blades,'accepted':False,'status':'not_accepted',
              'solver_success':bool(result.success),'solver_message':str(result.message),
              'iterations':int(result.nit),'invalid_evaluations':rejected,
              'seed_energy_J':seed_energy,'design':design}
    try:
        energy, cons, cases = evaluate(case,design,polar)
        fine_energy, fine_cons, fine_cases = evaluate(case,design,polar,stations=cfg['stations_verification'])
        changes = [abs(f[metric_key(case)]/c[metric_key(case)]-1) for c,f in zip(cases,fine_cases)]
        bounds_ok = bool(np.all(result.x >= -1e-9) and np.all(result.x <= 1+1e-9))
        accepted = bool(result.success and bounds_ok and min(cons)>=-cfg['constraint_tolerance']
                        and min(fine_cons)>=-cfg['constraint_tolerance'] and max(changes)<cfg[grid_limit_key(case)]
                        and energy<=seed_energy*(1+1e-6))
        report.update(accepted=accepted,status='converged_feasible' if accepted else 'not_accepted',
                      geometry_screening=screen_geometry(design,2*cfg['geometry_stations']-1,
                          cfg['minimum_section_thickness_m'],cfg['minimum_circumferential_gap_m'])[1],
                      energy_J=fine_energy,coarse_energy_J=energy,
                      min_constraint=float(min(fine_cons)),refinement_metric=metric_key(case),
                      duty_refinement_changes=changes,
                      thrust_refinement_changes=[abs(f['thrust_rotor_N']/c['thrust_rotor_N']-1) for c,f in zip(cases,fine_cases)],
                      cases=[{k:v for k,v in r.items() if k!='local'} for r in fine_cases],
                      polar_coordinates_sha256=polar.data['coordinates_sha256'])
    except ModelDomainError as exc:
        report['verification_error'] = str(exc)
    return finalize_attempt(case,report,polar,evaluate)


def default_output_directory(case):
    """Salva nel caso Venturi comune a tutti i punti, se identificabile.

    Nel caso: risultati/<caso>/3_ventola/, riscritta a ogni esecuzione come
    2_venturi (il caso e gia identificato dal nome della cartella). Fuori da un
    caso: ventola_output/slsqp_<data_ora>/, una cartella nuova per esecuzione.
    """
    roots = set()
    points = case['operating_points']
    for point in points:
        source = point.get('venturi_source', {}).get('path')
        if not source:
            break
        path = Path(source).resolve()
        if (path.name != 'risultati.json' or path.parent.name != '00_sintesi'
                or path.parent.parent.name != '2_venturi'):
            break
        roots.add(path.parents[2])
    else:
        if points and len(roots) == 1:
            return next(iter(roots))/'3_ventola'
    return Path(__file__).resolve().parents[1]/'ventola_output'/datetime.now().strftime('slsqp_%Y%m%d_%H%M%S_%f')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True,
                        help='Input JSON della ventola; nella catena lo scrive run_sistema.py '
                             'in risultati/<caso>/input_ventola.json.')
    parser.add_argument('--profiles',nargs='+')
    parser.add_argument('--blades',nargs='+',type=int)
    parser.add_argument('--maxiter',type=int)
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--jobs',type=int,default=os.cpu_count() or 1,
                        help='Coppie profilo/pale ottimizzate in parallelo (default: tutti i core).')
    args = parser.parse_args(argv)
    try:
        case = load_case(args.input)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    profiles = args.profiles or case['rotor']['airfoil_candidates']
    blades = args.blades or case['rotor']['blade_count_candidates']
    if not set(profiles)<=set(case['rotor']['airfoil_candidates']) or not set(blades)<=set(case['rotor']['blade_count_candidates']):
        parser.error('Profili e pale devono appartenere ai candidati del caso.')
    if args.maxiter is not None and args.maxiter < 1:
        parser.error('--maxiter deve essere positivo.')
    if args.maxiter is not None:
        case['sizing']['maxiter'] = args.maxiter
    if args.validate_only:
        from .config import operating_air
        print(json.dumps({'status':'input_valid_no_optimization','settings':sizing_settings(case),
                          'velocity_reference':case['velocity_reference'],
                          'design_mode':case.get('design_mode','thrust'), 'rotor':case['rotor'],
                          'operating_points':[{**p,'air':operating_air(case,p)}
                                              for p in case['operating_points']]},indent=2))
        return 0
    for point in case['operating_points']:
        if 'venturi_source' in point:
            print(f"Input Venturi [{point['name']}]: {point['venturi_source']['path']}", flush=True)
    out = args.output or default_output_directory(case)
    if args.output is None and out.name == '3_ventola' and out.exists():
        shutil.rmtree(out)          # cartella del caso: nessun file di un'esecuzione precedente
    out.mkdir(parents=True,exist_ok=False)
    print(f'Cartella risultati: {out.resolve()}', flush=True)
    report = {'method':'SLSQP_local_discrete_enumeration','complete':False,'input_case':case,'runs':[],
              'scope':{'profiles':profiles,'blade_counts':blades},'best':None,
              'settings':sizing_settings(case),
              'limitations':['Rotor-only preliminary BEMT; duct not modeled. Tip/hub correction follows settings.loss_model; Prandtl option is for a free rotor only.',
                             'Velocity convention: '+case['velocity_reference']+'.',
                             'Numerical polars, no experimental validation or structural verification.',
                             'Local multistart optimization; global optimum not guaranteed.',
                             'Chord, pitch, solidity and Mach bounds are provisional project choices.',
                             'Invalid BEMT points rejected with discontinuous penalty; may obstruct convergence.']}
    # Le coppie profilo/pale sono indipendenti: un processo per coppia.
    pairs = [(profile, b) for profile in profiles for b in blades]
    order = {pair: i for i, pair in enumerate(pairs)}
    jobs = max(1, min(args.jobs, len(pairs)))
    print(f'SLSQP su {len(pairs)} coppie profilo/pale, {jobs} in parallelo', flush=True)

    def record(run):
        report['runs'].append(run)
        report['runs'].sort(key=lambda r: order[(r['profile'], r['blades'])])
        accepted = [r for r in report['runs'] if r['accepted']]
        report['best'] = min(accepted,key=lambda r:r['energy_J']) if accepted else None
        (out/'optimization.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        print(f"  {run['profile']}, {run['blades']} pale: {run['status']}: {run.get('energy_J')} J",flush=True)

    if jobs == 1:
        for profile, b in pairs:
            record(optimize_pair(case,profile,b,args.maxiter))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(optimize_pair,case,profile,b,args.maxiter) for profile, b in pairs]
            for future in as_completed(futures):
                record(future.result())
    report['complete']=True
    if report['best']:
        best = report['best']
        best['design']['status'] = 'SLSQP_final_verified_preliminary'
        (out/'optimization.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        export_geometry(out,case,best['design'],blade_sections(best['design']),load_catalog())
        from .cad_export import export_cad
        print('CAD della ventola (STEP e STL, versioni A e speculare)...', flush=True)
        try:
            report['cad'] = export_cad(out,case,best['design'])
        except Exception as exc:     # il dimensionamento resta valido anche senza CAD
            report['cad'] = {'errore': str(exc)}
            print(f'ERRORE CAD: {exc}', flush=True)
        # L'export geometrico ha metadati per il vecchio seme: sostituirli col report effettivo.
        (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        svg = (out/'preview.svg').read_text(encoding='utf-8').replace('geometria iniziale','geometria SLSQP').replace('Non ottimizzata — spinta e potenza ancora da calcolare','Ottimizzazione locale BEMT — modello preliminare')
        (out/'preview.svg').write_text(svg,encoding='utf-8')
    report['paraview'] = export_paraview_results(out, case, report['runs'], report['best'])
    from .reporting import render_report
    (out/'optimization.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    (out/'RISULTATO.md').write_text(render_report(report),encoding='utf-8')
    from .result_layout import organize_results
    organize_results(out)
    print(f'Report: {out.resolve()}')
    return 0 if report['best'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
