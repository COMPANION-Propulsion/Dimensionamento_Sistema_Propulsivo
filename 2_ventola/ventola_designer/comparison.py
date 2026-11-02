"""Tabella comparativa e ricalcolo sulla griglia finale configurata dall'utente."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from .optimizer import evaluate
from .polars import PolarGrid, PolarDomainError
from .settings import sizing_settings


def rejection_reason(run, cfg):
    if run['accepted']:
        return ''
    if run['status'] == 'no_feasible_seed_found':
        return 'Nessun seme ammissibile trovato; fattibilita non determinata'
    reasons = []
    if not run.get('solver_success',False):
        reasons.append(run.get('solver_message','SLSQP non convergente'))
    if 'verification_error' in run:
        reasons.append(run['verification_error'])
    if run.get('min_constraint',0) < -cfg['constraint_tolerance']:
        reasons.append('Vincolo violato nella griglia di verifica')
    if max(run.get('thrust_refinement_changes',[0])) >= cfg['max_thrust_grid_change']:
        reasons.append('Sensibilita della spinta alla griglia superiore alla soglia')
    if run.get('coarse_energy_J',0)>run.get('seed_energy_J',float('inf'))*(1+1e-6):
        reasons.append('Energia superiore al seme')
    return '; '.join(reasons) or 'Verifica finale non superata; consultare il report'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    report = json.loads(raw)
    cfg = sizing_settings({'sizing':report['settings']})
    scope = report['scope']
    expected = {(p,b) for p in scope['profiles'] for b in scope['blade_counts']}
    actual = {(r['profile'],r['blades']) for r in report['runs']}
    if expected != actual or len(actual) != len(report['runs']):
        parser.error('Confronto incompleto o coppie duplicate: attendere la fine del calcolo.')
    out = args.report.parent
    rows = []
    for r in report['runs']:
        rows.append({'profile':r['profile'],'blades':r['blades'],'accepted':r['accepted'],
                     'energy_J':r.get('energy_J'),'iterations':r.get('iterations'),
                     'reason':rejection_reason(r,cfg)})
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    accepted = sorted((r for r in report['runs'] if r['accepted']),key=lambda r:r['energy_J'])
    verification = {'report_sha256':hashlib.sha256(raw).hexdigest(),'attempted_pairs':len(rows),
                    'accepted_pairs':len(accepted),'passed':False,'stations':cfg['stations_final']}
    lines = ['# Confronto SLSQP del catalogo','',
             f"Coppie esaminate: {len(rows)}. Accettate: {len(accepted)}.",
             'Ricerca locale; nessuna garanzia di minimo globale. Avvii registrati nel report.',
             'I casi scartati non dimostrano impossibilita fisica. Dettagli in comparison.csv.','',
             '| Profilo | Pale | Energia [J] | Esito |',
             '|---|---:|---:|---|']
    for r in sorted(rows,key=lambda r:(not r['accepted'],r['energy_J'] if r['energy_J'] is not None else float('inf'))):
        energy = f"{r['energy_J']:.2f}" if r['energy_J'] is not None else '—'
        lines.append(f"| {r['profile']} | {r['blades']} | {energy} | {'Accettato' if r['accepted'] else r['reason']} |")
    if accepted:
        best = accepted[0]
        case, design = report['input_case'], best['design']
        case['sizing'] = cfg
        polar = PolarGrid.load(Path(__file__).parent/'airfoils/polars_neuralfoil'/f"{best['profile']}.json")
        try:
            energy, constraints, cases = evaluate(case,design,polar,stations=cfg['stations_final'])
            reference_cases = best.get('verification_grid_cases',best['cases'])
            changes = [abs(f['thrust_rotor_N']/c['thrust_rotor_N']-1) for c,f in zip(reference_cases,cases)]
            passed = bool(min(constraints)>=-cfg['constraint_tolerance'] and max(changes)<cfg['max_thrust_grid_change'])
            verification.update(passed=passed,energy_J=energy,min_constraint=float(min(constraints)),
                                thrust_change_verification_to_final=changes,
                                cases=[{k:v for k,v in c.items() if k!='local'} for c in cases])
        except PolarDomainError as exc:
            verification['error'] = str(exc)
        d = design['outer_diameter_m']
        limits = case['rotor']['hub_diameter_bounds_m']
        active = []
        if abs(design['hub_diameter_m']-limits[0]) < 1e-6*d:
            active.append('Mozzo al limite inferiore')
        if abs(design['hub_diameter_m']-limits[1]) < 1e-6*d:
            active.append('Mozzo al limite superiore')
        for i,c in enumerate(design['chord_m']):
            for name,bound in zip(('inferiore','superiore'),report['settings']['chord_over_D_bounds']):
                if abs(c-bound*d)<1e-6*d:
                    active.append(f'Corda nodo {i} al limite {name}')
        verification['active_geometric_bounds'] = active
        lines += ['',f"Migliore accettato: {best['profile']}, {best['blades']} pale.",
                  f"Verifica aggiuntiva a {cfg['stations_final']} anelli: {'SUPERATA' if verification['passed'] else 'NON SUPERATA'}.",
                  'Limiti geometrici raggiunti: '+('; '.join(active) or 'nessuno fra mozzo e corde'),'',
                  'Modello preliminare del solo rotore. Correzione perdite: '+report['settings'].get('loss_model','none')+'; condotto non modellato. Prandtl, se selezionato, riguarda un rotore libero;',
                  'polari numeriche, nessuna validazione sperimentale o verifica strutturale.']
    (out/'verification_final.json').write_text(json.dumps(verification,indent=2,allow_nan=False),encoding='utf-8')
    (out/'CONFRONTO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(verification,indent=2))
    return 0 if verification['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
