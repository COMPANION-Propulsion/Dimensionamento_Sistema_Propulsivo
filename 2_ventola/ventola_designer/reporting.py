"""Report leggibile generato dai risultati, senza nuovi calcoli o ottimizzazioni."""
from .config import operating_air


def cell(value):
    return str(value).replace('|', r'\|').replace('\n', ' ').replace('\r', ' ')


def render_report(report):
    if report['input_case'].get('design_mode') == 'pressure_flow':
        return render_pressure_report(report)
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


def render_pressure_report(report):
    case, best = report['input_case'], report['best']
    rows = ['# Dimensionamento a portata imposta', '',
        'Candidato accettato nel modello preliminare.' if best else 'Nessun candidato accettato trovato.',
        f"Diametro esterno imposto: {case['rotor']['outer_diameter_m']:.6g} m.",
        'La portata e conservata; la velocita sulle pale e Q / area anulare libera.', '',
        '| Condizione | Q [m3/s] | Delta p totale minimo [Pa] | V disco senza mozzo [m/s] | Durata [s] |',
        '|---|---:|---:|---:|---:|']
    for point in case['operating_points']:
        rows.append(f"| {cell(point['name'])} | {point['volume_flow_m3_s']:.6g} | {point['minimum_total_pressure_rise_Pa']:.6g} | {point['full_disk_velocity_m_s']:.6g} | {point['duration_s']:.6g} |")
        source = point.get('venturi_source')
        if source:
            rows += ['', f"Sorgente {cell(point['name'])}: {cell(source['path'])}.",
                f"Ciclo dp Venturi convergente: {source['dp_loop_converged']}; studio di griglia affidabile: {source['thrust_grid_reliable']}.",
                'Questi stati descrivono il calcolo a monte e non sono validati dal dimensionatore della ventola.', '']
    if best:
        d = best['design']
        rows += ['', f"Profilo {cell(d['profile'])}; pale {d['blade_count']}; mozzo {d['hub_diameter_m']:.6g} m.",
            f"Energia meccanica del ciclo: {best['energy_J']:.6g} J.", '',
            '| Condizione | Q [m3/s] | Va pale [m/s] | Delta p totale [Pa] | Delta p statica [Pa] | Potenza albero [W] | Coppia [Nm] | rpm |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
        if len(best['cases']) != len(case['operating_points']):
            raise ValueError('Risultati incompleti.')
        for point, result in zip(case['operating_points'], best['cases']):
            keys = ('volume_flow_m3_s','axial_blade_velocity_m_s','total_pressure_rise_Pa',
                    'static_pressure_rise_Pa','shaft_power_W','torque_Nm','rpm')
            rows.append('| '+cell(point['name'])+' | '+' | '.join(f'{result[k]:.6g}' for k in keys)+' |')
        rows += ['', '| Posizione normalizzata | Corda [m] | Calettamento [gradi] |', '|---:|---:|---:|']
        for s,c,p in zip(d['span_nodes'],d['chord_m'],d['pitch_deg']):
            rows.append(f'| {s:.6g} | {c:.6g} | {p:.6g} |')
    rows += ['', '| Profilo | Pale | Esito | Dettaglio |', '|---|---:|---|---|']
    for run in report['runs']:
        rows.append(f"| {cell(run['profile'])} | {run['blades']} | {cell(run['status'])} | {cell(run.get('verification_error',run.get('solver_message','')))} |")
    rows += ['', '## Interpretazione', '',
        'Pressione totale media pesata sulla portata; include energia cinetica dello swirl in uscita.',
        'La potenza all’albero comprende il lavoro sul fluido e le perdite di profilo stimate dalle polari.',
        'Spinta rotorica, potenza nello swirl, perdite e rendimento totale sono nel JSON.',
        'La forza sul rotore non e la spinta complessiva del sistema Venturi.',
        'Portata uniforme nell’anello, ingresso senza swirl, densita costante; interazioni di cascata,',
        'perdite al mozzo/pareti e gioco di punta non modellati. Nessuna verifica accoppiata del condotto con il mozzo.',
        'Il requisito e soddisfatto nel modello; convergenza e screening non costituiscono validazione sperimentale.',
        'La ricerca SLSQP e locale; minimo globale non garantito.', '']
    return '\n'.join(rows)
