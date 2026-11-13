"""
Stima della massa dai volumi dei CAD, per confrontare i casi.

Volume = volume geometrico del solido pieno (STL chiuso, somma dei tetraedri con segno);
massa = volume * densita * riempimento. Sono esclusi supporti, viti, motore ed elettronica.
Nessuna funzione solleva per un file mancante: il pezzo e None con una nota.

Funzioni pubbliche:
    stl_volume_m3(path)                      -> StlVolume(volume_m3, chiuso)
    tube_volume_from_design(design_json)     -> volume del tubo [m3] da un design.json
    masses_of_chain(chain_root, ...)         -> dict (pezzi, totale, alternative di lunghezza)
    write_mass_summary(case_root, ...)       -> RIEPILOGO_masse.xlsx / .json del caso
    write_series_summary(case_roots, path, labels, ...) -> confronto_casi.xlsx
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import NamedTuple, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DENSITA_PLA = 1240.0
VARIANTS = ('Statore', 'NoStatore')
PIECES = (('tubo', '2_venturi/03_cad/tubo.stl'),
          ('rotore', '3_ventola/03_cad/ventola_A.stl'),
          ('statore', '3_ventola/03_cad/statore_A.stl'))


class StlVolume(NamedTuple):
    volume_m3: float
    chiuso: bool


# ---------------------------------------------------------------------------
# STL
# ---------------------------------------------------------------------------
def _read_triangles(path):
    """Triangoli (n, 3, 3) di un STL ASCII o binario, nelle unita del file."""
    raw = Path(path).read_bytes()
    if len(raw) >= 84:
        n = int(np.frombuffer(raw, dtype='<u4', count=1, offset=80)[0])
        if len(raw) == 84 + 50*n:
            dt = np.dtype([('n', '<3f4'), ('v', '<9f4'), ('a', '<u2')])
            data = np.frombuffer(raw, dtype=dt, count=n, offset=84)
            return data['v'].astype(float).reshape(-1, 3, 3)
    vals = []
    for line in raw.decode('ascii', 'replace').splitlines():
        parts = line.split()
        if parts and parts[0].lower() == 'vertex':
            vals.append([float(x) for x in parts[1:4]])
    if len(vals) % 3:
        raise ValueError('STL ASCII con vertici non multipli di 3')
    return np.array(vals, dtype=float).reshape(-1, 3, 3)


def _is_closed(tris):
    """Ogni bordo condiviso da esattamente due triangoli (triangoli degeneri ignorati)."""
    flat = np.round(tris.reshape(-1, 3), 5)
    _, idx = np.unique(flat, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    idx = idx[(idx[:, 0] != idx[:, 1]) & (idx[:, 1] != idx[:, 2]) & (idx[:, 0] != idx[:, 2])]
    if not len(idx):
        return False
    edges = np.concatenate((idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]))
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.all(counts == 2))


def stl_volume_m3(path, unita_mm=True):
    """Volume [m3] di uno STL (di norma in mm) e se la superficie e chiusa."""
    tris = _read_triangles(path)
    vol = abs(float(np.einsum('ij,ij->i', tris[:, 0],
                              np.cross(tris[:, 1], tris[:, 2])).sum()))/6.0
    return StlVolume(vol*(1e-9 if unita_mm else 1.0), _is_closed(tris))


# ---------------------------------------------------------------------------
# Tubo da design.json
# ---------------------------------------------------------------------------
def _venturi_on_path():
    ven = str(ROOT/'1_venturi')
    if ven not in sys.path:
        sys.path.insert(0, ven)


def tube_volume_from_design(design_json):
    """Volume del tubo [m3] (parete con bocca e labbri, come tubo.stl) da un design.json."""
    _venturi_on_path()
    from venturi_designer.export.cad_duct import closed_mesh, sample, tube_pieces
    from venturi_designer.export.duct import cad_geometry
    from venturi_designer.optimization.shape_opt import DuctProblem
    from venturi_designer.optimization.target_thrust import load_design
    case, layout, design = load_design(str(design_json))
    geom = cad_geometry(DuctProblem(case, layout), design)
    pieces = tube_pieces(geom)
    r_tube = float(sample(pieces, 0.01, 1.0)[:, 1].max())
    tris = closed_mesh(pieces, r_tube)
    return abs(float(np.einsum('ij,ij->i', tris[:, 0],
                               np.cross(tris[:, 1], tris[:, 2])).sum()))/6.0*1e-9


# ---------------------------------------------------------------------------
# Catena
# ---------------------------------------------------------------------------
def _json(path):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _mass_g(volume_m3, densita, riempimento):
    return None if volume_m3 is None else volume_m3*densita*riempimento*1e3


def _piece(path, densita, riempimento, nome):
    out = dict(file=str(path), volume_mm3=None, massa_g=None, chiuso=None, nota=None)
    path = Path(path)
    if not path.is_file():
        out['nota'] = f'{nome}: file assente ({path.name})'
        return out
    try:
        v = stl_volume_m3(path)
    except Exception as exc:
        out['nota'] = f'{nome}: STL illeggibile ({exc})'
        return out
    out.update(volume_mm3=v.volume_m3*1e9, massa_g=_mass_g(v.volume_m3, densita, riempimento),
               chiuso=v.chiuso)
    if not v.chiuso:
        out['nota'] = f'{nome}: superficie STL non chiusa, volume indicativo'
    return out


def _alt_volume(chain, design_rel, cache):
    """(volume m3, nota) del tubo di un'alternativa; design_rel e relativo ad alternative/."""
    if not design_rel:
        return None, 'design.json non indicato'
    path = Path(chain)/'2_venturi'/'05_convergenza'/'alternative'/design_rel
    if not path.is_file():
        return None, f'{design_rel} assente'
    if path in cache:
        return cache[path], None
    try:
        cache[path] = tube_volume_from_design(path)
        return cache[path], None
    except Exception as exc:
        return None, f'volume da design.json non calcolabile ({exc})'


def _alternatives(chain, densita, riempimento, tubo, notes):
    conv = Path(chain)/'2_venturi'/'05_convergenza'
    alt = _json(conv/'alternative'/'alternative.json')
    if not alt or not alt.get('casi'):
        notes.append('alternative di lunghezza assenti (alternative.json)')
        return []
    cache, rows = {}, []
    ref = next((r for r in alt['casi'] if r.get('id') == 'ottimo'), None)
    vref, nref = _alt_volume(chain, (ref or {}).get('design_json'), cache)
    if vref is None and (conv/'design.json').is_file():
        try:
            vref, nref = tube_volume_from_design(conv/'design.json'), None
        except Exception as exc:
            nref = str(exc)
    if vref is None and tubo.get('volume_mm3') is not None:
        vref, nref = tubo['volume_mm3']*1e-9, 'volume dell\'ottimo da tubo.stl'
    mref = _mass_g(vref, densita, riempimento)
    pref = (ref or {}).get('potenza_W')
    for r in alt['casi']:
        v, nota = _alt_volume(chain, r.get('design_json'), cache)
        if r.get('id') == 'ottimo' and v is None and vref is not None:
            v = vref
        m = _mass_g(v, densita, riempimento)
        pw = r.get('potenza_W')
        dpot = r.get('delta_potenza_pct')
        if dpot is None and pw is not None and pref:
            dpot = 100*(pw/pref - 1)
        dm = None if (m is None or mref is None) else m - mref
        dm_pct = None if (dm is None or not mref) else 100*dm/mref
        g_pct = None
        if dm is not None and dpot is not None and dpot > 1e-9 and r.get('id') != 'ottimo':
            g_pct = (mref - m)/dpot
        if r.get('stato') not in (None, 'ok') and nota is None:
            nota = r.get('stato')
        rows.append(dict(id=r.get('id'), L_tubo_mm=r.get('L_tubo_mm'), dp_Pa=r.get('dp_Pa'),
                         potenza_W=pw, volume_mm3=None if v is None else v*1e9, massa_g=m,
                         delta_massa_g=dm, delta_massa_pct=dm_pct, delta_potenza_pct=dpot,
                         g_per_pct_potenza=g_pct, convergito=r.get('convergito'), nota=nota))
    return rows


def masses_of_chain(chain_root, densita_kg_m3=DENSITA_PLA, riempimento=1.0):
    """Volumi e masse [g] di tubo, rotore, statore e delle alternative di lunghezza."""
    chain = Path(chain_root)
    notes = []
    pieces = {}
    for nome, rel in PIECES:
        pieces[nome] = _piece(chain/rel, densita_kg_m3, riempimento, nome)
        if pieces[nome]['nota']:
            notes.append(pieces[nome]['nota'])
    have = [p for p in pieces.values() if p['massa_g'] is not None]
    if pieces['tubo']['massa_g'] is None or pieces['rotore']['massa_g'] is None:
        tot_v = tot_m = None
        notes.append('totale non calcolabile: manca tubo o rotore')
    else:
        tot_v = sum(p['volume_mm3'] for p in have)
        tot_m = sum(p['massa_g'] for p in have)
    try:
        alts = _alternatives(chain, densita_kg_m3, riempimento, pieces['tubo'], notes)
    except Exception as exc:
        alts = []
        notes.append(f'alternative non elaborabili ({exc})')
    return dict(radice=str(chain), densita_kg_m3=densita_kg_m3, riempimento=riempimento,
                tubo=pieces['tubo'], rotore=pieces['rotore'], statore=pieces['statore'],
                totale=dict(volume_mm3=tot_v, massa_g=tot_m),
                alternative=alts, note=notes)


# ---------------------------------------------------------------------------
# Grandezze di una catena (per i riepiloghi)
# ---------------------------------------------------------------------------
def chain_info(folder):
    """Grandezze principali di una catena; chiavi None se i file mancano."""
    folder = Path(folder)
    ven = _json(folder/'2_venturi'/'00_sintesi'/'risultati.json') or {}
    rep = _json(folder/'3_ventola'/'00_sintesi'/'report.json') or {}
    fascia = [r for r in (_json(folder/'fascia.json') or []) if 'errore' not in r]
    case = ((rep.get('best') or {}).get('cases') or [{}])[0]
    v, g = ven.get('ventola') or {}, ven.get('geometria') or {}
    cmp_ = _json(folder.parent/'5_confronto_statore'/'confronto_statore.json')
    shaft, torque = case.get('shaft_power_W'), None
    if case.get('net_torque_Nm') is not None:
        torque = 1e3*case['net_torque_Nm']
    sv = ((cmp_ or {}).get('varianti') or {}).get(folder.name) or {}
    if sv.get('presente'):
        shaft = (sv.get('ventola') or {}).get('potenza_albero_W', shaft)
        torque = (sv.get('ventola') or {}).get('coppia_netta_mNm', torque)
    return dict(
        L_disk_mm=1e3*fascia[-1]['L_disk_m'] if fascia else (
            1e3*v['L_ventola_m'] if 'L_ventola_m' in v else None),
        L_tubo_mm=g.get('L_tubo_mm'), dp_Pa=v.get('dp_disk_Pa'),
        D_ventola_mm=1e3*v['D_ventola_m'] if 'D_ventola_m' in v else None,
        potenza_albero_W=shaft, coppia_netta_mNm=torque)


def _variants(case_root):
    """[(nome, cartella)] delle catene del caso: Statore/NoStatore o la radice."""
    root = Path(case_root)
    named = [(n, root/n) for n in VARIANTS if (root/n).is_dir()]
    if named:
        return named
    return [('', root)]


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def _header(ws, cols, widths=None):
    from openpyxl.styles import Font, PatternFill
    for c, k in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c, value=k)
        cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
        ws.column_dimensions[cell.column_letter].width = (widths or {}).get(c, 18)
    ws.freeze_panes = 'A2'


def _r(x, d=3):
    return round(x, d) if isinstance(x, (int, float)) and not isinstance(x, bool) else x


ALT_COLS = ('id', 'L_tubo_mm', 'dp_Pa', 'potenza_W', 'volume_mm3', 'massa_g', 'delta_massa_g',
            'delta_massa_pct', 'delta_potenza_pct', 'g_per_pct_potenza', 'nota')


def _sheet_alternative(wb, chains, with_variant):
    from openpyxl.styles import Font, PatternFill
    ws = wb.create_sheet('Alternative')
    head = (['variante'] if with_variant else []) + [
        'id', 'L tubo [mm]', 'Δp [Pa]', 'potenza [W]', 'volume tubo [mm³]', 'massa tubo [g]',
        'Δ massa vs ottimo [g]', 'Δ massa [%]', 'Δ potenza [%]', 'g risparmiati per % di potenza',
        'nota']
    _header(ws, head, {1: 14, len(head): 50})
    r = 2
    for name, m in chains:
        for a in m['alternative']:
            vals = ([name] if with_variant else []) + [_r(a[k]) if k != 'nota' else a[k]
                                                         for k in ALT_COLS]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=c, value=v)
                if a['id'] == 'ottimo':
                    cell.font, cell.fill = Font(bold=True), PatternFill('solid', fgColor='FFF2CC')
            r += 1
    if r == 2:
        ws.cell(row=2, column=1, value='nessuna alternativa di lunghezza disponibile')


def _sheet_statore(wb, case_root, chains):
    ws = wb.create_sheet('Statore')
    cols = ['voce', 'massa tubo [g]', 'massa rotore [g]', 'massa statore [g]', 'massa totale [g]',
            'L_disk [mm]', 'L tubo [mm]', 'Δp [Pa]', 'potenza albero [W]', 'coppia netta [mN·m]']
    _header(ws, cols, {1: 28})
    vals, info = {}, {}
    for n, m in chains:
        i = chain_info(Path(case_root)/n)
        info[n] = i
        vals[n] = [m['tubo']['massa_g'], m['rotore']['massa_g'], m['statore']['massa_g'],
                   m['totale']['massa_g'], i['L_disk_mm'], i['L_tubo_mm'], i['dp_Pa'],
                   i['potenza_albero_W'], i['coppia_netta_mNm']]
    for r, n in enumerate(VARIANTS, 2):
        ws.cell(row=r, column=1, value=n)
        for c, v in enumerate(vals[n], 2):
            ws.cell(row=r, column=c, value=_r(v))
    text = None
    dm = dpw = dt = None
    a, b = vals['Statore'], vals['NoStatore']
    diff = [None if (x is None or y is None) else y - x for x, y in zip(a, b)]
    pct = [None if (d is None or not x) else 100*d/x for d, x in zip(diff, a)]
    ws.cell(row=4, column=1, value='NoStatore − Statore')
    ws.cell(row=5, column=1, value='NoStatore − Statore [%]')
    for c, (d, p) in enumerate(zip(diff, pct), 2):
        ws.cell(row=4, column=c, value=_r(d))
        ws.cell(row=5, column=c, value=_r(p, 2))
    dm, dpw, dt = diff[3], diff[7], diff[8]
    if dm is not None:
        text = f'togliendo lo statore: {dm:+.2f} g'
        text += f', {dpw:+.3f} W' if dpw is not None else ''
        text += f', {dt:+.3f} mN·m di coppia' if dt is not None else ''
        text = text.replace('-', '−')
    ws.cell(row=7, column=1, value=text or 'differenza non calcolabile (manca una variante)')
    return dict(righe={n: dict(zip(cols[1:], vals[n])) for n in VARIANTS},
                differenza=dict(zip(cols[1:], diff)), differenza_pct=dict(zip(cols[1:], pct)),
                testo=text)


def write_mass_summary(case_root, densita_kg_m3=DENSITA_PLA, riempimento=1.0):
    """Scrive RIEPILOGO_masse.xlsx e .json nel caso; ritorna il percorso dell'xlsx."""
    from openpyxl import Workbook
    root = Path(case_root)
    root.mkdir(parents=True, exist_ok=True)
    variants = _variants(root)
    chains = [(n, masses_of_chain(f, densita_kg_m3, riempimento)) for n, f in variants]
    two = [n for n, _ in chains] == list(VARIANTS)
    wb = Workbook()
    wb.remove(wb.active)
    _sheet_alternative(wb, chains, with_variant=bool(variants[0][0]))
    stat = _sheet_statore(wb, root, chains) if two else None
    ws = wb.create_sheet('Parametri')
    _header(ws, ['voce', 'valore'], {1: 34, 2: 90})
    rows = [('densità [kg/m³]', densita_kg_m3), ('riempimento', riempimento),
            ('metodo', 'volume dei CAD (STL, mm) x densità x riempimento; solido pieno'),
            ('non inclusi', 'supporti, viti, motore, elettronica')]
    for n, m in chains:
        for k in ('tubo', 'rotore', 'statore'):
            rows.append((f'file {k} {n}'.strip(), m[k]['file']))
        rows += [('nota ' + n, x) for x in m['note']]
    for r, (k, v) in enumerate(rows, 2):
        ws.cell(row=r, column=1, value=k)
        ws.cell(row=r, column=2, value=v)
    path = root/'RIEPILOGO_masse.xlsx'
    wb.save(path)
    (root/'RIEPILOGO_masse.json').write_text(json.dumps(
        dict(densita_kg_m3=densita_kg_m3, riempimento=riempimento,
             catene={n or 'catena': m for n, m in chains}, statore=stat),
        indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    return str(path)


def write_series_summary(case_roots, path, labels, densita_kg_m3=DENSITA_PLA, riempimento=1.0):
    """confronto_casi.xlsx: una riga per caso (foglio 'Casi'); ritorna il percorso."""
    from openpyxl import Workbook
    names = ('Statore', 'NoStatore')
    cols = ['caso', 'stato', 'spinta per ugello [N]', 'Δp [Pa]', 'D ventola [mm]', 'L tubo [mm]',
            'potenza albero [W]']
    mass_cols = []
    for n in names:
        mass_cols += [f'{n}: {k} [g]' for k in ('tubo', 'rotore', 'statore', 'totale')]
    simple = ['massa tubo [g]', 'massa rotore [g]', 'massa statore [g]', 'massa totale [g]']
    rows, notes = [], []
    for root, label in zip(case_roots, labels):
        root = Path(root)
        thrust = (_json(root/'1_spinta'/'spinta.json') or {}).get('T_ugello_N')
        row = dict(caso=label, stato='ok', spinta=thrust, chains={})
        if not root.is_dir():
            row['stato'] = 'cartella del caso assente'
        for n, f in _variants(root):
            m = masses_of_chain(f, densita_kg_m3, riempimento)
            row['chains'][n] = (chain_info(f), m)
        if row['stato'] == 'ok':
            ok = [i['L_tubo_mm'] is not None for i, _ in row['chains'].values()]
            if not any(ok):
                row['stato'] = 'fallito: catena senza risultati'
            elif not all(ok):
                row['stato'] = 'parziale: una variante senza risultati'
        rows.append(row)
    multi = any(n for r in rows for n in r['chains'])
    head = cols + (mass_cols if multi else simple)
    delta_head = [f'Δ {h} vs primo caso' for h in ('massa totale [g]', 'potenza albero [W]')]
    wb = Workbook()
    ws = wb.active
    ws.title = 'Casi'
    _header(ws, head + delta_head, {1: 18, 2: 34})
    first = {}
    for r, row in enumerate(rows, 2):
        chains = row['chains']
        main = chains.get('Statore') or next(iter(chains.values()), ({}, None))
        info = main[0]
        vals = [row['caso'], row['stato'], row['spinta'], info.get('dp_Pa'), info.get('D_ventola_mm'),
                info.get('L_tubo_mm'), info.get('potenza_albero_W')]
        if multi:
            for n in names:
                m = (chains.get(n) or (None, None))[1]
                vals += [None]*4 if m is None else [m['tubo']['massa_g'], m['rotore']['massa_g'],
                                                    m['statore']['massa_g'], m['totale']['massa_g']]
        else:
            m = main[1]
            vals += [None]*4 if m is None else [m['tubo']['massa_g'], m['rotore']['massa_g'],
                                                m['statore']['massa_g'], m['totale']['massa_g']]
        mm = (chains.get('Statore') or main)[1]
        tot = mm['totale']['massa_g'] if mm else None
        key = (tot, info.get('potenza_albero_W'))
        if r == 2:
            first = dict(zip(('m', 'p'), key))
        d_m = None if key[0] is None or first.get('m') is None else key[0] - first['m']
        d_p = None if key[1] is None or first.get('p') is None else key[1] - first['p']
        for c, v in enumerate(vals + [d_m, d_p], 1):
            ws.cell(row=r, column=c, value=_r(v))
    ws2 = wb.create_sheet('Parametri')
    _header(ws2, ['voce', 'valore'], {1: 30, 2: 80})
    for r, (k, v) in enumerate((('densità [kg/m³]', densita_kg_m3), ('riempimento', riempimento),
                                ('metodo', 'volume dei CAD x densità x riempimento'),
                                ('non inclusi', 'supporti, viti, motore, elettronica'),
                                ('delta', 'masse della variante Statore (o catena semplice)')), 2):
        ws2.cell(row=r, column=1, value=k)
        ws2.cell(row=r, column=2, value=v)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return str(path)
