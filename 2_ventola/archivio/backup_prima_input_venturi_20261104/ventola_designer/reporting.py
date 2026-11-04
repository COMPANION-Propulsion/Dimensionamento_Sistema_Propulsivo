"""Report leggibile generato dai risultati, senza nuovi calcoli o ottimizzazioni."""
from .config import operating_air


def cell(value):
    return str(value).replace('|', r'\|').replace('\n', ' ').replace('\r', ' ')


def render_report(report):
    case, best = report['input_case'], report['best']
    rows = ['# Esito del dimensionamento', '',
            'Soluzione accettata nel modello preliminare.' if best else
            'Nessuna soluzione accettata trovata. Questo non dimostra impossibilita fisica.', '',
            f"Diametro imposto: {case['rotor']['outer_diameter_m']*1000:.3f} mm.",
            'Spinta riferita al solo rotore; velocita assiale riferita alla corrente lontano a monte.', '',
            '## Requisiti e condizioni', '',
            '| Punto | Spinta minima [N] | Velocita [m/s] | Durata [s] | T [K] | p statica [Pa] |',
            '|---|---:|---:|---:|---:|---:|']
    for p in case['operating_points']:
        air = operating_air(case,p)
        rows.append(f"| {cell(p['name'])} | {p['minimum_rotor_thrust_N']:.6g} | {p['axial_inlet_velocity_m_s']:.6g} | {p['duration_s']:.6g} | {air['temperature_K']:.6g} | {air['static_pressure_Pa']:.6g} |")
    if best:
        design = best['design']
        rows += ['', '## Risultato', '',
                 f"Profilo: {cell(design['profile'])}. Pale: {design['blade_count']}. Mozzo: {design['hub_diameter_m']*1000:.3f} mm.",
                 f"Energia meccanica del ciclo: {best['energy_J']:.3f} J.",
                 'Ottimo locale fra i tentativi accettati; minimo globale non garantito.', '',
                 '| Punto | Spinta [N] | Margine sul requisito [N] | Potenza albero [W] | Coppia [Nm] | rpm |',
                 '|---|---:|---:|---:|---:|---:|']
        if len(best['cases']) != len(case['operating_points']):
            raise ValueError('Risultati incompleti per i punti operativi.')
        for p,r in zip(case['operating_points'],best['cases']):
            rows.append(f"| {cell(p['name'])} | {r['thrust_rotor_N']:.6f} | {r['thrust_rotor_N']-p['minimum_rotor_thrust_N']:.6f} | {r['shaft_power_W']:.4f} | {r['torque_Nm']:.6f} | {r['rpm']:.2f} |")
        rows += ['', 'Il margine tabulato e rispetto al requisito utente, non al requisito maggiorato dal margine numerico.', '',
                 '| Posizione radiale normalizzata | Corda [mm] | Calettamento [gradi] |', '|---:|---:|---:|']
        for s,c,b in zip(design['span_nodes'],design['chord_m'],design['pitch_deg']):
            rows.append(f'| {s:.3f} | {c*1000:.3f} | {b:.3f} |')
        rows += ['', f"Minimo vincolo normalizzato alla verifica: {best.get('min_constraint','non disponibile')}.",
                 'I dettagli di convergenza, griglia e polari sono in optimization.json.']
    if best and 'geometry_screening' in best:
        g=best['geometry_screening']
        rows += ['', '## Screening geometrico', '',
                 f"Stazioni controllate: {g['stations']}.",
                 f"Minimo spazio circonferenziale fra inviluppi: {g['min_circumferential_envelope_gap_m']*1000:.4f} mm; richiesto {g['required_gap_m']*1000:.4f} mm.",
                 f"Minimo degli spessori massimi delle sezioni: {g['min_section_max_thickness_m']*1000:.4f} mm; richiesto {g['required_thickness_m']*1000:.4f} mm.",
                 'Controllo su sezioni campionate; non distanza minima 3D, controllo dei bordi sottili o verifica strutturale.']
    rows += ['', '## Tentativi', '', '| Profilo | Pale | Esito | Diagnostica |', '|---|---:|---|---|']
    for run in report['runs']:
        if run['accepted']:
            explanation = 'Verifiche del dimensionatore superate'
        elif run['status']=='no_feasible_seed_found':
            explanation = 'Nessun punto iniziale ammissibile trovato; fattibilita non determinata'
        else:
            explanation = run.get('verification_error') or run.get('solver_message','Consultare attempts in optimization.json')
            if run.get('solver_success'):
                explanation += '; candidato escluso dalle verifiche successive'
        rows.append(f"| {cell(run['profile'])} | {run['blades']} | {'Accettato' if run['accepted'] else 'Escluso'} | {cell(explanation)} |")
    rows += ['', '## Limiti', '',
             'Polari numeriche, assenza di validazione sperimentale e verifica strutturale.',
             'Modello perdite: '+cell(report.get('settings',{}).get('loss_model','none'))+'.',
             'none esclude le perdite; prandtl_free_rotor e una correzione per rotore libero, non per ventola intubata. Il condotto non e modellato.',
             'La convergenza numerica non certifica la prestazione reale o la costruibilita della pala.', '']
    return '\n'.join(rows)
