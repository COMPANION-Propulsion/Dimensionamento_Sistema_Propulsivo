"""Tabella comparativa e ricalcolo a 128 anelli del migliore risultato SLSQP."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from .optimizer import evaluate
from .polars import PolarGrid, PolarDomainError


def rejection_reason(run):
    if run['accepted']:
        return ''
    if run['status'] == 'no_feasible_seed_found':
        return 'Nessun seme ammissibile trovato; fattibilita non determinata'
    reasons = []
    if not run.get('solver_success',False):
        reasons.append(run.get('solver_message','SLSQP non convergente'))
    if 'verification_error' in run:
        reasons.append(run['verification_error'])
    if run.get('min_constraint',0) < -1e-6:
        reasons.append('Vincolo violato nella verifica a 64 anelli')
    if max(run.get('thrust_refinement_changes',[0])) >= .01:
        reasons.append('Sensibilita della spinta alla griglia >= 1%')
    if run.get('coarse_energy_J',0)>run.get('seed_energy_J',float('inf'))*(1+1e-6):
        reasons.append('Energia superiore al seme')
    return '; '.join(reasons) or 'Verifica finale non superata; consultare il report'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    report = json.loads(raw)
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
                     'reason':rejection_reason(r)})
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    accepted = sorted((r for r in report['runs'] if r['accepted']),key=lambda r:r['energy_J'])
    verification = {'report_sha256':hashlib.sha256(raw).hexdigest(),'attempted_pairs':len(rows),
                    'accepted_pairs':len(accepted),'passed':False,'stations':128}
    lines = ['# Confronto SLSQP del catalogo','',
             f"Coppie esaminate: {len(rows)}. Accettate: {len(accepted)}.",
             'Un solo avvio locale per coppia; nessuna garanzia di minimo globale.',
             'I casi scartati non dimostrano impossibilita fisica. Dettagli in comparison.csv.','',
             '| Profilo | Pale | Energia [J] | Esito |',
             '|---|---:|---:|---|']
    for r in sorted(rows,key=lambda r:(not r['accepted'],r['energy_J'] if r['energy_J'] is not None else float('inf'))):
        energy = f"{r['energy_J']:.2f}" if r['energy_J'] is not None else '—'
        lines.append(f"| {r['profile']} | {r['blades']} | {energy} | {'Accettato' if r['accepted'] else r['reason']} |")
    if accepted:
        best = accepted[0]
        case, design = report['input_case'], best['design']
        polar = PolarGrid.load(Path(__file__).parent/'airfoils/polars_neuralfoil'/f"{best['profile']}.json")
        try:
            energy, constraints, cases = evaluate(case,design,polar,stations=128)
            changes = [abs(f['thrust_rotor_N']/c['thrust_rotor_N']-1) for c,f in zip(best['cases'],cases)]
            passed = bool(min(constraints)>=-1e-6 and max(changes)<.01)
            verification.update(passed=passed,energy_J=energy,min_constraint=float(min(constraints)),
                                thrust_change_64_to_128=changes,
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
                  f"Verifica aggiuntiva a 128 anelli: {'SUPERATA' if verification['passed'] else 'NON SUPERATA'}.",
                  'Limiti geometrici raggiunti: '+('; '.join(active) or 'nessuno fra mozzo e corde'),'',
                  'Modello preliminare del solo rotore. Perdite di punta/mozzo e condotto non modellati;',
                  'polari numeriche, nessuna validazione sperimentale o verifica strutturale.']
    (out/'verification_128.json').write_text(json.dumps(verification,indent=2,allow_nan=False),encoding='utf-8')
    (out/'CONFRONTO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(verification,indent=2))
    return 0 if verification['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
