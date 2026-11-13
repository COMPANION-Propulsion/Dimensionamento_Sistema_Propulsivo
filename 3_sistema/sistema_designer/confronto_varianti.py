"""
Confronto fra le due catene complete, con statore (Statore/) e senza (NoStatore/).

Legge, per ciascuna cartella di variante, solo file gia scritti:
    2_venturi/00_sintesi/risultati.json, 2_venturi/03_cad/profilo.csv
    3_ventola/00_sintesi/report.json (punto di progetto, CAD dello statore)
    4_sistema/00_sintesi/potenza_manovra.json, confronto_statore.json (swirl perso)
    fascia.json (storia del ciclo sulla fascia)
e scrive in risultati/<caso>/5_confronto_statore/:
    confronto_statore.json, RISULTATO.md, confronto_statore.xlsx,
    bilancio_potenza.svg, confronto_grandezze.svg, profili_tubi.svg, fascia_iterazioni.svg

Una variante mancante o fallita non ferma il confronto: esce con quello che c'e e lo dice.
Il bilancio e sulla potenza all'albero per ugello:
    albero = getto utile (Q * p0_uscita) + perdite del condotto (Q * perdita totale)
             + profili del rotore + statore + swirl perso nel getto + residuo
Il residuo non e una perdita: e quanto i modelli di venturi e ventola non chiudono fra loro.
"""
import csv
import json
import math
from pathlib import Path

NAMES = ('Statore', 'NoStatore')
COLORS = {'Statore': '#1f77b4', 'NoStatore': '#ff7f0e'}
OUT = '5_confronto_statore'


def _json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def wall_area_m2(csv_path):
    """Area di parete interna [m2] = somma di 2*pi*R*ds sul profilo (z_mm, r_mm)."""
    path = Path(csv_path)
    if not path.is_file():
        return None
    with path.open(encoding='utf-8') as fh:
        pts = [(float(r['z_mm']), float(r['r_mm'])) for r in csv.DictReader(fh)]
    area = sum(math.pi*(r0 + r1)*math.hypot(z1 - z0, r1 - r0)
               for (z0, r0), (z1, r1) in zip(pts, pts[1:]))
    return area*1e-6


def profile(csv_path):
    path = Path(csv_path)
    if not path.is_file():
        return None
    with path.open(encoding='utf-8') as fh:
        rows = [(float(r['z_mm']), float(r['r_mm'])) for r in csv.DictReader(fh)]
    return [z for z, _ in rows], [r for _, r in rows]


def stator_area_mm2(stator):
    """Area delle pale dello statore [mm2]: corda integrata sul raggio, per il numero di pale."""
    if not stator or not stator.get('radius_mm'):
        return 0.0
    r, c = stator['radius_mm'], stator['chord_mm']
    per_vane = sum(0.5*(c[i] + c[i + 1])*(r[i + 1] - r[i]) for i in range(len(r) - 1))
    return per_vane*stator['vanes']


def summarise(folder):
    """Tutte le grandezze di una variante; {'presente': False, 'motivo': ...} se manca."""
    folder = Path(folder)
    if not folder.is_dir():
        return dict(presente=False, motivo='cartella assente')
    ven = _json(folder/'2_venturi'/'00_sintesi'/'risultati.json')
    rep = _json(folder/'3_ventola'/'00_sintesi'/'report.json')
    fascia = _json(folder/'fascia.json') or []
    errors = [r['errore'] for r in fascia if 'errore' in r]
    if ven is None or not rep or not rep.get('best'):
        why = ('; '.join(errors) if errors else
               'venturi assente' if ven is None else 'ventola senza progetto accettato')
        return dict(presente=False, motivo=why, fascia=fascia)
    ok = [r for r in fascia if 'errore' not in r]
    v, g, loss = ven['ventola'], ven['geometria'], ven.get('perdite') or {}
    c = rep['best']['cases'][0]
    cad = rep.get('cad') or {}
    st = cad.get('stator')
    q = c['volume_flow_m3_s']
    stator_on = bool(c.get('stator_enabled'))
    cmp = _json(folder/'4_sistema'/'00_sintesi'/'confronto_statore.json')
    swirl_note = None
    if stator_on:
        rows = [r for r in (cmp or {}).get('varianti', []) if r.get('statore') and 'errore' not in r]
        if rows:
            swirl_W = rows[0].get('swirl_perso_Pa', 0.0)*q
        else:
            swirl_W, swirl_note = 0.0, 'swirl perso con lo statore non disponibile (confronto_statore.json), contato 0'
    else:
        swirl_W = c['swirl_power_W']
    shaft = c['shaft_power_W']
    duct_W = q*loss.get('totale_Pa', 0.0)
    jet_W = q*loss['p0_uscita_Pa'] if 'p0_uscita_Pa' in loss else None
    balance = None
    if jet_W is not None:
        parts = dict(getto_utile_W=jet_W, perdite_condotto_W=duct_W,
                     profili_rotore_W=c['profile_loss_power_W'],
                     statore_W=c.get('stator_loss_power_W', 0.0) if stator_on else 0.0,
                     swirl_perso_W=swirl_W)
        resid = shaft - sum(parts.values())
        balance = dict(**parts, residuo_W=resid, residuo_pct_albero=100*resid/shaft)
    man = _json(folder/'4_sistema'/'00_sintesi'/'potenza_manovra.json') or {}
    last = ok[-1] if ok else {}
    wall = wall_area_m2(folder/'2_venturi'/'03_cad'/'profilo.csv')
    return dict(
        presente=True, statore=stator_on, note=[swirl_note] if swirl_note else [],
        fascia=dict(L_disk_mm=1e3*last['L_disk_m'] if last else 1e3*v['L_ventola_m'],
                    iterazioni=len(ok), convergito=last.get('convergito'),
                    monte_mm=1e3*last['monte_m'] if last else None,
                    valle_mm=1e3*last['valle_m'] if last else None,
                    storia=fascia),
        tubo=dict(L_tubo_mm=g['L_tubo_mm'], D_ventola_mm=1e3*v['D_ventola_m'],
                  D_uscita_mm=1e3*g['D_uscita_m'],
                  area_parete_cm2=None if wall is None else 1e4*wall,
                  pale_statore=st['vanes'] if st else 0, area_pale_statore_mm2=stator_area_mm2(st)),
        venturi=dict(dp_assiale_Pa=v['dp_disk_Pa'], portata_L_s=1e3*v['portata_m3_s'],
                     perdita_imbocco_Pa=loss.get('imbocco_Pa'), perdita_disco_Pa=loss.get('disco_Pa'),
                     perdita_valle_Pa=loss.get('valle_Pa'), perdita_totale_Pa=loss.get('totale_Pa'),
                     potenza_persa_W=loss.get('potenza_persa_W')),
        ventola=dict(giri_rpm=c['rpm'], potenza_albero_W=shaft,
                     rendimento=c['axial_total_pressure_rise_Pa']*q/shaft,
                     perdita_profili_W=c['profile_loss_power_W'],
                     perdita_statore_W=c.get('stator_loss_power_W', 0.0) if stator_on else 0.0,
                     swirl_perso_W=swirl_W, coppia_netta_mNm=1e3*c['net_torque_Nm'],
                     Mach_max=c['Mach_max'], pale_rotore=rep['best']['design']['blade_count'],
                     profilo_rotore=rep['best']['design']['profile']),
        bilancio=balance,
        manovra=dict(energia_J=man.get('energia_manovra_J'), picco_W=man.get('picco_W')),
        profilo=profile(folder/'2_venturi'/'03_cad'/'profilo.csv'),
        banda=dict(z_centro_mm=1e3*v['z_centro_ventola_m'], semi_mm=1e3*v['L_ventola_m']))


# (gruppo, sezione, chiave, etichetta, unita, decimali, meno_e_meglio)
ROWS = (
    ('fascia e tubo', 'fascia', 'L_disk_mm', 'L_disk finale', 'mm', 2, True),
    ('fascia e tubo', 'fascia', 'iterazioni', 'passate sulla fascia', '', 0, None),
    ('fascia e tubo', 'tubo', 'L_tubo_mm', 'lunghezza del tubo', 'mm', 1, True),
    ('fascia e tubo', 'tubo', 'D_ventola_mm', 'diametro ventola', 'mm', 2, None),
    ('fascia e tubo', 'tubo', 'D_uscita_mm', 'diametro di uscita', 'mm', 2, None),
    ('fascia e tubo', 'tubo', 'area_parete_cm2', 'area di parete del tubo', 'cm2', 1, True),
    ('fascia e tubo', 'tubo', 'pale_statore', 'pale dello statore', '', 0, True),
    ('fascia e tubo', 'tubo', 'area_pale_statore_mm2', 'area delle pale dello statore', 'mm2', 0, True),
    ('venturi', 'venturi', 'dp_assiale_Pa', 'Δp assiale richiesto', 'Pa', 2, True),
    ('venturi', 'venturi', 'portata_L_s', 'portata', 'L/s', 3, None),
    ('venturi', 'venturi', 'perdita_imbocco_Pa', 'perdita imbocco', 'Pa', 2, True),
    ('venturi', 'venturi', 'perdita_disco_Pa', 'perdita banda del disco', 'Pa', 2, True),
    ('venturi', 'venturi', 'perdita_valle_Pa', 'perdita disco-uscita', 'Pa', 2, True),
    ('venturi', 'venturi', 'perdita_totale_Pa', 'perdita totale del condotto', 'Pa', 2, True),
    ('ventola', 'ventola', 'giri_rpm', 'giri', 'rpm', 0, None),
    ('ventola', 'ventola', 'potenza_albero_W', 'potenza all\'albero (per ugello)', 'W', 3, True),
    ('ventola', 'ventola', 'rendimento', 'rendimento (Δp assiale·Q / albero)', '', 3, False),
    ('ventola', 'ventola', 'perdita_profili_W', 'perdita dei profili del rotore', 'W', 3, True),
    ('ventola', 'ventola', 'perdita_statore_W', 'attrito dello statore', 'W', 3, True),
    ('ventola', 'ventola', 'swirl_perso_W', 'swirl perso nel getto', 'W', 3, True),
    ('ventola', 'ventola', 'coppia_netta_mNm', 'coppia netta sul veicolo', 'mN·m', 3, True),
    ('ventola', 'ventola', 'Mach_max', 'Mach massimo', '', 3, None),
    ('bilancio', 'bilancio', 'getto_utile_W', 'getto utile (Q·p0 uscita)', 'W', 3, False),
    ('bilancio', 'bilancio', 'perdite_condotto_W', 'perdite del condotto', 'W', 3, True),
    ('bilancio', 'bilancio', 'profili_rotore_W', 'profili del rotore', 'W', 3, True),
    ('bilancio', 'bilancio', 'statore_W', 'statore', 'W', 3, True),
    ('bilancio', 'bilancio', 'swirl_perso_W', 'swirl perso', 'W', 3, True),
    ('bilancio', 'bilancio', 'residuo_W', 'residuo non chiuso', 'W', 3, None),
    ('bilancio', 'bilancio', 'residuo_pct_albero', 'residuo / potenza all\'albero', '%', 2, None),
    ('manovra', 'manovra', 'energia_J', 'energia sulla manovra', 'J', 2, True),
    ('manovra', 'manovra', 'picco_W', 'picco di potenza (faccia)', 'W', 2, True),
)


def _get(summary, section, key):
    if not summary.get('presente'):
        return None
    return (summary.get(section) or {}).get(key)


def build_table(variants):
    table = []
    for group, section, key, label, unit, dec, better in ROWS:
        a, b = (_get(variants.get(n, {}), section, key) for n in NAMES)
        row = dict(gruppo=group, voce=label, chiave=f'{section}.{key}', unita=unit, decimali=dec,
                   Statore=a, NoStatore=b, meno_e_meglio=better)
        if a is not None and b is not None:
            row['delta'] = b - a
            row['delta_pct'] = 100*(b/a - 1) if a else None
        table.append(row)
    return table


def verdict(table, variants):
    """Vantaggi e svantaggi dell'assenza dello statore, scritti dai numeri."""
    by = {r['chiave']: r for r in table}
    pros, cons = [], []

    def add(key, phrase_good, phrase_bad, minimum=0.0):
        r = by.get(key)
        if not r or r.get('delta') is None or abs(r['delta']) <= minimum:
            return
        dec, unit = r['decimali'], f" {r['unita']}" if r['unita'] else ''
        pct = f" ({r['delta_pct']:+.1f} %)" if r.get('delta_pct') is not None else ''
        text = (f"{phrase_good if r['delta'] < 0 else phrase_bad}: "
                f"{r['delta']:+.{dec}f}{unit}{pct}").replace('-', '−')
        good = (r['delta'] < 0) == bool(r['meno_e_meglio'])
        (pros if good else cons).append(text)

    add('ventola.potenza_albero_W', 'senza statore consuma meno potenza all\'albero',
        'senza statore serve più potenza all\'albero', 1e-4)
    add('manovra.energia_J', 'energia sulla manovra minore', 'energia sulla manovra maggiore', 1e-3)
    add('fascia.L_disk_mm', 'fascia della ventola più corta', 'fascia della ventola più lunga', 0.05)
    add('tubo.L_tubo_mm', 'tubo più corto', 'tubo più lungo', 0.05)
    add('tubo.area_parete_cm2', 'meno area di parete', 'più area di parete', 0.05)
    add('tubo.area_pale_statore_mm2', 'niente pale statore da costruire', 'più area di pale statore', 1.0)
    add('venturi.dp_assiale_Pa', 'Δp assiale richiesto minore', 'Δp assiale richiesto maggiore', 0.05)
    add('ventola.coppia_netta_mNm', 'coppia netta sul veicolo minore',
        'coppia netta sul veicolo maggiore, da compensare (coppie opposte delle due ventole, '
        'ruote di reazione o ugelli a controrotazione)', 1e-3)
    add('bilancio.swirl_perso_W', 'meno swirl perso', 'più swirl perso nel getto', 1e-3)
    add('ventola.perdita_statore_W', 'niente attrito dello statore', 'più attrito dello statore', 1e-3)
    add('ventola.giri_rpm', 'giri minori', 'giri maggiori', 1.0)
    missing = [n for n in NAMES if not variants.get(n, {}).get('presente')]
    if missing:
        pros, cons = [], []
    return pros, cons


def _plots(variants, folder):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names = [n for n in NAMES if variants.get(n, {}).get('presente')]
    files = []
    if not names:
        return files
    label = {'Statore': 'con statore', 'NoStatore': 'senza statore'}

    # bilancio di potenza impilato
    fig, ax = plt.subplots(figsize=(7, 5))
    parts = (('getto_utile_W', 'getto utile', '#2ca02c'), ('perdite_condotto_W', 'perdite del condotto', '#7f7f7f'),
             ('profili_rotore_W', 'profili del rotore', '#1f77b4'), ('statore_W', 'attrito statore', '#9467bd'),
             ('swirl_perso_W', 'swirl perso', '#d62728'), ('residuo_W', 'residuo', '#bcbd22'))
    bottom = [0.0]*len(names)
    for key, lab, col in parts:
        vals = [((variants[n].get('bilancio') or {}).get(key) or 0.0) for n in names]
        ax.bar([label[n] for n in names], vals, bottom=bottom, label=lab, color=col, width=0.55)
        for i, (b0, v) in enumerate(zip(bottom, vals)):
            if v > 0.04*max(variants[n]['ventola']['potenza_albero_W'] for n in names):
                ax.text(i, b0 + v/2, f'{v:.2f}', ha='center', va='center', fontsize=8, color='white')
        bottom = [b0 + v for b0, v in zip(bottom, vals)]
    ax.set_ylabel('potenza all\'albero per ugello [W]')
    ax.set_title('Bilancio di potenza all\'albero')
    ax.legend(fontsize=8, loc='upper left', bbox_to_anchor=(1.0, 1.0))
    ax.grid(True, axis='y', ls=':', alpha=0.6)
    fig.tight_layout()
    fig.savefig(folder/'bilancio_potenza.svg', format='svg')
    plt.close(fig)
    files.append('bilancio_potenza.svg')

    # grandezze principali
    fig, axs = plt.subplots(1, 4, figsize=(13, 4.2))
    for ax, (sec, key, lab) in zip(axs, (('venturi', 'dp_assiale_Pa', 'Δp assiale [Pa]'),
                                         ('ventola', 'giri_rpm', 'giri [rpm]'),
                                         ('ventola', 'potenza_albero_W', 'potenza all\'albero [W]'),
                                         ('ventola', 'coppia_netta_mNm', 'coppia netta [mN·m]'))):
        ax.bar([label[n] for n in names], [variants[n][sec][key] for n in names],
               color=[COLORS[n] for n in names], width=0.55)
        ax.set_ylabel(lab)
        ax.grid(True, axis='y', ls=':', alpha=0.6)
        ax.tick_params(axis='x', labelsize=8)
    fig.suptitle('Con e senza statore: catene complete')
    fig.tight_layout()
    fig.savefig(folder/'confronto_grandezze.svg', format='svg')
    plt.close(fig)
    files.append('confronto_grandezze.svg')

    # profili sovrapposti, fascia evidenziata
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for n in names:
        prof, band = variants[n].get('profilo'), variants[n]['banda']
        if prof:
            ax.plot(prof[0], prof[1], color=COLORS[n], lw=1.6, label=f'{label[n]} (tubo {variants[n]["tubo"]["L_tubo_mm"]:.0f} mm)')
            ax.plot(prof[0], [-r for r in prof[1]], color=COLORS[n], lw=1.6)
        ax.axvspan(band['z_centro_mm'] - band['semi_mm'], band['z_centro_mm'] + band['semi_mm'],
                   color=COLORS[n], alpha=0.15, label=f'fascia {label[n]} ({2*band["semi_mm"]:.1f} mm)')
    ax.set_xlabel('z dall\'ingresso [mm]')
    ax.set_ylabel('raggio [mm]')
    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(True, ls=':', alpha=0.6)
    ax.legend(fontsize=8)
    ax.set_title('Profili del condotto e tratto dritto della ventola')
    fig.tight_layout()
    fig.savefig(folder/'profili_tubi.svg', format='svg')
    plt.close(fig)
    files.append('profili_tubi.svg')

    # convergenza della fascia
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2))
    for n in names:
        rows = [r for r in _history(variants[n]) if 'errore' not in r]
        if not rows:
            continue
        it = [r['iterazione'] for r in rows]
        axs[0].plot(it, [1e3*r['L_disk_m'] for r in rows], 'o-', color=COLORS[n], label=f'{label[n]}: L_disk usato')
        axs[0].plot(it, [1e3*r['L_disk_nuovo_m'] for r in rows], 's--', color=COLORS[n], alpha=0.6,
                    label=f'{label[n]}: richiesto dalla ventola')
        axs[1].plot(it, [r['dp_Pa'] for r in rows], 'o-', color=COLORS[n], label=label[n])
    axs[0].set_ylabel('L_disk [mm]')
    axs[1].set_ylabel('Δp assiale del venturi [Pa]')
    for ax in axs:
        ax.set_xlabel('passata')
        ax.xaxis.get_major_locator().set_params(integer=True)
        ax.grid(True, ls=':', alpha=0.6)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8)
    fig.suptitle('Ciclo sulla fascia della ventola')
    fig.tight_layout()
    fig.savefig(folder/'fascia_iterazioni.svg', format='svg')
    plt.close(fig)
    files.append('fascia_iterazioni.svg')
    return files


def _xlsx(table, variants, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    def header(ws, cols):
        for c, k in enumerate(cols, 1):
            cell = ws.cell(row=1, column=c, value=k)
            cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
            ws.column_dimensions[cell.column_letter].width = 18 if c > 1 else 40
        ws.freeze_panes = 'A2'

    wb = Workbook()
    ws = wb.active
    ws.title = 'Confronto'
    header(ws, ['voce', 'gruppo', 'unità', 'Statore', 'NoStatore', 'Δ assoluto', 'Δ %'])
    for r, row in enumerate(table, 2):
        for c, v in enumerate((row['voce'], row['gruppo'], row['unita'], row['Statore'], row['NoStatore'],
                               row.get('delta'), row.get('delta_pct')), 1):
            ws.cell(row=r, column=c, value=v)
    ws = wb.create_sheet('Fascia')
    header(ws, ['variante', 'passata', 'L_disk [mm]', 'monte [mm]', 'valle [mm]', 'L_disk nuovo [mm]',
                'Δp [Pa]', 'L tubo [mm]', 'D ventola [mm]', 'convergito', 'errore'])
    r = 2
    for n in NAMES:
        for row in _history(variants.get(n, {})):
            vals = [n, row.get('iterazione'), 1e3*row['L_disk_m'],
                    1e3*row['monte_m'] if 'monte_m' in row else None,
                    1e3*row['valle_m'] if 'valle_m' in row else None,
                    1e3*row['L_disk_nuovo_m'] if 'L_disk_nuovo_m' in row else None,
                    row.get('dp_Pa'), row.get('L_tubo_mm'), row.get('D_ventola_mm'),
                    row.get('convergito'), row.get('errore')]
            for c, v in enumerate(vals, 1):
                ws.cell(row=r, column=c, value=v)
            r += 1
    wb.save(path)


def _history(summary):
    f = summary.get('fascia')
    return (f.get('storia') if isinstance(f, dict) else f) or []


def _fmt(x, dec):
    return '—' if x is None else (f'{x:.{dec}f}' if isinstance(x, (int, float)) else str(x))


def _markdown(table, variants, pros, cons, files):
    L = ['# Confronto con e senza statore', '',
         'Due catene complete (venturi → ventola → sistema), ciascuna con la fascia della ventola '
         'adattata al proprio ingombro. **Senza statore la ventola riprogetta il rotore** '
         '(il Δp assiale non include lo swirl recuperato): non è il confronto a rotore fisso di '
         '`4_sistema` ma due progetti distinti. Potenze all\'albero per ugello.', '']
    for n in NAMES:
        s = variants.get(n, {})
        if not s.get('presente'):
            L.append(f"- **{n} non disponibile:** {s.get('motivo', 'variante assente')}")
        else:
            f = s['fascia']
            state = ('storia della fascia assente (fascia.json mancante)' if f['convergito'] is None else
                     'convergita' if f['convergito'] else '**NON convergita** (risultati tenuti)')
            L.append(f"- {n}: fascia {f['L_disk_mm']:.2f} mm in {f['iterazioni']} passate, {state}; "
                     f"rotore {s['ventola']['profilo_rotore']} a {s['ventola']['pale_rotore']} pale")
            L += [f'  - nota: {x}' for x in s.get('note', [])]
    L.append('')
    if pros or cons:
        L += ['## Senza statore: vantaggi e svantaggi', '']
        L += [f'- vantaggio: {x}' for x in pros] + [f'- svantaggio: {x}' for x in cons] + ['']
    group = None
    for r in table:
        if r['gruppo'] != group:
            group = r['gruppo']
            L += ['', f'## {group.capitalize()}', '', '| voce | unità | con statore | senza statore | Δ | Δ % |',
                  '|---|---|---|---|---|---|']
        d = r['decimali']
        L.append(f"| {r['voce']} | {r['unita']} | {_fmt(r['Statore'], d)} | {_fmt(r['NoStatore'], d)} | "
                 f"{_fmt(r.get('delta'), d)} | {_fmt(r.get('delta_pct'), 1)} |")
    L += ['', '## Come leggere il bilancio', '',
          '- getto utile = Q · p0 all\'uscita (da `risultati.json`); perdite del condotto = Q · perdita totale '
          '(bocca d\'imbocco del CAD esclusa);',
          '- swirl perso: senza statore tutto lo swirl esce col getto; con lo statore è quello residuo '
          'del confronto a rotore fisso di `4_sistema`;',
          '- il **residuo** è quanto i due modelli non chiudono (Δp assiale del venturi contro Δp del '
          'rotore, swirl): deve restare piccolo, è riportato in % della potenza all\'albero.', '']
    for n in NAMES:
        b = (variants.get(n) or {}).get('bilancio')
        if b:
            L.append(f"- {n}: residuo {b['residuo_W']:+.3f} W = {b['residuo_pct_albero']:+.2f} % della potenza all'albero")
    L += ['', '## File', ''] + [f'- `{f}`' for f in ['confronto_statore.json', 'confronto_statore.xlsx'] + files]
    return '\n'.join(L) + '\n'


def run(case_root):
    """Scrive 5_confronto_statore/ del caso; ritorna la cartella."""
    root = Path(case_root)
    out = root/OUT
    out.mkdir(parents=True, exist_ok=True)
    variants = {n: summarise(root/n) for n in NAMES}
    table = build_table(variants)
    pros, cons = verdict(table, variants)
    files = _plots(variants, out)
    clean = {n: {k: v for k, v in s.items() if k != 'profilo'} for n, s in variants.items()}
    sintesi = [f'vantaggio: {x}' for x in pros] + [f'svantaggio: {x}' for x in cons]
    for n in NAMES:
        if not variants[n].get('presente'):
            sintesi.append(f"{n} non disponibile: {variants[n].get('motivo')}")
    (out/'confronto_statore.json').write_text(json.dumps(
        dict(varianti=clean, tabella=table, vantaggi_senza_statore=pros, svantaggi_senza_statore=cons,
             sintesi=sintesi, grafici=files), indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    (out/'RISULTATO.md').write_text(_markdown(table, variants, pros, cons, files), encoding='utf-8')
    _xlsx(table, variants, out/'confronto_statore.xlsx')
    return out
