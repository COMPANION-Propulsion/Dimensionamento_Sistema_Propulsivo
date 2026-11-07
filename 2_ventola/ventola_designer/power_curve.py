"""
Curva di potenza: spinta dell'ugello in funzione della potenza all'albero, da 0 a P_max,
a geometria fissata (condotto e pale del caso), variando i giri.

Per ogni regime n il punto di lavoro e dove la ventola e il condotto si incontrano:

    ventola    dp_ass(Q, n)   pressione totale assiale del BEMT a portata imposta
    condotto   dp_c(Q) = dp* (Q / Q*)^2

e la spinta dell'ugello segue dal Venturi:  T = T* (dp / dp*)^k.

* = punto di progetto del Venturi; k = esponente T ~ dp^k misurato dal ciclo su dp
(k = 1 per un disco ideale). Primo ordine: il condotto ha resistenza quadratica,
cioe le perdite seguono la pressione dinamica (Reynolds del condotto quasi
costante). Gli effetti di Reynolds sulle pale sono invece nel BEMT, perche ogni
regime e risolto davvero. Il punto (0, 0) e esatto.

Uscite in 3_ventola/: 00_sintesi/curva_potenza.json, 01_grafici/curva_potenza.svg,
02_excel/curva_potenza.xlsx.
"""
import json
import math
from copy import deepcopy
from pathlib import Path

from scipy.optimize import brentq

from .polars import PolarDomainError, PolarGrid
from .pressure_bemt import solve_pressure

N_POINTS = 40               # regimi della curva
RPM_START = 0.15            # primo regime / regime di progetto
SCAN = [0.4 + 0.05*i for i in range(25)]   # portata / stima per similitudine, 0.4..1.6
POLARS = Path(__file__).parent/'airfoils'/'polars_neuralfoil'


def _fan_dp(case, design, point, polar, flow, rpm, stations):
    p = {**point, 'volume_flow_m3_s': flow}
    r = solve_pressure(case, {**design, 'rpm': rpm}, p, polar, stations=stations)
    return r['axial_total_pressure_rise_Pa'], r


def operating_point(case, design, point, polar, duct, rpm, q_guess, stations):
    """Portata in cui ventola e condotto danno lo stesso dp, al regime rpm."""
    dp_star, q_star = duct['dp'], duct['Q']

    def f(q):
        return _fan_dp(case, design, point, polar, q, rpm, stations)[0] - dp_star*(q/q_star)**2

    # Scansione attorno alla stima: le polari coprono solo una fascia di incidenze,
    # quindi fuori fascia il BEMT si rifiuta; si cerca il cambio di segno fra punti validi.
    prev = None
    for k in SCAN:
        q = k*q_guess
        try:
            value = f(q)
        except PolarDomainError:
            continue
        if prev is not None and prev[1] > 0.0 >= value:
            lo, hi = prev[0], q
            break
        prev = (q, value)
    else:
        raise PolarDomainError('Nessun punto di lavoro nel dominio delle polari.')
    q = brentq(f, lo, hi, xtol=1e-9*q_star, rtol=1e-10)
    dp, r = _fan_dp(case, design, point, polar, q, rpm, stations)
    return q, dp, r


def power_curve(fan_report, venturi_result, p_max=None, n_points=N_POINTS):
    """Righe (rpm, potenza, spinte, dp, Q, ...) da potenza 0 a p_max."""
    case = fan_report['input_case']
    best = fan_report['best']
    design = best['design']
    design_case = best['cases'][0]
    point = deepcopy(case['operating_points'][0])
    polar = PolarGrid.load(POLARS/f"{design['profile']}.json")
    stations = case['sizing']['stations_verification']
    v = venturi_result
    duct = dict(dp=v['ventola']['dp_disk_Pa'], Q=v['ventola']['portata_m3_s'],
                T=v['spinta']['calcolata_N'], k=v['numerica'].get('esponente_T_dp') or 1.0)
    n_star, p_star = design_case['rpm'], design_case['shaft_power_W']
    p_max = 2.0*p_star if p_max is None else float(p_max)
    n_max = 1.1*n_star*(p_max/p_star)**(1.0/3.0)        # fan laws: P ~ n^3

    rows = [dict(rpm=0.0, potenza_albero_W=0.0, spinta_ugello_N=0.0, spinta_pale_N=0.0,
                 dp_assiale_Pa=0.0, portata_m3_s=0.0, coppia_Nm=0.0, rendimento=float('nan'),
                 Re_min=float('nan'), stato='esatto')]
    skipped = []
    for i in range(n_points):
        rpm = n_star*RPM_START + (n_max - n_star*RPM_START)*i/(n_points - 1)
        try:
            q, dp, r = operating_point(case, design, point, polar, duct, rpm,
                                       duct['Q']*rpm/n_star, stations)
        except (PolarDomainError, ValueError) as exc:
            skipped.append(dict(rpm=rpm, motivo=str(exc)))
            continue
        row = dict(rpm=rpm, potenza_albero_W=r['shaft_power_W'],
                   spinta_ugello_N=duct['T']*(dp/duct['dp'])**duct['k'],
                   spinta_pale_N=r['thrust_rotor_N'], dp_assiale_Pa=dp, portata_m3_s=q,
                   coppia_Nm=r['torque_Nm'], rendimento=r['total_pressure_efficiency'],
                   Re_min=r['Re_min'], stato='BEMT')
        if row['potenza_albero_W'] > p_max:
            prev = rows[-1]          # ultimo punto interpolato esattamente a p_max
            w = (p_max - prev['potenza_albero_W'])/(row['potenza_albero_W'] - prev['potenza_albero_W'])
            rows.append({k: (prev[k] + w*(row[k] - prev[k]) if isinstance(row[k], float) else 'interpolato')
                         for k in row})
            break
        critical = r.get('rotor_stall_critical')
        row['rotor_stall_margin_deg'] = critical['rotor_stall_margin_deg'] if critical else None
        rows.append(row)
    for row in rows:
        row.setdefault('rotor_stall_margin_deg', None)
    return dict(
        righe=rows, saltati=skipped, potenza_max_W=p_max,
        progetto=dict(rpm=n_star, potenza_albero_W=p_star, spinta_ugello_N=duct['T'],
                      dp_assiale_Pa=design_case.get('axial_total_pressure_rise_Pa'),
                      portata_m3_s=design_case['volume_flow_m3_s']),
        condotto=dict(dp_progetto_Pa=duct['dp'], portata_progetto_m3_s=duct['Q'],
                      spinta_progetto_N=duct['T'], esponente_k=duct['k'],
                      modello='dp = dp* (Q/Q*)^2, T = T* (dp/dp*)^k'),
        ventola=dict(profilo=design['profile'], pale=design['blade_count'],
                     mozzo_m=design['hub_diameter_m'], diametro_m=design['outer_diameter_m']),
        nota=('Geometria fissa, giri variabili. La spinta dell ugello comprende il condotto; '
              'la spinta delle pale e la sola forza sul rotore. Regimi senza punto di lavoro '
              'nel dominio delle polari sono in "saltati". Margine rotorico stimato sui soli punti BEMT. '
              'Con statore attivo il modello ne ricalcola il calettamento a ciascun regime.'))


def _plot(curve, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = [r for r in curve['righe']]
    P = [r['potenza_albero_W'] for r in rows]
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(9, 11), sharex=True)
    a1.plot(P, [r['spinta_ugello_N'] for r in rows], 'b-o', ms=3, label='spinta ugello (tubo + pale)')
    a1.plot(P, [r['spinta_pale_N'] for r in rows], 'c--', label='spinta sulle pale')
    d = curve['progetto']
    a1.plot([d['potenza_albero_W']], [d['spinta_ugello_N']], 'r*', ms=12, label='punto di progetto')
    a1.set_ylabel('spinta [N]')
    a2.plot(P, [r['rpm'] for r in rows], 'k-')
    a2.set_ylabel('giri [rpm]')
    a3.plot(P, [r['dp_assiale_Pa'] for r in rows], 'm-', label='Δp assiale')
    a3b = a3.twinx()
    a3b.plot(P, [r['portata_m3_s']*1e3 for r in rows], 'g--', label='portata')
    a3.set_ylabel('Δp assiale [Pa]')
    a3b.set_ylabel('portata [L/s]')
    a3.set_xlabel('potenza all\'albero [W]')
    for a in (a1, a2, a3):
        a.grid(True, ls=':', alpha=0.6)
        a.axvline(curve['potenza_max_W'], color='r', lw=0.8, ls=':')
    a1.legend(fontsize=9)
    a3.legend(loc='upper left', fontsize=9)
    a3b.legend(loc='lower right', fontsize=9)
    v = curve['ventola']
    a1.set_title(f"Curva di potenza: {v['profilo']}, {v['pale']} pale, D {v['diametro_m']*1e3:.1f} mm "
                 f"(geometria fissa, giri variabili)")
    fig.tight_layout()
    fig.savefig(path, format='svg')
    plt.close(fig)


def _xlsx(curve, path):
    from openpyxl import Workbook
    from openpyxl.chart import Reference, ScatterChart, Series
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = 'Curva'
    head = [('rpm', 'giri [rpm]'), ('potenza_albero_W', 'potenza albero [W]'),
            ('spinta_ugello_N', 'spinta ugello [N]'), ('spinta_pale_N', 'spinta pale [N]'),
            ('dp_assiale_Pa', 'Δp assiale [Pa]'), ('portata_m3_s', 'portata [m3/s]'),
            ('coppia_Nm', 'coppia [N m]'), ('rendimento', 'rendimento [-]'), ('stato', 'stato'),
            ('rotor_stall_margin_deg', 'margine rotore [°]')]
    for c, (_, h) in enumerate(head, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
        ws.column_dimensions[cell.column_letter].width = 18
    for r, row in enumerate(curve['righe'], 2):
        for c, (k, _) in enumerate(head, 1):
            v = row.get(k)
            ws.cell(row=r, column=c, value=None if isinstance(v, float) and math.isnan(v) else v)
    ws.freeze_panes = 'A2'
    n = len(curve['righe']) + 1
    ch = ScatterChart()
    ch.title, ch.x_axis.title, ch.y_axis.title = 'Spinta in funzione della potenza', 'potenza albero [W]', 'spinta [N]'
    x = Reference(ws, min_col=2, min_row=2, max_row=n)
    for col in (3, 4):
        ch.series.append(Series(Reference(ws, min_col=col, min_row=1, max_row=n), x, title_from_data=True))
    ws.add_chart(ch, 'K2')
    wb.save(path)


def export_power_curve(fan_dir, venturi_file, p_max=None, out_dir=None):
    """Calcola la curva della ventola in fan_dir e la scrive in out_dir (default fan_dir)."""
    fan_dir = Path(fan_dir)
    out = Path(out_dir) if out_dir else fan_dir
    for sub in ('00_sintesi', '01_grafici', '02_excel'):
        (out/sub).mkdir(parents=True, exist_ok=True)
    report = json.loads((fan_dir/'00_sintesi'/'report.json').read_text(encoding='utf-8'))
    if not report.get('best'):
        raise ValueError('Nessuna ventola accettata: curva di potenza non calcolabile.')
    venturi = json.loads(Path(venturi_file).read_text(encoding='utf-8'))
    curve = power_curve(report, venturi, p_max)
    (out/'00_sintesi'/'curva_potenza.json').write_text(
        json.dumps(curve, indent=1, allow_nan=True, ensure_ascii=False), encoding='utf-8')
    _plot(curve, out/'01_grafici'/'curva_potenza.svg')
    _xlsx(curve, out/'02_excel'/'curva_potenza.xlsx')
    return curve
