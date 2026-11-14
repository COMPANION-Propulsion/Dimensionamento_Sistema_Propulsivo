"""
CAD per SolidWorks (e altri CAD) nelle cartelle degli step: nessuna cartella CAD nella radice.

I file CAD di ogni catena stanno solo nelle cartelle 03_cad dei rispettivi step:

    2_venturi/03_cad/    tubo.step/.stl (condotto), fluido*.step/.stl, profilo.dxf/csv
    3_ventola/03_cad/    ventola_A / ventola_B_speculare, statore_A / statore_B_speculare,
                         pala.step, CAD_info.json
    4_sistema/03_cad/    assieme_A / assieme_B (tubo + rotore + statore)

Qui si aggiunge, dentro ognuna, la sottocartella solidworks/ (parti con nome, STEP AP214 e AP203,
IGES; le versioni B in solidworks/speculari/) e un LEGGIMI.txt breve in italiano:

    tubo               -> 2_venturi/03_cad/solidworks/
    rotore, statore    -> 3_ventola/03_cad/solidworks/
    assieme            -> 4_sistema/03_cad/solidworks/

Nessun calcolo: si legge cio che c'e (la versione SolidWorks si ricostruisce dai risultati
esistenti, vedi ventola_designer/cad_solidworks.py). Le informazioni su una variante incompleta
(cosa manca e perche) le scrive RIEPILOGO.md del caso, che usa chain_state.

    chain_state(chain_root, variant)         stato del CAD di una catena (solo lettura)
    build_chain(chain_root, variant)         solidworks/ + LEGGIMI.txt dei tre step di una catena
    build_case(case_root)                    tutte le catene del caso
    rebuild(path)                            serie, caso o catena gia calcolati
"""
import json
import re
from pathlib import Path

VARIANTS = ('Statore', 'NoStatore')

# chiave -> (cartella sorgente relativa alla catena, nome del file senza estensione)
PIECES = (
    ('tubo', '2_venturi/03_cad', 'tubo'),
    ('rotore', '3_ventola/03_cad', 'ventola_A'),
    ('statore', '3_ventola/03_cad', 'statore_A'),
    ('assieme', '4_sistema/03_cad', 'assieme_A'),
    ('rotore_B', '3_ventola/03_cad', 'ventola_B_speculare'),
    ('statore_B', '3_ventola/03_cad', 'statore_B_speculare'),
    ('assieme_B', '4_sistema/03_cad', 'assieme_B'),
)
STEP_OF = {'tubo': '2_venturi', 'rotore': '3_ventola', 'statore': '3_ventola', 'assieme': '4_sistema',
           'rotore_B': '3_ventola', 'statore_B': '3_ventola', 'assieme_B': '4_sistema'}


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
    for key, folder, name in PIECES:
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


# ---------------------------------------------------------------------------
# LEGGIMI.txt dei tre step
# ---------------------------------------------------------------------------

def _units(state):
    L = ['Unita: millimetri (mm). Asse X = asse del condotto, il flusso va verso +X.',
         "Origine: x = 0 al piano d'ingresso del condotto, sull'asse (y = z = 0); la bocca "
         "d'imbocco arrotondata sporge a monte (x < 0)."]
    if state['x_ventola_mm'] is not None:
        L.append(f'La ventola e gia al suo posto (centro a x = {state["x_ventola_mm"]:.2f} mm): '
                 'tubo, rotore, statore e assieme si sovrappongono senza spostamenti.')
    return L


def _file_line(folder, state, key, text):
    """Una riga per un file del 03_cad; MANCA se la catena doveva averlo e non c'e."""
    step = next(n for k, _, n in PIECES if k == key)
    if key in state['sorgenti']:
        return f'  {step + ".step / .stl":<34} {text}'
    if key.startswith('statore') and state['statore'] is False:
        return f"  {step + '.step':<34} non c'e: questa variante non ha lo statore"
    return f'  {step + ".step":<34} MANCA: {text}'


def readme_step(step, state, sw, case_name):
    """Testo del LEGGIMI.txt di 2_venturi/03_cad, 3_ventola/03_cad o 4_sistema/03_cad."""
    v = state['variante']
    title = f'CAD - {case_name}' + (f' / {v}' if v else '') + f' - {step}'
    L = [title, '=' * len(title), '']
    if not state['completa']:
        L += ['ATTENZIONE: questa catena e INCOMPLETA: il motivo e i file che mancano sono nel',
              'RIEPILOGO.md del caso.', '']
    L += _units(state) + ['']
    sw_ok = sw.get('ok')
    if step == '2_venturi':
        L += ['FILE', _file_line(step, state, 'tubo', "condotto (tubo con bocca d'imbocco e ugello), un solido"),
              '  fluido.step / .stl                 dominio del fluido (per CFD), zona_disco.*',
              '  profilo.dxf / profilo.csv          profilo del condotto (sezione)', '',
              'IN SOLIDWORKS']
        L += (['  Aprire solidworks/tubo_AP214.step. Se non si apre: solidworks/tubo_AP203.step; '
               'poi solidworks/tubo.igs (IGES).'] if sw_ok else _no_sw(sw, 'tubo.step'))
    elif step == '3_ventola':
        L += ['FILE', _file_line(step, state, 'rotore', 'rotore A: mozzo + pale fuse in un solido'),
              _file_line(step, state, 'statore', 'statore A: mozzo fisso + pale fisse dopo il rotore'),
              _file_line(step, state, 'rotore_B', 'rotore speculare B (ugello che gira al contrario)'),
              _file_line(step, state, 'statore_B', 'statore speculare B'),
              '  pala.step / .stl                   una pala sola; CAD_info.json: volumi e controlli', '',
              'Verso: il rotore A visto da valle gira in senso orario, il B (speculare) in senso '
              'antiorario. Il diametro delle pale e quello di progetto meno 2 volte il gioco di punta '
              '(0,5 mm per lato di default). Mozzo cilindrico, senza ogiva ne attacco albero.', '',
              'IN SOLIDWORKS']
        L += (['  Aprire solidworks/rotore_A_AP214.step e solidworks/statore_A_AP214.step '
               '(AP203 e IGES come ripiego). Le parti speculari B sono in solidworks/speculari/.']
              if sw_ok else _no_sw(sw, 'ventola_A.step'))
        if sw_ok and sw.get('sezioni_rotore') is not None:
            L.append(f'  Sezioni delle pale: rotore {sw["sezioni_rotore"]}'
                     + (f', statore {sw["sezioni_statore"]}' if sw.get('sezioni_statore') else '')
                     + f' (tolleranza {sw["tolleranza_mm"]:g} mm; dettagli in solidworks/INFO_solidworks.json).')
    else:
        L += ['FILE', _file_line(step, state, 'assieme', 'assieme A: tubo + rotore + statore'),
              _file_line(step, state, 'assieme_B', 'assieme B, con le parti speculari'), '',
              'IN SOLIDWORKS']
        L += (['  Aprire solidworks/assieme_A_AP214.step: assieme con i componenti nominati '
               '(tubo, rotore_A, statore_A). Se non si apre: assieme_A_AP203.step, poi assieme_A.igs.',
               '  La versione B e in solidworks/speculari/.'] if sw_ok else _no_sw(sw, 'assieme_A.step'))
    if sw_ok:
        L += ['  Scegliere di importare come SOLIDO (non solo superfici).',
              '  Rispetto agli altri file di questa cartella: stessa geometria, ma con nomi di parte, '
              'mm dichiarati, AP214 o AP203 a scelta, senza curve sulle superfici (file piu leggeri).']
    L.append('')
    return '\n'.join(L)


def _no_sw(sw, fallback):
    return ['  La versione per SolidWorks non e stata scritta: ' + (sw.get('motivo') or 'non richiesta') + '.',
            f'  Provare {fallback} di questa cartella.']


def build_chain(chain_root, variant=None, solidworks=True, log=print):
    """solidworks/ e LEGGIMI.txt nei 03_cad di una catena; ritorna lo stato (chain_state)."""
    root = Path(chain_root)
    state = chain_state(root, variant)
    sw = dict(ok=False, motivo='non richiesta')
    if not solidworks and (root/'3_ventola'/'03_cad'/'solidworks').is_dir():
        sw = dict(ok=True)         # versione SolidWorks scritta in precedenza: resta com'e
    if solidworks:
        if not ({'rotore', 'rotore_B'} <= set(state['sorgenti'])):
            sw['motivo'] = 'manca il CAD del rotore'
        else:
            try:
                from ventola_designer.cad_solidworks import build_solidworks
                data = build_solidworks(root, log=log)
                sw = dict(ok=True, **{k: data.get(k) for k in ('sezioni_rotore', 'sezioni_statore',
                                                              'tolleranza_mm')})
                state['avvisi'] += [f'solidworks: {e}' for e in data.get('errori', [])]
                if data.get('avviso'):
                    state['avvisi'].append(f"solidworks: {data['avviso']}")
            except Exception as exc:         # il CAD di progetto resta: la versione SW e un di piu
                sw['motivo'] = str(exc)
                state['avvisi'].append(f'versione SolidWorks non scritta: {exc}')
                log(f'  AVVISO versione SolidWorks di {variant or "catena"}: {exc}')
    name = root.parent.name if variant else root.name
    for step in ('2_venturi', '3_ventola', '4_sistema'):
        cad = root/step/'03_cad'
        if cad.is_dir():
            (cad/'LEGGIMI.txt').write_text(readme_step(step, state, sw, name), encoding='utf-8-sig')
    return state


def build_case(case_root, solidworks=True, log=print):
    """solidworks/ + LEGGIMI.txt di tutte le catene del caso. Ritorna [stato]."""
    root = Path(case_root)
    states = []
    for variant, chain_root in case_chains(root):
        log(f'  CAD {root.name}' + (f'/{variant}' if variant else ''))
        states.append(build_chain(chain_root, variant, solidworks, log))
    return states


def find_cases(path):
    """('serie' | 'caso', [cartelle dei casi]) per una cartella gia calcolata."""
    p = Path(path)
    if p.name in VARIANTS and is_chain_root(p) and is_chain_root(p.parent) is False:
        p = p.parent
    if case_chains(p):
        return 'caso', [p]
    cases = [d for d in sorted(p.iterdir()) if d.is_dir() and case_chains(d)]
    if cases:
        return 'serie', cases
    raise ValueError(f'{p}: non e una serie ne un caso calcolato (mancano 2_venturi, 3_ventola, Statore/NoStatore)')


def rebuild(path, solidworks=True, log=print):
    """Rigenera solidworks/ e i LEGGIMI.txt dai risultati esistenti (nessun calcolo)."""
    kind, cases = find_cases(path)
    states = {}
    for case in cases:
        states[case] = build_case(case, solidworks, log)
    return kind, states
