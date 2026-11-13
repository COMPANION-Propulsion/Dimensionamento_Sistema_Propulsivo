"""
Fascia della ventola nel tratto dritto del condotto: quanto serve davvero.

Il Venturi lascia un tratto dritto lungo 2*L_disk con il centro ventola a meta. Qui si legge
dal CAD della ventola (report.json -> cad) quanto rotore e statore si estendono a monte e a
valle del centro ventola, e se ne ricava il L_disk che li contiene.

    band_need(...)      estensione a monte e a valle del centro ventola [m]
    update_band(...)    regola di aggiornamento di L_disk (margine, minimo, limite L_max/4)
"""
import json
import struct
from pathlib import Path

import numpy as np

HUB_MARGIN_MM = 1.0          # cad_export.HUB_MARGIN_M: mozzo piu lungo della pala, per lato
TOL_FASCIA_M = 0.5e-3        # sotto questa variazione la fascia e convergita


def stl_x_range(path):
    """(xmin, xmax) [mm] dei vertici di un STL (binario o ASCII); None se il file non c'e."""
    path = Path(path)
    if not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) >= 84:
        n = struct.unpack('<I', data[80:84])[0]
        if len(data) == 84 + 50*n and n > 0:
            tri = np.frombuffer(data[84:], count=n, dtype=np.dtype(
                [('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]))
            x = tri['v'][..., 0]
            return float(x.min()), float(x.max())
    xs = [float(line.split()[1]) for line in data.decode('ascii', 'ignore').splitlines()
          if line.strip().startswith('vertex')]
    return (min(xs), max(xs)) if xs else None


def _centre_mm(cad, venturi_results):
    if cad.get('fan_centre_x_mm') is not None:
        return float(cad['fan_centre_x_mm'])
    return 1000.0*float(venturi_results['ventola']['z_centro_ventola_m'])


def band_need(report, venturi_results, stator_on, cad_dir=None):
    """Estensione assiale a monte e a valle del centro ventola [m].

    report          report.json della ventola (serve `cad`)
    venturi_results risultati.json del venturi (centro ventola, se il CAD non lo riporta)
    stator_on       True: a valle si conta fino alla fine dello statore (cad.stator.x_end_mm);
                    False: fino all'estremo a valle del rotore
    cad_dir         cartella 03_cad della ventola: con ventola_A.stl l'estensione del rotore e
                    misurata sul solido; senza, la si ricava da cad.stator (rotore a ridosso
                    dello statore) o, senza statore, si assume il mozzo simmetrico.

    Ritorna dict(monte_m, valle_m, fonte).
    """
    cad = (report or {}).get('cad') or {}
    if not cad or cad.get('errore') or cad.get('hub_length_mm') is None:
        raise ValueError('report.json senza dati CAD della ventola: ingombro non calcolabile.')
    x0 = _centre_mm(cad, venturi_results)
    st = cad.get('stator') if stator_on else None
    if stator_on and not st:
        raise ValueError('statore richiesto ma assente nel CAD della ventola.')
    rotor = stl_x_range(Path(cad_dir)/'ventola_A.stl') if cad_dir else None
    if rotor is not None:
        up, rotor_down, source = x0 - rotor[0], rotor[1] - x0, 'STL del rotore'
    elif cad.get('stator'):
        # statore: mozzo + gioco + pale a valle del rotore, mozzo piu lungo delle pale di 1 mm
        cs = cad['stator']
        rotor_down = cs['x_end_mm'] - x0 - cs['axial_gap_mm'] - cs['length_mm'] - HUB_MARGIN_MM
        up, source = cad['hub_length_mm'] - rotor_down, 'bounding box del rotore e statore'
    else:
        up = rotor_down = 0.5*cad['hub_length_mm']
        source = 'mozzo supposto simmetrico (STL assente)'
    down = (st['x_end_mm'] - x0) if st else rotor_down
    return dict(monte_m=max(up, 0.0)*1e-3, valle_m=max(down, 0.0)*1e-3, fonte=source)


def update_band(L_disk, need, margin=0.001, minimum=None, L_max=None, tol=TOL_FASCIA_M):
    """Nuovo L_disk [m] da un ingombro `need` (dict di band_need).

    L_nuovo = max(monte, valle) + margine, almeno `minimum`; sotto L_max/4 (il venturi rifiuta
    4*L_disk >= L_max): se serve si taglia e `tagliato` e True. `convergito` se la fascia
    cambia meno di tol.
    """
    L_new = max(need['monte_m'], need['valle_m']) + float(margin or 0.0)
    if minimum:
        L_new = max(L_new, float(minimum))
    L_new = round(L_new, 6)              # micrometres: tidy numbers in input_usato.py
    cut = False
    if L_max is not None and 4.0*L_new >= L_max:
        L_new, cut = round(0.25*L_max - 1e-4, 6), True
    return dict(L_disk_nuovo_m=L_new, tagliato=cut, convergito=abs(L_new - L_disk) <= tol)


def write_json(path, rows):
    Path(path).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding='utf-8')
