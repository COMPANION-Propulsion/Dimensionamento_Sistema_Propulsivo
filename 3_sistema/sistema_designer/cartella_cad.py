"""
Cartella CAD chiara, per chi apre i file in SolidWorks (o in un altro CAD) senza conoscere la catena.

    <caso>/CAD/<variante>/        con le varianti Statore / NoStatore
    <caso>/CAD/                   senza varianti
        01_tubo.step              condotto (solido)
        02_rotore.step            mozzo + pale
        03_statore.step           pale fisse (solo con statore)
        04_assieme.step           tubo + rotore + statore
        speculari/                le stesse parti nella versione B (ugello che gira al contrario)
        stl/                      mesh STL di tutto
        solidworks/               versione per SolidWorks: parti nominate, AP214 e AP203, IGES
        LEGGIMI.txt               cosa e ogni file, unita, asse, quale aprire e, se manca qualcosa, perche
    <serie>/CAD/INDICE.txt        indice dei casi della serie

I file di calcolo restano dove sono (2_venturi/03_cad, 3_ventola/03_cad, 4_sistema/03_cad: li
leggono masse.py, fascia.py, assembly.py e la Dinamica): qui ci sono COPIE con nomi chiari.
Nessun calcolo: si legge cio che c'e. Una variante incompleta viene costruita lo stesso, con
i file che esistono, e il LEGGIMI.txt dice quali mancano e perche (fascia.json, report.json).

    build_chain(case_root, variant, chain_root)   copia + LEGGIMI.txt di una catena
    build_case(case_root)                         tutte le catene del caso + LEGGIMI.txt del caso
    write_series_index(series_root, case_roots)   <serie>/CAD/INDICE.txt
    rebuild(path)                                 serie, caso o catena gia calcolati
"""
import json
import re
import shutil
from pathlib import Path

VARIANTS = ('Statore', 'NoStatore')
CAD_DIR = 'CAD'

# chiave -> (cartella sorgente relativa alla catena, nome sorgente, nome nella cartella CAD, stl)
PIECES = (
    ('tubo', '2_venturi/03_cad', 'tubo', '01_tubo', False),
    ('rotore', '3_ventola/03_cad', 'ventola_A', '02_rotore', False),
    ('statore', '3_ventola/03_cad', 'statore_A', '03_statore', False),
    ('assieme', '4_sistema/03_cad', 'assieme_A', '04_assieme', False),
    ('rotore_B', '3_ventola/03_cad', 'ventola_B_speculare', '02_rotore_B', True),
    ('statore_B', '3_ventola/03_cad', 'statore_B_speculare', '03_statore_B', True),
    ('assieme_B', '4_sistema/03_cad', 'assieme_B', '04_assieme_B', True),
)
DESCRIPTION = {
    'tubo': 'condotto (tubo con bocca d\'imbocco e ugello), un solido',
    'rotore': 'rotore: mozzo + pale fuse in un solido, versione A',
    'statore': 'statore: mozzo fisso + pale fisse dopo il rotore, versione A',
    'assieme': 'assieme: tubo + rotore + statore insieme, versione A',
    'rotore_B': 'rotore speculare (versione B)',
    'statore_B': 'statore speculare (versione B)',
    'assieme_B': 'assieme con le parti speculari (versione B)',
}


def _json(path):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def is_chain_root(path):
    p = Path(path)
    return p.is_dir() and any((p/n).exists() for n in ('2_venturi', '3_ventola', 'fascia.json'))


def case_chains(case_root):
    """[(variante o None, cartella della catena)] del caso."""
    root = Path(case_root)
    found = [(v, root/v) for v in VARIANTS if is_chain_root(root/v)]
    if found:
        return found
    return [(None, root)] if is_chain_root(root) else []


def stator_expected(chain_root, variant):
    """True / False se la catena deve avere lo statore, None se non si sa."""
    if variant == 'Statore':
        return True
    if variant == 'NoStatore':
        return False
    rep = _json(Path(chain_root)/'3_ventola'/'00_sintesi'/'report.json')
    if rep:
        return bool((rep.get('input_case', {}).get('stator') or {}).get('enabled'))
    text = Path(chain_root, 'input_usato.py')
    if text.is_file():
        m = re.findall(r'"presente":\s*(True|False)', text.read_text(encoding='utf-8'))
        if m:
            return m[-1] == 'True'
    return None


def chain_state(chain_root, variant=None):
    """Stato del CAD di una catena, leggendo i file: nessun calcolo.

    Ritorna dict(sorgenti {chiave: Path}, mancano [chiave], problemi [str], avvisi [str],
    completa bool, statore bool o None, x_ventola_mm).
    """
    root = Path(chain_root)
    expected = stator_expected(root, variant)
    src = {}
    for key, folder, name, _, _ in PIECES:
        step = root/folder/f'{name}.step'
        if step.is_file():
            src[key] = step
    problems, warnings = [], []
    rows = _json(root/'fascia.json') or []
    # solo se l'ultima riga e un errore la catena si e fermata li (le righe d'errore seguite da
    # una passata riuscita sono i tentativi dell'adattamento del diametro della ventola)
    errors = [rows[-1]] if rows and rows[-1].get('errore') and rows[-1].get('esito') is None else []
    report = _json(root/'3_ventola'/'00_sintesi'/'report.json')
    cad = (report or {}).get('cad') or {}
    if errors:
        last = errors[-1]
        problems.append(f"catena interrotta alla passata {last.get('iterazione', '?')} "
                        f"(L_disk {1e3*float(last.get('L_disk_m', 0)):.1f} mm): {last['errore']}")
    if report is None:
        problems.append('ventola non eseguita: 3_ventola/00_sintesi/report.json assente')
    elif not report.get('best'):
        problems.append('la ventola non ha un progetto accettato: nessun CAD di rotore e statore')
    elif cad.get('errore'):
        problems.append(f"CAD della ventola non prodotto: {cad['errore']}")
    elif cad.get('status'):
        problems.append(f"CAD della ventola non prodotto: {cad['status']}")
    for w in cad.get('avvisi') or []:
        warnings.append(f'CAD ventola: {w}')
    if (cad.get('stator') or {}).get('avviso'):
        warnings.append(f"CAD ventola: {cad['stator']['avviso']}")
    if expected is None:
        expected = 'statore' in src
    need = ['tubo', 'rotore', 'rotore_B', 'assieme', 'assieme_B'] + (['statore', 'statore_B'] if expected else [])
    missing = [k for k in need if k not in src]
    if 'tubo' in missing and not any('2_venturi' in p for p in problems):
        problems.append('manca il CAD del condotto: 2_venturi/03_cad/tubo.step (venturi non eseguito o fallito)')
    if missing and not problems:
        problems.append('file mancanti senza un errore registrato: ' + ', '.join(missing))
    if {'assieme', 'assieme_B'} & set(missing) and not (set(missing) & {'rotore', 'statore'}):
        problems.append('assieme non costruito: vedi 4_sistema/00_sintesi/RISULTATO.md')
    elif {'assieme', 'assieme_B'} & set(missing):
        problems.append('assieme non costruito perche mancano le parti sopra (il passo "sistema" non e partito '
                        'o non ha trovato rotore/statore)')
    info = _json(root/'3_ventola'/'03_cad'/'CAD_info.json') or {}
    return dict(sorgenti=src, mancano=missing, problemi=problems, avvisi=warnings, completa=not missing,
                statore=expected, x_ventola_mm=info.get('fan_centre_x_mm'), root=root, variante=variant)


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def cad_path(case_root, variant):
    base = Path(case_root)/CAD_DIR
    return base/variant if variant else base


def _size(path):
    return f'{path.stat().st_size/2**20:.1f} MB'


def readme_text(case_name, state, dest, solidworks):
    v = state['variante']
    title = f'CAD del caso {case_name}' + (f', variante {v}' if v else '')
    sw = ('con statore' if state['statore'] else 'senza statore' if state['statore'] is False
          else 'statore non noto')
    L = [title, '=' * len(title), '', f'Stato: {"COMPLETA" if state["completa"] else "INCOMPLETA"} ({sw}).', '']
    if not state['completa']:
        L += ['QUESTA VARIANTE E INCOMPLETA.', 'File che mancano: ' + ', '.join(
              f'{n}.step' for k, _, _, n, _ in PIECES if k in state['mancano']) + '.', 'Perche:']
        L += [f'  - {p}' for p in state['problemi']] + ['']
    if state['avvisi']:
        L += ['Avvisi:'] + [f'  - {w}' for w in state['avvisi']] + ['']
    L += ['UNITA E RIFERIMENTO (uguali per tutti i file)',
          '  - Unita: millimetri (mm).',
          '  - Asse X = asse del condotto, il flusso va verso +X. Origine: x = 0 al piano d\'ingresso '
          'del condotto, sull\'asse (y = z = 0); la bocca d\'imbocco arrotondata sporge a monte (x < 0).']
    if state['x_ventola_mm'] is not None:
        L += [f'  - La ventola e gia al suo posto: centro a x = {state["x_ventola_mm"]:.2f} mm. '
              'Tubo, rotore, statore e assieme si sovrappongono senza spostamenti.']
    L += ['  - Verso: rotore A visto da valle (guardando verso l\'ingresso) gira in senso orario; '
          'B (speculare) in senso antiorario, per l\'ugello vicino che gira al contrario.',
          '  - Il diametro delle pale nel CAD e il diametro di progetto meno 2 volte il gioco di punta '
          '(0,5 mm per lato di default). Mozzo cilindrico senza ogiva ne attacco albero.', '',
          'FILE DI QUESTA CARTELLA']
    for key, _, _, new, is_b in PIECES:
        where = f'speculari/{new}.step' if is_b else f'{new}.step'
        if key in state['sorgenti']:
            L.append(f'  {where:<34} {DESCRIPTION[key]} ({_size(state["sorgenti"][key])})')
        elif key.startswith('statore') and state['statore'] is False:
            L.append(f'  {where:<34} non c\'e: questa variante non ha lo statore')
        else:
            L.append(f'  {where:<34} MANCA: {DESCRIPTION[key]}')
    L += ['  stl/                               le stesse parti come mesh STL (per CFD, stampa 3D, anteprime)',
          '  solidworks/                        versione pensata per SolidWorks (vedi sotto)', '',
          'QUALE APRIRE IN SOLIDWORKS']
    if solidworks.get('ok'):
        L += ['  1. solidworks/04_assieme_A_AP214.step: assieme con i componenti nominati '
              '(tubo, rotore_A, statore_A); oppure le parti singole 02_rotore_A_AP214.step, '
              '03_statore_A_AP214.step.',
              '  2. Se non si apre: gli stessi file con _AP203 (schema piu vecchio e diffuso).',
              '  3. Se nessuno STEP si apre: i file .igs (IGES, solidi B-rep).',
              '  4. Le parti speculari B sono in solidworks/speculari/ (AP214 e AP203).',
              '  Dove SolidWorks lo chiede, scegliere di importare come SOLIDO (non solo superfici).',
              '  Differenza con i file 01..04 di questa cartella: stessa geometria, ma nomi di parte, '
              'AP214 o AP203 a scelta, mm dichiarati, senza curve sulle superfici (file piu leggeri).']
        if solidworks.get('sezioni_rotore') is not None:
            L.append(f'  Sezioni delle pale: rotore {solidworks["sezioni_rotore"]}'
                     + (f', statore {solidworks["sezioni_statore"]}' if solidworks.get('sezioni_statore') else '')
                     + f' (tolleranza di semplificazione {solidworks["tolleranza_mm"]:g} mm; '
                     'dettagli in solidworks/INFO_solidworks.json).')
    else:
        L += ['  La versione per SolidWorks non e stata scritta: ' + (solidworks.get('motivo') or 'non richiesta')
              + '.', '  Provare i file 01..04 di questa cartella.']
    L += ['', 'ALTRI FILE (restano nelle cartelle di calcolo)',
          '  2_venturi/03_cad: dominio del fluido (fluido.step), profilo.dxf/csv; 3_ventola/03_cad: una pala '
          'sola (pala.step), CAD_info.json con volumi e controlli di ogni parte; '
          '4_sistema/03_cad: assiemi originali.', '']
    return '\n'.join(L)


def build_chain(case_root, variant, chain_root, solidworks=True, log=print):
    """Costruisce <caso>/CAD/<variante>/ dai file esistenti; ritorna lo stato (chain_state)."""
    state = chain_state(chain_root, variant)
    dest = cad_path(case_root, variant)
    if dest.exists():
        shutil.rmtree(dest)         # solo la cartella CAD di questa variante, ricostruita da capo
    dest.mkdir(parents=True)
    for key, _, _, new, is_b in PIECES:
        if key not in state['sorgenti']:
            continue
        step = state['sorgenti'][key]
        _copy(step, dest/('speculari' if is_b else '.')/f'{new}.step')
        stl = step.with_suffix('.stl')
        if stl.is_file():
            _copy(stl, dest/'stl'/f'{new}.stl')
    sw = dict(ok=False, motivo='non richiesta')
    if solidworks:
        if not ({'rotore', 'rotore_B'} <= set(state['sorgenti'])):
            sw['motivo'] = 'manca il CAD del rotore'
        else:
            try:
                from ventola_designer.cad_solidworks import build_solidworks
                data = build_solidworks(chain_root, dest/'solidworks', log=log)
                sw = dict(ok=True, **{k: data.get(k) for k in ('sezioni_rotore', 'sezioni_statore',
                                                              'tolleranza_mm')})
                state['avvisi'] += [f'solidworks: {e}' for e in data.get('errori', [])]
                if data.get('avviso'):
                    state['avvisi'].append(f"solidworks: {data['avviso']}")
            except Exception as exc:         # il CAD di progetto resta: la versione SW e un di piu
                sw['motivo'] = str(exc)
                state['avvisi'].append(f'versione SolidWorks non scritta: {exc}')
                log(f'  AVVISO versione SolidWorks di {variant or "catena"}: {exc}')
    name = Path(case_root).name
    (dest/'LEGGIMI.txt').write_text(readme_text(name, state, dest, sw), encoding='utf-8-sig')
    return state


def build_case(case_root, solidworks=True, log=print):
    """CAD di tutte le catene del caso + <caso>/CAD/LEGGIMI.txt. Ritorna [stato]."""
    root = Path(case_root)
    states = []
    for variant, chain_root in case_chains(root):
        log(f'  CAD {root.name}' + (f'/{variant}' if variant else ''))
        states.append(build_chain(root, variant, chain_root, solidworks, log))
    if any(s['variante'] for s in states):
        write_case_readme(root, states)
    return states


def _status_line(state):
    if state['completa']:
        return 'completa'
    return 'INCOMPLETA - ' + '; '.join(state['problemi'][:2])


def write_case_readme(case_root, states):
    root = Path(case_root)
    L = [f'CAD del caso {root.name}', '=' * (11 + len(root.name)), '',
         'Una cartella per variante; in ognuna c\'e un LEGGIMI.txt con i dettagli.', '']
    for s in states:
        L.append(f'  {s["variante"]}/  {_status_line(s)}')
    L += ['', 'Unita: mm. Asse X lungo il flusso, x = 0 all\'ingresso del condotto.', '']
    (root/CAD_DIR/'LEGGIMI.txt').write_text('\n'.join(L), encoding='utf-8-sig')


def write_series_index(series_root, case_roots):
    """<serie>/CAD/INDICE.txt: i casi, lo stato del CAD di ogni variante e dove sta."""
    root = Path(series_root)
    L = [f'Indice del CAD della serie {root.name}', '=' * (27 + len(root.name)), '',
         'Per ogni caso: <caso>/CAD/<variante>/ (LEGGIMI.txt dentro). Unita: mm.', '']
    incomplete = 0
    for case in case_roots:
        case = Path(case)
        L.append(case.name)
        chains = case_chains(case)
        if not chains:
            L.append('    nessuna catena calcolata (cartelle 2_venturi/3_ventola assenti)')
        for variant, chain_root in chains:
            state = chain_state(chain_root, variant)
            incomplete += not state['completa']
            where = f'{case.name}/{CAD_DIR}/{variant}' if variant else f'{case.name}/{CAD_DIR}'
            L.append(f'    {variant or "(catena unica)"}: {_status_line(state)}')
            L.append(f'        {where}')
            for p in state['problemi'] if not state['completa'] else []:
                L.append(f'        perche: {p}')
        L.append('')
    L.insert(4, f'Casi: {len(list(case_roots))}; varianti incomplete: {incomplete}.')
    L.insert(5, '')
    out = root/CAD_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out/'INDICE.txt').write_text('\n'.join(L), encoding='utf-8-sig')
    return out/'INDICE.txt'


def find_cases(path):
    """('serie' | 'caso', [cartelle dei casi]) per una cartella gia calcolata."""
    p = Path(path)
    if p.name in VARIANTS and is_chain_root(p) and is_chain_root(p.parent) is False:
        p = p.parent
    if case_chains(p):
        return 'caso', [p]
    cases = [d for d in sorted(p.iterdir()) if d.is_dir() and d.name != CAD_DIR and case_chains(d)]
    if cases:
        return 'serie', cases
    raise ValueError(f'{p}: non e una serie ne un caso calcolato (mancano 2_venturi, 3_ventola, Statore/NoStatore)')


def rebuild(path, solidworks=True, log=print):
    """Ricostruisce la cartella CAD (e l'indice se e una serie) dai risultati esistenti."""
    kind, cases = find_cases(path)
    states = {}
    for case in cases:
        states[case] = build_case(case, solidworks, log)
    if kind == 'serie':
        index = write_series_index(path, cases)
        log(f'Indice: {index}')
    return kind, states
