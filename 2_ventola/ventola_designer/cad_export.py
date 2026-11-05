"""
CAD della ventola, pronto per CAD e CFD: mozzo e pale in un solido unico, in mm.

Riferimento: lo stesso dei CAD del condotto (1_venturi), asse X lungo il flusso,
x = 0 al piano d'ingresso del condotto. La ventola e gia al suo posto (centro a
z_centro_ventola_m del Venturi): tubo, fluido e ventola si importano insieme senza
spostamenti. Senza dati del Venturi resta nell'origine, sempre con asse X.

    ventola_A.step / .stl            rotore di progetto (mozzo + pale)
    ventola_B_speculare.step / .stl  rotore specchiato, per l'ugello vicino che gira
                                     al contrario (coppie controrotanti: momenti opposti)
    statore_A / statore_B_speculare  pale fisse + mozzo fisso dopo il rotore, se c'e lo
                                     statore (corpi separati dal rotore: zona fissa in CFD)
    pala.step / .stl                 una pala sola, con la radice dentro il mozzo
    CAD_info.json                    unita, versi di rotazione, gioco, controlli

Le sezioni sono spline chiuse (dorso e ventre), unite sezione per sezione da
superfici rigate: ogni sezione e una curva liscia e lungo l'apertura ci sono
SECTIONS tratti. Un loft unico "liscio" non va usato: quando la corda cambia
molto fra due sezioni (corda minima alla radice, per esempio) la superficie che
le interpola oscilla e la pala esce lunga decine di centimetri. Gli STL vengono
dalla tassellazione dello stesso solido. Ogni pala e controllata: deve stare
fra il mozzo e la punta e non essere piu larga di due corde.

Gioco di punta: il diametro delle pale nel CAD e D - 2 gioco, perche le pale
non tocchino il condotto. L'aerodinamica resta calcolata a diametro pieno;
la perdita di gioco non e modellata (scarto dell'ordine di 2 gioco / D).
La radice e prolungata dentro il mozzo fino a ROOT_OVERLAP x raggio del mozzo,
per una fusione netta.

Verso: con la convenzione di geometry.py il bordo d'attacco precede verso -theta
attorno all'asse e l'aria esce verso valle. Visto da valle (guardando verso
l'ingresso) A gira in senso orario, B in senso antiorario.
"""
import json
import math
from copy import deepcopy
from pathlib import Path

import numpy as np

from .geometry import blade_sections

TIP_CLEARANCE_M = 0.0005   # default del gioco di punta
ROOT_OVERLAP = 0.6         # raggio della sezione di radice dentro il mozzo / raggio del mozzo
HUB_MARGIN_M = 0.001       # mozzo piu lungo della pala, per lato
STL_TOL_MM = 0.005         # scarto massimo fra STL e superficie
STL_ANGLE = 0.1            # [rad] scarto angolare della tassellazione
SECTIONS = 41              # sezioni lungo l'apertura della pala

try:
    import cadquery as cq
except ImportError:        # il resto del dimensionatore funziona anche senza
    cq = None


def _section_wire(points_mm):
    """Sezione chiusa: spline sul contorno NACA, segmento sul bordo d'uscita."""
    pts = [cq.Vector(*p) for p in points_mm]
    spline = cq.Edge.makeSpline(pts)
    te = cq.Edge.makeLine(pts[-1], pts[0])
    return cq.Wire.assembleEdges([spline, te])


def _root_section(points, r_from, r_to):
    """La stessa sezione riportata sul cilindro di raggio r_to, stesso azimut e z."""
    out = []
    for x, y, z in points:
        a = math.atan2(y, x)
        out.append((r_to*math.cos(a), r_to*math.sin(a), z))
    return out


def blade_solid(design, clearance=TIP_CLEARANCE_M):
    """Una pala, in mm, con la radice prolungata dentro il mozzo."""
    cad = deepcopy(design)
    cad['outer_diameter_m'] = design['outer_diameter_m'] - 2*clearance
    if cad['outer_diameter_m'] <= design['hub_diameter_m']:
        raise ValueError('Gioco di punta troppo grande per il raggio della pala.')
    sections = blade_sections(cad, count=SECTIONS, panels=80)
    r_hub = design['hub_diameter_m']/2
    root = _root_section(sections[0]['points'], r_hub, ROOT_OVERLAP*r_hub)
    stack = [root] + [s['points'] for s in sections]
    wires = [_section_wire([tuple(1000*v for v in p) for p in pts]) for pts in stack]
    solid = _closed_loft(wires)
    _check_blade(solid, design, cad, r_hub)
    return solid


def _check_blade(solid, design, cad, r_hub):
    """La pala deve stare dove le sezioni dicono: altrimenti il CAD e sbagliato."""
    tip = 1000*cad['outer_diameter_m']/2
    width = 2000*max(design['chord_m'])
    pts = np.array([v.toTuple() for v in solid.Vertices()])
    r = np.hypot(pts[:, 0], pts[:, 1])
    bb = solid.BoundingBox()
    if r.max() > tip + 0.5 or bb.zlen > width or min(bb.xlen, bb.ylen) > tip + width:
        raise ValueError(f'Pala CAD fuori dalle dimensioni attese (raggio {r.max():.1f} mm '
                         f'contro {tip:.1f}, estensione assiale {bb.zlen:.1f} mm).')


def _closed_loft(wires):
    """Loft rigato chiuso da due superfici di riempimento.

    Le sezioni stanno su cilindri, non su piani: il loft "solido" di OCCT
    chiude le estremita con facce piane e il risultato non e valido. Qui la
    superficie laterale e chiusa da due facce non piane e cucita in un solido.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopoDS import TopoDS
    loft = BRepOffsetAPI_ThruSections(False, True, 1e-6)      # rigato, vedi docstring
    for w in wires:
        loft.AddWire(w.wrapped)
    loft.Build()
    side = cq.Shape.cast(loft.Shape())
    caps = [cq.Face.makeNSidedSurface(w.Edges(), []) for w in (wires[0], wires[-1])]
    sew = BRepBuilderAPI_Sewing(1e-4)
    for face in [*side.Faces(), *caps]:
        sew.Add(face.wrapped)
    sew.Perform()
    fix = ShapeFix_Solid(BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(sew.SewedShape())).Solid())
    fix.Perform()
    solid = cq.Shape.cast(fix.Solid())
    if not solid.isValid() or solid.Volume() <= 0:
        raise ValueError('Loft della pala non valido.')
    return solid


def rotor_solid(design, clearance=TIP_CLEARANCE_M):
    """Mozzo cilindrico + tutte le pale, fusi in un solido, in mm."""
    blade = blade_solid(design, clearance)
    bb = blade.BoundingBox()
    r_hub = 1000*design['hub_diameter_m']/2
    z0, z1 = bb.zmin - 1000*HUB_MARGIN_M, bb.zmax + 1000*HUB_MARGIN_M
    rotor = cq.Solid.makeCylinder(r_hub, z1 - z0, cq.Vector(0, 0, z0), cq.Vector(0, 0, 1))
    n = design['blade_count']
    for k in range(n):
        rotor = rotor.fuse(blade.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 360.0*k/n))
    rotor = rotor.clean()
    if not rotor.isValid():
        raise ValueError('Solido della ventola non valido dopo la fusione.')
    return blade, rotor


def _stl(shape, path):
    shape.exportStl(str(path), tolerance=STL_TOL_MM, angularTolerance=STL_ANGLE)
    return path


def _closed(path):
    try:
        import pyvista as pv
    except ImportError:
        return None
    mesh = pv.read(str(path)).clean()
    return bool(mesh.n_open_edges == 0 and mesh.is_manifold)


def fan_position_mm(case):
    """Centro della ventola sull'asse del condotto [mm], dal Venturi importato."""
    for point in case.get('operating_points', []):
        source = point.get('venturi_source', {}).get('path')
        if source and Path(source).is_file():
            data = json.loads(Path(source).read_text(encoding='utf-8'))
            return 1000*float(data['ventola']['z_centro_ventola_m'])
    return 0.0


def fan_section_end_mm(case):
    """Fine del tratto dritto del condotto attorno alla ventola [mm], dal Venturi."""
    for point in case.get('operating_points', []):
        source = point.get('venturi_source', {}).get('path')
        if source and Path(source).is_file():
            data = json.loads(Path(source).read_text(encoding='utf-8'))
            v = data['ventola']
            return 1000*(v['z_centro_ventola_m'] + v['L_ventola_m'])   # tratto = 2 L_disk
    return None


def to_duct_frame(shape, x_mm):
    """Asse del rotore Z -> asse del condotto X, poi centro della ventola in x_mm."""
    return shape.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), 90).translate(cq.Vector(x_mm, 0, 0))


def stator_sections(case, design, count=21):
    """Corda e calettamento dello statore per raggio, dal BEMT del punto di progetto."""
    from .polars import PolarGrid
    from .pressure_bemt import solve_pressure
    polar = PolarGrid.load(Path(__file__).parent/'airfoils'/'polars_neuralfoil'/f"{design['profile']}.json")
    rpm = design.get('rpm', (design.get('rpm_by_point') or [None])[0])
    result = solve_pressure(case, {**design, 'rpm': rpm}, case['operating_points'][0], polar,
                            stations=count)
    rows = [(r['r_m'], r['stator_chord_m'], r['stator_stagger_deg']) for r in result['local']]
    return result['stator_vanes'], rows


def stator_vane(profile, rows, r_from, r_to, z_le_mm):
    """Una pala dello statore in mm (asse Z), dal mozzo alla parete del condotto.

    Corda allineata al flusso medio meno l'incidenza: dal bordo d'attacco verso
    valle e verso -theta (lo swirl del rotore va verso -theta), dorso verso -theta.
    """
    from .geometry import naca4
    contour = naca4(profile, 80)
    radii = np.array([r for r, _, _ in rows])
    chords = np.array([c for _, c, _ in rows])
    stagger = np.array([g for _, _, g in rows])
    wires = []
    for r in np.linspace(r_from, r_to, SECTIONS):
        c = float(np.interp(r, radii, chords))
        g = math.radians(float(np.interp(r, radii, stagger)))
        e_c = (-math.sin(g), math.cos(g))         # (tangenziale, assiale), bordo d'attacco -> uscita
        e_n = (-math.cos(g), -math.sin(g))        # verso il dorso
        pts = []
        for x, y in contour:
            t = c*(x*e_c[0] + y*e_n[0])
            z = c*(x*e_c[1] + y*e_n[1])
            a = t/r
            pts.append((1000*r*math.cos(a), 1000*r*math.sin(a), z_le_mm + 1000*z))
        wires.append(_section_wire(pts))
    return _closed_loft(wires)


def stator_solid(case, design, z_start_mm):
    """Mozzo fisso + pale dello statore, in mm (asse Z), e dati di progetto."""
    st = case.get('stator') or {}
    n, rows = stator_sections(case, design)
    r_hub, r_duct = design['hub_diameter_m']/2, design['outer_diameter_m']/2
    gap = 1000*float(st.get('axial_gap_m', 0.002))
    z_le = z_start_mm + gap
    vane = stator_vane(st.get('profile', 'NACA4412'), rows, ROOT_OVERLAP*r_hub, r_duct, z_le)
    bb = vane.BoundingBox()
    hub = cq.Solid.makeCylinder(1000*r_hub, bb.zmax + 1000*HUB_MARGIN_M - z_start_mm,
                                cq.Vector(0, 0, z_start_mm), cq.Vector(0, 0, 1))
    body = hub
    for k in range(n):
        body = body.fuse(vane.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 360.0*k/n))
    body = body.clean()
    if not body.isValid():
        raise ValueError('Solido dello statore non valido dopo la fusione.')
    data = dict(vanes=n, profile=st.get('profile', 'NACA4412'), axial_gap_mm=gap,
                chord_mm=[1000*c for _, c, _ in rows], stagger_deg=[g for _, _, g in rows],
                radius_mm=[1000*r for r, _, _ in rows], length_mm=bb.zmax - z_le)
    return body, data


def export_cad(directory, case, design):
    """Scrive i file del docstring in directory; ritorna le informazioni scritte."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    if cq is None:
        info = dict(status='cadquery non installato: STEP non scritti')
        (out/'CAD_info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
        return info
    clearance = float(case.get('cad', {}).get('tip_clearance_m', TIP_CLEARANCE_M))
    blade, rotor = rotor_solid(design, clearance)
    mirror = rotor.mirror('XZ')          # specchio su un piano che contiene l'asse
    x_mm = fan_position_mm(case)
    blade, rotor, mirror = (to_duct_frame(s, x_mm) for s in (blade, rotor, mirror))
    shapes = [('pala', blade), ('ventola_A', rotor), ('ventola_B_speculare', mirror)]
    stator_info = None
    if (case.get('stator') or {}).get('enabled'):
        z_rotor_end = rotor_solid(design, clearance)[1].BoundingBox().zmax
        stator, stator_info = stator_solid(case, design, z_rotor_end)
        shapes += [('statore_A', to_duct_frame(stator, x_mm)),
                   ('statore_B_speculare', to_duct_frame(stator.mirror('XZ'), x_mm))]
        stator_info['x_end_mm'] = shapes[-1][1].BoundingBox().xmax
        straight_end = fan_section_end_mm(case)
        if straight_end is not None and stator_info['x_end_mm'] > straight_end:
            stator_info['avviso'] = (f"lo statore finisce a x = {stator_info['x_end_mm']:.1f} mm, "
                                     f"oltre il tratto dritto del condotto ({straight_end:.1f} mm): "
                                     f"aumentare VENTURI['L_disk']")
    files = {}
    for name, shape in shapes:
        shape.exportStep(str(out/f'{name}.step'))
        _stl(shape, out/f'{name}.stl')
        files[name] = dict(step=f'{name}.step', stl=f'{name}.stl', volume_mm3=shape.Volume(),
                           stl_closed=_closed(out/f'{name}.stl'), valid=shape.isValid())
    bb = rotor.BoundingBox()
    info = dict(
        units='mm', axis='X (flusso verso +X), come i CAD del condotto', files=files,
        fan_centre_x_mm=x_mm,
        blade_count=design['blade_count'], profile=design['profile'],
        diameter_aero_mm=1000*design['outer_diameter_m'],
        diameter_cad_mm=1000*(design['outer_diameter_m'] - 2*clearance),
        tip_clearance_mm=1000*clearance, hub_diameter_mm=1000*design['hub_diameter_m'],
        hub_length_mm=bb.xlen, stator=stator_info,
        rotation={'ventola_A': 'oraria vista da valle (guardando verso -X)',
                  'ventola_B_speculare': 'antioraria vista da valle (guardando verso -X)'},
        note=('Coppia di ugelli A + B: stessa spinta e stessa potenza, momenti di reazione '
              'opposti; con lo statore la coppia netta di ogni ugello e gia quasi nulla. '
              'Gioco di punta e perdita di gioco: vedi docstring di cad_export.py. '
              'Mozzo cilindrico senza ogiva ne attacco albero; statore fino alla parete.'))
    (out/'CAD_info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    return info
