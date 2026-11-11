"""
Sequenza del sistema (condotto + ventola) e RISULTATO.md in risultati/<caso>/4_sistema/.

    00_sintesi/    RISULTATO.md, potenza_manovra.json, confronto_statore.json, curva_potenza.json
    01_grafici/    potenza_manovra, curva_potenza, confronto_statore, rotore/statore lungo il
                   raggio, condotto con la ventola vera, viste 3D dell'assieme
    02_excel/      curva_potenza.xlsx, pale_lungo_raggio.xlsx
    03_cad/        assieme_A e assieme_B (tubo + rotore + statore), STEP e STL
    04_cfd/        condotto_con_ventola 2D e 3D, pale_rotore.vtp, pale_statore.vtp, tubo.vtp,
                   sistema.pvd (tutto insieme in ParaView)

Ogni passo che fallisce viene annotato in RISULTATO.md e non ferma gli altri.
"""
import json
import shutil
import traceback
from pathlib import Path

from .data import FOLDERS, Case
from . import assembly, mission_power, note, spanwise, stator_compare


def _xlsx(rotor, stator, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    for title, rows in (('Rotore', rotor), ('Statore', stator)):
        ws = wb.active if title == 'Rotore' else wb.create_sheet(title)
        ws.title = title
        if not rows:
            ws['A1'] = 'nessuno statore'
            continue
        keys = list(rows[0])
        for c, k in enumerate(keys, 1):
            cell = ws.cell(row=1, column=c, value=k)
            cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
            ws.column_dimensions[cell.column_letter].width = 16
        for r, row in enumerate(rows, 2):
            for c, k in enumerate(keys, 1):
                ws.cell(row=r, column=c, value=row[k])
        ws.freeze_panes = 'A2'
    wb.save(path)


def run(case_root, p_max=None, verbose=True, p_cabin=None):
    case = Case(Path(case_root))
    if case.out.exists():
        shutil.rmtree(case.out)
    for f in FOLDERS:
        case.folder(f)
    log = {}

    def step(name, fn):
        if verbose:
            print(f'  {name}...', flush=True)
        try:
            log[name] = fn()
        except Exception as exc:            # un passo fallito non ferma gli altri
            log[name] = None
            log.setdefault('errori', []).append(f'{name}: {exc}')
            if verbose:
                print(f'    ERRORE: {exc}', flush=True)
                traceback.print_exc()

    from ventola_designer.power_curve import export_power_curve
    from venturi_designer.analysis.fan_coupled import solve_with_fan

    point = case.fan_point()
    design = case.fan['best']['design']
    R = design['outer_diameter_m']/2
    step('curva di potenza', lambda: export_power_curve(case.fan_dir, case.venturi_file, p_max,
                                                        out_dir=case.out))
    step('potenza nella manovra', lambda: mission_power.export(case, log.get('curva di potenza')))
    step('confronto statore', lambda: stator_compare.export(case))
    rotor, stator = spanwise.rotor_rows(point, design), spanwise.stator_rows(point)
    step('pale lungo il raggio', lambda: [
        spanwise.plot_rotor(rotor, design, case.folder('01_grafici')/'rotore_lungo_raggio.svg'),
        spanwise.plot_stator(stator, case.folder('01_grafici')/'statore_lungo_raggio.svg'),
        _xlsx(rotor, stator, case.folder('02_excel')/'pale_lungo_raggio.xlsx')])
    step('condotto con la ventola vera', lambda: solve_with_fan(
        str(case.design_file), [x['r_m']/R for x in point['local']],
        [x['axial_total_pressure_rise_Pa'] for x in point['local']],
        design['hub_diameter_m']/design['outer_diameter_m'],
        str(case.folder('04_cfd')), str(case.folder('01_grafici'))))
    step('assieme CAD', lambda: assembly.assembly_cad(case))
    step('viste 3D', lambda: assembly.views(case))
    step('ParaView', lambda: assembly.paraview(case, point))
    step('note e limiti', lambda: note.export(case, p_cabin, log.get('potenza nella manovra'),
                                              log.get('condotto con la ventola vera')))
    path = case.folder('00_sintesi')/'RISULTATO.md'
    path.write_text(report(case, point, log), encoding='utf-8')
    return log


def report(case, point, log):
    m, cmp, cpl, curve = (log.get(k) for k in ('potenza nella manovra', 'confronto statore',
                                               'condotto con la ventola vera', 'curva di potenza'))
    L = ['# Sistema: condotto + ventola', '']
    if m:
        L += ['## Quando la ventola consuma, e quanto', '',
              '| fase | tempo [s] | faccia | potenza all\'albero [W] |', '|---|---|---|---|']
        L += [f"| {p['fase']} | {p['da_s']:.2f} → {p['a_s']:.2f} | {p['faccia']} | {p['potenza_faccia_W']:.3f} |"
              for p in m['fasi']]
        L += ['', f"- **picco {m['picco_W']:.3f} W** = {m['ugelli_per_faccia']} ugelli × "
                  f"{m['potenza_ugello_W']:.3f} W, a {m['rpm']:.0f} rpm, per "
                  f"{m['tempo_con_motori_accesi_s']:.2f} s su {m['durata_manovra_s']:g}",
              f"- energia della manovra {m['energia_manovra_J']:.2f} J ({1000*m['energia_manovra_Wh']:.2f} mWh), "
              f"media {m['potenza_media_W']:.3f} W",
              '- potenza all\'albero: quella elettrica è più alta del rendimento di motore e regolatore',
              '- grafico: `01_grafici/potenza_manovra.svg`', '']
        d = m.get('con_disturbo')
        if d:
            L += ['### Manovra e disturbo separati (senza margine)', '',
                  f"Disturbo residuo {d['disturbo_residuo_g']:g} g contrario al moto: la manovra chiede "
                  f"{d['spinta_manovra_N']:.3f} N per faccia, il disturbo {d['spinta_disturbo_N']:.3f} N. "
                  f"Potenza da: {d['modello_potenza']}.", '',
                  '| fase | tempo [s] | faccia | spinta [N] | potenza all\'albero [W] |', '|---|---|---|---|---|']
            L += [f"| {p['fase']} | {p['da_s']:.2f} → {p['a_s']:.2f} | {p['faccia']} | {p['spinta_faccia_N']:.3f} | "
                  f"{p['potenza_faccia_W']:.3f} |" for p in d['fasi']]
            L += ['', f"- picco {d['picco_W']:.3f} W, energia {d['energia_J']:.2f} J, di cui "
                      f"{d['energia_del_disturbo_J']:.2f} J per il disturbo ({d['energia_senza_disturbo_J']:.2f} J senza)",
                  f"- tenere la posizione contro il solo disturbo costa {d['potenza_per_tenere_la_posizione_W']:.3f} W "
                  'per asse, per tutto il volo libero', '']
    if curve:
        last = curve['righe'][-1]
        L += ['## Curva di potenza', '',
              f"Condotto e pale fissi, giri variabili: da 0 a {last['potenza_albero_W']:.3f} W la spinta "
              f"dell'ugello va da 0 a {last['spinta_ugello_N']:.4g} N (progetto: "
              f"{curve['progetto']['potenza_albero_W']:.3f} W → {curve['progetto']['spinta_ugello_N']:.4g} N). "
              '`01_grafici/curva_potenza.svg`, `02_excel/curva_potenza.xlsx`.', '']
    if cmp:
        L += ['## Con o senza statore (stesso Δp, rotore fisso)', '',
              '| | giri [rpm] | potenza [W] | coppia netta [mN·m] | attrito statore [Pa] | swirl perso [Pa] |',
              '|---|---|---|---|---|---|']
        for r in cmp['varianti']:
            name = 'con statore' if r['statore'] else 'senza statore'
            if 'errore' in r:
                L.append(f"| {name} | — | — | — | — | {r['errore']} |")
            else:
                L.append(f"| {name} | {r['rpm']:.0f} | {r['potenza_albero_W']:.3f} | "
                         f"{1e3*r['coppia_netta_Nm']:.3f} | {r['perdita_statore_Pa']:.2f} | {r['swirl_perso_Pa']:.2f} |")
        if 'differenza_potenza_pct' in cmp:
            better = 'meno' if cmp['conviene_statore_per_potenza'] else 'più'
            L += ['', f"Con lo statore la ventola consuma il {abs(cmp['differenza_potenza_pct']):.1f} % "
                      f"{better} potenza; la coppia netta sul veicolo è nella colonna dedicata. "
                      '`01_grafici/confronto_statore.svg`.']
        L += ['']
    if cpl:
        L += ['## Condotto con la ventola vera', '',
              f"Spinta {cpl['spinta_con_ventola_N']:.4g} N contro {cpl['spinta_disco_uniforme_N']:.4g} N "
              f"del disco uniforme ({cpl['scarto_spinta_pct']:+.1f} %), {cpl['celle_flusso_invertito']} celle con "
              f"flusso invertito, sforzo a parete minimo {cpl['tau_parete_min_Pa']:.3f} Pa "
              f"(negativo = separazione). Mappe `01_grafici/condotto_con_ventola_*.svg`.", '']
    if log.get('note e limiti'):
        L += note.markdown(log['note e limiti'])
    L += ['## File', '',
          '- `03_cad/assieme_A.step` e `assieme_B.step`: tubo + rotore + statore insieme (mm, asse X)',
          '- `01_grafici/vista_3d_assieme.png`, `vista_assiale_da_valle.png`, `vista_laterale_sezione.png`',
          '- `04_cfd/sistema.pvd`: in ParaView apre insieme campo 3D del condotto, pale di rotore e statore '
          '(colorate per incidenza, Reynolds, Δp, CL, perdite...) e tubo',
          '- `01_grafici/rotore_lungo_raggio.svg`, `statore_lungo_raggio.svg`, `02_excel/pale_lungo_raggio.xlsx`', '']
    if log.get('errori'):
        L += ['## Passi non riusciti', ''] + [f'- {e}' for e in log['errori']] + ['']
    return '\n'.join(L)
