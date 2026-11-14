"""
Versione dei CAD pensata per SolidWorks (e per altri CAD che aprono male i STEP di progetto).

I STEP di progetto (cad_export.py) sono corretti (solidi validi, mm dichiarati), ma sono
pesanti: centinaia di superfici B-spline, 100-250 mila punti per parte, nessun nome di parte,
schema AP214 di Open CASCADE. Qui si riscrive lo stesso progetto in modo piu semplice da
leggere, senza cambiare nulla del dimensionamento:

  - ogni parte e un solo solido con il suo NOME (tubo, rotore_A, statore_A...); l'assieme e
    un vero assieme con i componenti nominati (tubo, rotore_A, statore_A);
  - unita mm dichiarate esplicitamente (xstep.cascade.unit e write.step.unit = MM);
  - due schemi per ogni file: AP214 (AUTOMOTIVE_DESIGN, IS) e AP203 (CONFIG_CONTROL_DESIGN),
    il piu vecchio e diffuso: se uno non si apre si prova l'altro;
  - in piu IGES (solido B-rep, mm), ripiego se nessuno STEP si apre;
  - niente curve sulle superfici (write.surfacecurve.mode = 0): file piu piccoli, e' la
    forma che scrivono molti CAD;
  - pale semplificate: meno sezioni lungo l'apertura, quindi meno facce e meno punti di
    controllo. Il numero di sezioni e il MINIMO per cui la superficie resta entro SW_TOL_MM
    (0,01 mm) da quella a 41 sezioni del CAD di progetto: lo scostamento e misurato sulle
    41 sezioni di riferimento (ruled_deviation_mm) e scritto in INFO_solidworks.json.

Si rigenera dai risultati esistenti (report.json della ventola, CAD_info.json, tubo.step):
nessun calcolo aerodinamico, solo la costruzione dei solidi.
"""
import json
import shutil
from pathlib import Path

import numpy as np

from . import cad_export as ce
from .cad_export import cq

SW_TOL_MM = 0.01
# Sezioni della pala semplificata: i tratti (4, 5, 8, 10, 20) dividono i 40 del CAD di progetto,
# cosi le sezioni coincidono con quelle di riferimento e lo scostamento si misura esattamente.
SW_SECTION_CANDIDATES = (5, 6, 9, 11, 21)
SCHEMAS = {'AP214': 'AP214IS', 'AP203': 'AP203'}


# ---------------------------------------------------------------------------
# scelta del numero di sezioni
# ---------------------------------------------------------------------------

def ruled_deviation_mm(fine, n):
    """Scarto massimo [mm] fra la superficie rigata a n sezioni e quella delle sezioni `fine`.

    fine: lista di array (punti, 3) in mm, una per sezione. Le n sezioni della versione
    semplificata sono una ogni k delle fini; quelle intermedie, che ora stanno su rette, si
    confrontano con la sezione fine nella stessa posizione. None se n non divide i tratti.
    """
    tratti = len(fine) - 1
    if n < 3 or tratti % (n - 1):
        return None
    k = tratti//(n - 1)
    pts = [np.asarray(f, float) for f in fine]
    worst = 0.0
    for i in range(n - 1):
        a, b = pts[i*k], pts[(i + 1)*k]
        for j in range(1, k):
            u = j/k
            worst = max(worst, float(np.linalg.norm((1 - u)*a + u*b - pts[i*k + j], axis=1).max()))
    return worst


def pick_sections(fine, tol_mm=SW_TOL_MM, candidates=SW_SECTION_CANDIDATES):
    """(sezioni, scarto mm): le meno numerose entro tol_mm; senza, tutte quelle di riferimento."""
    for n in candidates:
        dev = ruled_deviation_mm(fine, n)
        if dev is not None and dev <= tol_mm:
            return n, dev
    return len(fine), 0.0


# ---------------------------------------------------------------------------
# scrittura dei file
# ---------------------------------------------------------------------------

def write_step(path, parts, schema='AP214'):
    """STEP con nomi di parte e mm. parts = [(nome, forma cadquery)]: una parte = file di
    una parte; piu parti = assieme con i componenti nominati. schema = 'AP214' o 'AP203'."""
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    if schema not in SCHEMAS:
        raise ValueError(f'schema {schema!r}: usare uno fra {sorted(SCHEMAS)}')
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString('XmlOcaf'))
    app.InitDocument(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name(label, text):
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(text))

    if len(parts) == 1:
        label = tool.AddShape(parts[0][1].wrapped, False)
        name(label, parts[0][0])
    else:
        top = tool.NewShape()
        name(top, 'assieme')
        for part_name, shape in parts:
            label = tool.AddShape(shape.wrapped, False)
            name(label, part_name)
            name(tool.AddComponent(top, label, TopLoc_Location()), part_name)
    tool.UpdateAssemblies()
    Interface_Static.SetCVal_s('write.step.schema', SCHEMAS[schema])
    Interface_Static.SetCVal_s('xstep.cascade.unit', 'MM')
    Interface_Static.SetCVal_s('write.step.unit', 'MM')
    Interface_Static.SetIVal_s('write.surfacecurve.mode', 0)
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(False)
    writer.SetLayerMode(False)
    writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)
    if writer.Write(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ValueError(f'scrittura di {path} non riuscita')
    return Path(path)


def write_iges(path, shapes):
    """IGES con solidi B-rep (entita 186), mm: ripiego se gli STEP non si aprono."""
    from OCP.IGESControl import IGESControl_Controller, IGESControl_Writer
    from OCP.Interface import Interface_Static
    IGESControl_Controller.Init_s()
    Interface_Static.SetIVal_s('write.iges.brep.mode', 1)
    writer = IGESControl_Writer('MM', 1)
    for shape in shapes:
        writer.AddShape(shape.wrapped)
    writer.ComputeModel()
    if not writer.Write(str(path)):
        raise ValueError(f'scrittura di {path} non riuscita')
    return Path(path)


def _volume(shape):
    return sum(ce._volume(s) for s in shape.Solids())


def _check(path, expected, schema):
    """Rilegge il STEP appena scritto: solidi validi, volume uguale a quello scritto."""
    shape = cq.importers.importStep(str(path)).val()
    vol = _volume(shape)
    return dict(file=Path(path).name, schema=schema, valido=bool(shape.isValid()),
                solidi=len(shape.Solids()), volume_mm3=vol,
                scarto_volume_pct=100*(vol - expected)/expected if expected else None)


# ---------------------------------------------------------------------------
# costruzione dalle cartelle di una catena
# ---------------------------------------------------------------------------

def _fan_x_mm(root, info, case):
    if info.get('fan_centre_x_mm') is not None:
        return float(info['fan_centre_x_mm'])
    path = Path(root)/'2_venturi'/'00_sintesi'/'risultati.json'
    if path.is_file():
        return 1000*float(json.loads(path.read_text(encoding='utf-8'))['ventola']['z_centro_ventola_m'])
    return ce.fan_position_mm(case)


def build_parts(chain_root, tol_mm=SW_TOL_MM):
    """Parti semplificate della catena, nel riferimento del condotto, e i dati della scelta.

    Ritorna (dict nome -> forma, dict dati). Nomi: tubo, rotore_A, rotore_B, statore_A,
    statore_B (statore solo se il CAD di progetto lo ha). ValueError se manca il CAD di base.
    """
    if cq is None:
        raise ValueError('cadquery non installato')
    root = Path(chain_root)
    report_path = root/'3_ventola'/'00_sintesi'/'report.json'
    if not report_path.is_file():
        raise ValueError('3_ventola/00_sintesi/report.json assente: ventola non eseguita')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if not report.get('best'):
        raise ValueError('nessun progetto di ventola accettato')
    case, design = report['input_case'], report['best']['design']
    info_path = root/'3_ventola'/'03_cad'/'CAD_info.json'
    info = (json.loads(info_path.read_text(encoding='utf-8')) if info_path.is_file()
            else (report.get('cad') or {}))
    if info.get('errore'):
        raise ValueError(f"CAD della ventola non prodotto: {info['errore']}")
    clearance = float(case.get('cad', {}).get('tip_clearance_m', ce.TIP_CLEARANCE_M))
    x_mm = _fan_x_mm(root, info, case)
    data = dict(tolleranza_mm=tol_mm, fan_centre_x_mm=x_mm)
    parts = {}
    tube = root/'2_venturi'/'03_cad'/'tubo.step'
    if tube.is_file():
        parts['tubo'] = cq.importers.importStep(str(tube)).val()

    _, fine, _ = ce._blade_geometry(design, clearance)
    n_rot, dev_rot = pick_sections([1000*np.array(s['points']) for s in fine], tol_mm)
    data.update(sezioni_rotore=n_rot, scostamento_rotore_mm=dev_rot, sezioni_rotore_progetto=ce.SECTIONS)
    _, rotor = ce.rotor_solid(design, clearance, n_rot)
    z_end = rotor.BoundingBox().zmax
    parts['rotore_A'] = ce.to_duct_frame(rotor, x_mm)
    parts['rotore_B'] = ce.to_duct_frame(rotor.mirror('XZ'), x_mm)

    rows = ce.stator_rows_from_info(info)
    if rows is not None and (case.get('stator') or {}).get('enabled'):
        st = case['stator']
        r_hub, r_duct = design['hub_diameter_m']/2, design['outer_diameter_m']/2
        z_le = z_end + 1000*float(st.get('axial_gap_m', 0.002))
        fine_v = ce.stator_vane_points(st.get('profile', 'NACA4412'), rows[1], ce.ROOT_OVERLAP*r_hub,
                                       r_duct, z_le, ce.SECTIONS)
        n_st, dev_st = pick_sections([np.array(p) for p in fine_v], tol_mm)
        data.update(sezioni_statore=n_st, scostamento_statore_mm=dev_st)
        stator, _ = ce.stator_solid(case, design, z_end, rows=rows, sections=n_st)
        parts['statore_A'] = ce.to_duct_frame(stator, x_mm)
        parts['statore_B'] = ce.to_duct_frame(stator.mirror('XZ'), x_mm)
    elif (case.get('stator') or {}).get('enabled'):
        data['avviso'] = 'statore previsto ma assente nel CAD della ventola: versione SolidWorks senza statore'
    return parts, data



def solidworks_dirs(chain_root):
    """Cartelle SolidWorks della catena: ogni parte sta nel 03_cad del proprio step."""
    root = Path(chain_root)
    return dict(tubo=root/'2_venturi'/'03_cad'/'solidworks',
                ventola=root/'3_ventola'/'03_cad'/'solidworks',
                assieme=root/'4_sistema'/'03_cad'/'solidworks')


def build_solidworks(chain_root, tol_mm=SW_TOL_MM, log=print):
    """Scrive le versioni per SolidWorks di una catena, ognuna nel 03_cad del suo step:
    tubo -> 2_venturi/03_cad/solidworks, rotore e statore -> 3_ventola/03_cad/solidworks,
    assieme -> 4_sistema/03_cad/solidworks (le versioni speculari B in speculari/).

    Per ogni parte e per l'assieme: STEP AP214 e AP203 (nomi, mm), IGES per le versioni A.
    Ritorna un dict con la scelta delle sezioni, i file (percorso relativo alla catena) e la
    verifica di ognuno; lo scrive anche in 3_ventola/03_cad/solidworks/INFO_solidworks.json.
    Un file che non si scrive e annotato, non ferma gli altri. Le cartelle solidworks
    precedenti sono rifatte da capo.
    """
    root = Path(chain_root)
    parts, data = build_parts(chain_root, tol_mm)
    dirs = solidworks_dirs(root)
    for d in dirs.values():
        if d.exists():
            shutil.rmtree(d)
    files, errors = [], []

    def emit(folder, base, items, iges):
        folder.mkdir(parents=True, exist_ok=True)
        expected = sum(_volume(s) for _, s in items)
        for schema in ('AP214', 'AP203'):
            path = folder/f'{base}_{schema}.step'
            try:
                write_step(path, items, schema)
                row = _check(path, expected, schema)
                row['file'] = path.relative_to(root).as_posix()
                files.append(row)
            except Exception as exc:
                errors.append(f'{path.name}: {exc}')
                log(f'  AVVISO {path.name}: {exc}')
        if iges:
            try:
                write_iges(folder/f'{base}.igs', [s for _, s in items])
                files.append(dict(file=(folder/f'{base}.igs').relative_to(root).as_posix(),
                                  schema='IGES', valido=None))
            except Exception as exc:
                errors.append(f'{base}.igs: {exc}')
                log(f'  AVVISO {base}.igs: {exc}')

    for side, sub, iges in (('A', '', True), ('B', 'speculari', False)):
        sides = {k: v for k, v in parts.items() if k == 'tubo' or k.endswith('_' + side)}
        names = {'tubo': 'tubo', f'rotore_{side}': f'rotore_{side}', f'statore_{side}': f'statore_{side}'}

        def where(key):
            return dirs[key]/sub if sub else dirs[key]

        if side == 'A' and 'tubo' in sides:
            emit(where('tubo'), 'tubo', [('tubo', sides['tubo'])], iges)
        for kind in ('rotore', 'statore'):
            key = f'{kind}_{side}'
            if key in sides:
                emit(where('ventola'), key, [(key, sides[key])], iges)
        items = [(names[k], sides[k]) for k in names if k in sides]
        if len(items) > 1:
            emit(where('assieme'), f'assieme_{side}', items, iges)
    data.update(file=files, errori=errors)
    info = dirs['ventola']
    info.mkdir(parents=True, exist_ok=True)
    (info/'INFO_solidworks.json').write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return data
