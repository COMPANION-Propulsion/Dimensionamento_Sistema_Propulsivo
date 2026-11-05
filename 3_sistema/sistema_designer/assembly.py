"""
Assieme tubo + rotore + statore: CAD, viste 3D e file ParaView con i dati delle pale.

    03_cad/assieme_A.step / .stl    tubo + ventola_A + statore_A in un file (mm, asse X)
    03_cad/assieme_B.step / .stl    con le versioni speculari
    01_grafici/vista_*.png          vista 3D col tubo tagliato a meta, vista assiale, laterale
    04_cfd/pale_rotore.vtp          superficie del rotore con i dati del BEMT per raggio
    04_cfd/pale_statore.vtp         superficie dello statore con i dati della schiera
    04_cfd/tubo.vtp                 parete del tubo
    04_cfd/sistema.pvd              apre tutto insieme in ParaView (piu il campo del condotto)

Tutti i file usano il riferimento del condotto: si sovrappongono senza spostamenti.
I CAD sono in mm; i file ParaView sono in metri, come il campo del condotto.
"""
from pathlib import Path

import numpy as np

COLORS = dict(tubo='lightgray', rotore='tomato', statore='steelblue')


def _parts(case_data, side='A'):
    cad_v = case_data.root/'2_venturi'/'03_cad'
    cad_f = case_data.fan_dir/'03_cad'
    rotor = 'ventola_A' if side == 'A' else 'ventola_B_speculare'
    stator = 'statore_A' if side == 'A' else 'statore_B_speculare'
    parts = dict(tubo=cad_v/'tubo', rotore=cad_f/rotor, statore=cad_f/stator)
    return {k: v for k, v in parts.items() if v.with_suffix('.stl').is_file()}


def assembly_cad(case_data):
    """STEP e STL dell'assieme, per le due versioni (A e speculare B)."""
    import cadquery as cq
    import pyvista as pv
    out = case_data.folder('03_cad')
    files = []
    for side in ('A', 'B'):
        parts = _parts(case_data, side)
        shapes = [cq.importers.importStep(str(p.with_suffix('.step'))).val()
                  for p in parts.values() if p.with_suffix('.step').is_file()]
        if shapes:
            step = out/f'assieme_{side}.step'
            cq.Compound.makeCompound(shapes).exportStep(str(step))
            files.append(step)
        meshes = [pv.read(str(p.with_suffix('.stl'))) for p in parts.values()]
        if meshes:
            stl = out/f'assieme_{side}.stl'
            meshes[0].merge(meshes[1:]).save(str(stl))
            files.append(stl)
    return files


def views(case_data):
    """Viste PNG dell'assieme A: 3D col tubo tagliato, assiale da valle, laterale."""
    import pyvista as pv
    parts = {k: pv.read(str(p.with_suffix('.stl'))) for k, p in _parts(case_data, 'A').items()}
    out = case_data.folder('01_grafici')
    files = []
    shots = [('vista_3d_assieme.png', (0.6, -1.0, 0.7), True),
             ('vista_assiale_da_valle.png', (1.0, 0.0, 0.0), False),
             ('vista_laterale_sezione.png', (0.0, -1.0, 0.0), True)]
    for name, direction, cut in shots:
        pl = pv.Plotter(off_screen=True, window_size=(1400, 900))
        pl.set_background('white')
        for key, mesh in parts.items():
            # tolgo la meta di tubo verso la camera (y < 0) per vedere dentro
            m = mesh.clip(normal=(0, -1, 0), origin=(0, 0, 0)) if (cut and key == 'tubo') else mesh
            pl.add_mesh(m, color=COLORS[key], smooth_shading=True,
                        opacity=0.35 if (key == 'tubo' and not cut) else 1.0, label=key)
        pl.add_legend(bcolor='white', size=(0.15, 0.12))
        pl.add_axes()
        pl.view_vector(direction, viewup=(0, 0, 1))
        pl.camera.zoom(1.3)
        pl.screenshot(str(out/name))
        pl.close()
        files.append(out/name)
    return files


def _with_fields(mesh, radius, rows, keys):
    r = np.asarray([x['r_m'] for x in rows])
    for key in keys:
        mesh.point_data[key] = np.interp(radius, r, np.asarray([float(x[key]) for x in rows]))
    return mesh


def paraview(case_data, point):
    """VTP di rotore e statore con i dati per raggio, VTP del tubo e raccolta PVD."""
    import pyvista as pv
    out = case_data.folder('04_cfd')
    parts = _parts(case_data, 'A')
    files = []
    rotor_keys = ['alpha_deg', 'Re', 'Mach', 'static_pressure_rise_Pa', 'axial_total_pressure_rise_Pa',
                  'exit_swirl_m_s', 'dthrust_dr_N_m', 'dtorque_dr_Nm_m']
    stator_keys = ['stator_alpha_deg', 'stator_cl', 'stator_cd', 'stator_Re', 'stator_loss_Pa',
                   'stator_recovered_Pa', 'stator_removed', 'stator_chord_m', 'stator_stagger_deg']
    for key, fields, name in (('rotore', rotor_keys, 'pale_rotore.vtp'),
                              ('statore', stator_keys, 'pale_statore.vtp')):
        if key not in parts or (key == 'statore' and not point.get('stator_enabled')):
            continue
        mesh = pv.read(str(parts[key].with_suffix('.stl'))).extract_surface(algorithm='dataset_surface')
        mesh.points = mesh.points/1000.0                                   # mm -> m
        radius = np.hypot(mesh.points[:, 1], mesh.points[:, 2])            # asse X
        _with_fields(mesh, radius, point['local'], fields).save(str(out/name))
        files.append(out/name)
    if 'tubo' in parts:
        tube = pv.read(str(parts['tubo'].with_suffix('.stl'))).extract_surface(algorithm='dataset_surface')
        tube.points = tube.points/1000.0
        tube.save(str(out/'tubo.vtp'))
        files.append(out/'tubo.vtp')
    entries = [f.name for f in files]
    entries += [n for n in ('condotto_con_ventola_3d.vts',) if (out/n).is_file()]
    lines = ['<?xml version="1.0"?>', '<VTKFile type="Collection" version="0.1">', '  <Collection>']
    lines += [f'    <DataSet timestep="0" part="{i}" file="{n}"/>' for i, n in enumerate(entries)]
    lines += ['  </Collection>', '</VTKFile>', '']
    (out/'sistema.pvd').write_text('\n'.join(lines), encoding='utf-8')
    files.append(out/'sistema.pvd')
    return files
