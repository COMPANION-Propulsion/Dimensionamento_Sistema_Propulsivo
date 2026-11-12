"""
Cp e strato limite XFOIL viscoso per sezione, mappati sulle pale del candidato accettato.

Per ogni sezione del rotore (e dello statore, se c'e) XFOIL risolve il profilo isolato
all'incidenza, Reynolds e Mach del BEMT e restituisce Cp e coefficiente d'attrito Cf
lungo la corda. Dove Cf < 0 la corrente e staccata dalla parete:

    x_sep    primo punto, dal bordo d'attacco, con Cf < 0 su quella faccia
    x_riatt  punto dove Cf torna positivo (bolla laminare) oppure None
    frazione_staccata  quota della corda con Cf < 0

Faccia "dorso" = lato superiore del profilo (aspirazione per incidenza positiva).
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import numpy as np

from .geometry import naca4, interpolate
from .paraview import _write_polydata


def numeric_rows(path, columns):
    rows = []
    if path.exists():
        for line in path.read_text(errors='replace').splitlines():
            try:
                row = [float(v) for v in line.split()]
            except ValueError:
                continue
            if len(row) == columns and all(math.isfinite(v) for v in row):
                rows.append(row)
    return rows


def section_cp(executable, folder, profile, alpha, reynolds, mach, timeout=45):
    folder.mkdir(parents=True, exist_ok=False)
    contour = naca4(profile, 80)
    (folder/'foil.dat').write_text(profile+'\n'+'\n'.join(f'{x:.12g} {y:.12g}' for x,y in contour), encoding='ascii')
    commands = (f'PLOP\nG\n\nLOAD foil.dat\nPANE\nPSAV panel.dat\nOPER\n'
                f'VISC {reynolds:.10g}\nMACH {mach:.10g}\nVPAR\nN 9\n\nITER 250\n'
                f'PACC\npolar.dat\n\nALFA {alpha:.10g}\nCPWR cp.dat\nDUMP bl.dat\n\nQUIT\n')
    (folder/'commands.txt').write_text(commands, encoding='ascii')
    try:
        with (folder/'xfoil.log').open('w') as log:
            proc = subprocess.run([str(executable)], input=commands, text=True,
                                  stdout=log, stderr=subprocess.STDOUT, cwd=folder,
                                  timeout=timeout,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode != 0:
            raise ValueError(f'XFOIL exit code {proc.returncode}')
        polar = numeric_rows(folder/'polar.dat', 7)
        if not any(abs(row[0]-alpha) < .002 for row in polar):
            raise ValueError('Nessun punto viscoso convergente nella polare XFOIL')
        xy = numeric_rows(folder/'panel.dat', 2)
        cp = numeric_rows(folder/'cp.dat', 3) or numeric_rows(folder/'cp.dat', 2)
        if len(xy) < 20 or len(xy) != len(cp):
            raise ValueError('Coordinate e Cp incompleti o non corrispondenti')
        if any(abs(a[0]-b[0]) > 2e-4 for a,b in zip(xy,cp)):
            raise ValueError('Ordine delle coordinate Cp non coerente')
        bl = numeric_rows(folder/'bl.dat', 8)[:len(xy)]
        cf = [r[6] for r in bl] if len(bl) == len(xy) else None
        return {'valid': True, 'xy': xy, 'cp': [r[-1] for r in cp], 'cf': cf,
                'separation': separation(xy, cf) if cf else None,
                'CL_xfoil': polar[-1][1], 'CD_xfoil': polar[-1][2]}
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return {'valid': False, 'reason': str(exc)}


def separation(xy, cf, x_skip=0.02):
    """Punti di distacco e riattacco su dorso e ventre, da Cf (vedi docstring)."""
    le = min(range(len(xy)), key=lambda i: xy[i][0])
    faces = {'dorso': list(range(le, -1, -1)), 'ventre': list(range(le, len(xy)))}
    out = {}
    for name, idx in faces.items():
        x = [xy[i][0] for i in idx]
        c = [cf[i] for i in idx]
        sep = next((xi for xi, ci in zip(x, c) if xi > x_skip and ci < 0), None)
        reatt = None
        if sep is not None:
            after = [(xi, ci) for xi, ci in zip(x, c) if xi > sep]
            reatt = next((xi for xi, ci in after if ci > 0), None)
        detached = sum(x[k + 1] - x[k] for k in range(len(x) - 1) if c[k] < 0 and x[k] > x_skip)
        out[name] = dict(x_sep=sep, x_riatt=reatt, frazione_staccata=max(0.0, detached))
    return out


def export_cp(report_path, executable, sections=17):
    from .optimizer import evaluate
    from .polars import PolarGrid
    from .bemt import air_properties
    from .config import operating_air
    report_path, executable = Path(report_path).resolve(), Path(executable).resolve()
    if not executable.is_file():
        raise ValueError(f'Eseguibile XFOIL assente: {executable}')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if not report.get('complete') or not (report.get('best') or {}).get('accepted'):
        raise ValueError('Serve un report completo con candidato accettato')
    case, design = report['input_case'], report['best']['design']
    if case.get('design_mode') != 'pressure_flow':
        raise ValueError('Mappa Cp attualmente disponibile per pressure_flow')
    stations = case['sizing']['stations_final']
    if not 2 <= sections <= stations:
        raise ValueError(f'Sezioni richieste fra 2 e {stations}')
    polar = PolarGrid.load(Path(__file__).parent/'airfoils'/'polars_neuralfoil'/f"{design['profile']}.json")
    _, _, results = evaluate(case, design, polar, stations=stations)
    result_root = report_path.parent.parent if report_path.parent.name == '00_sintesi' else report_path.parent
    cfd_root = result_root/'04_cfd' if report_path.parent.name == '00_sintesi' else result_root/'paraview'
    out = cfd_root/'strato_limite'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    metadata = {'model': 'XFOIL viscous isolated 2D sections; Ncrit=9; free transition',
                'definition': 'Cp=(p-p_ref_local)/(0.5*rho*W_relative^2)',
                'reference': 'https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt',
                'report': str(report_path), 'report_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest(),
                'xfoil': str(executable), 'xfoil_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                'limitations': 'One-way postprocessing; does not update BEMT. No 3D, cascade or duct interaction. No radial extrapolation to root/tip. Surface strips require two converged adjacent sections.',
                'points': []}
    for pi, (point, result) in enumerate(zip(case['operating_points'], results)):
        air = operating_air(case, point)
        _, _, sound = air_properties(air['temperature_K'], air['static_pressure_Pa'])
        records = []
        for si, index in enumerate(np.linspace(0, stations-1, sections, dtype=int)):
            row = result['local'][index]
            r = row['r_m']
            hub, tip = design['hub_diameter_m']/2, design['outer_diameter_m']/2
            s = (r-hub)/(tip-hub)
            w = math.hypot(row['axial_velocity_m_s'], result['rpm']*2*math.pi/60*r-row['exit_swirl_m_s']/2)
            record = dict(radius_m=r, alpha_deg=row['alpha_deg'], Re=row['Re'], Mach_relative=w/sound,
                          chord_m=interpolate(design['span_nodes'], design['chord_m'], s),
                          pitch_deg=interpolate(design['span_nodes'], design['pitch_deg'], s))
            record.update(section_cp(executable, out/f'point_{pi:02d}_section_{si:02d}',
                                     design['profile'], record['alpha_deg'], record['Re'], record['Mach_relative']))
            records.append(record)
            print(f'Cp punto {pi}, sezione {si+1}/{sections}: '+('convergente' if record['valid'] else record['reason']), flush=True)
        points, faces, values, ids, cf_values = [], [], [], [], []
        # Ogni striscia ha estremi convergenti: nessun ponte su sezioni fallite.
        for blade in range(design['blade_count']):
            for left,right in zip(records, records[1:]):
                if not (left['valid'] and right['valid']) or len(left['xy']) != len(right['xy']):
                    continue
                first, count = len(points), len(left['xy'])
                for rec in (left,right):
                    beta = math.radians(rec['pitch_deg'])
                    for k, ((x,y), cp) in enumerate(zip(rec['xy'],rec['cp'])):
                        cf_values.append(rec['cf'][k] if rec.get('cf') else 0.0)
                        # Dorso (y > 0, aspirazione a incidenza positiva) a monte, come assume il BEMT.
                        t = rec['chord_m']*((x-.25)*math.cos(beta)+y*math.sin(beta))
                        z = rec['chord_m']*((x-.25)*math.sin(beta)-y*math.cos(beta))
                        theta = t/rec['radius_m']+2*math.pi*blade/design['blade_count']
                        points.append((rec['radius_m']*math.cos(theta),rec['radius_m']*math.sin(theta),z))
                        values.append(cp)
                for j in range(count-1):
                    faces.append((first+j, first+j+1, first+count+j+1, first+count+j))
                    ids.append(blade)
        filename = f'fan_cp_point_{pi:02d}.vtp' if faces else None
        if filename:
            fields = {'Cp': values}
            if cf_values and len(cf_values) == len(values):
                fields['Cf'] = cf_values
            _write_polydata(out/filename, points, polys=faces, point_data=fields, cell_data={'blade_id':ids})
        stator_records = []
        st = case.get('stator') or {}
        if st.get('enabled'):
            for si, index in enumerate(np.linspace(0, stations-1, sections, dtype=int)):
                row = result['local'][index]
                w = math.hypot(row['axial_velocity_m_s'], .5*row['exit_swirl_m_s'])
                record = dict(radius_m=row['r_m'], alpha_deg=row['stator_alpha_deg'],
                              Re=row['stator_Re'], Mach_relative=w/sound,
                              chord_m=row['stator_chord_m'], stalled_model=row['stator_stalled'])
                record.update(section_cp(executable, out/f'point_{pi:02d}_stator_{si:02d}',
                                         st.get('profile', 'NACA4412'), record['alpha_deg'],
                                         record['Re'], record['Mach_relative']))
                stator_records.append(record)
        metadata['points'].append({'name':point['name'], 'file':filename, 'valid_sections':sum(r['valid'] for r in records),
                                   'sections':records, 'stator_sections': stator_records})
        plot_boundary_layer(records, stator_records, result_root/'01_grafici'/f'strato_limite_{pi:02d}.svg',
                            design['profile'], st.get('profile'))
    (out/'cp_manifest.json').write_text(json.dumps(metadata,indent=2,allow_nan=False),encoding='utf-8')
    (out/'LEGGIMI.txt').write_text('Aprire fan_cp_point_00.vtp in ParaView, Apply, scegliere Cp o Cf '
                                   '(Cf < 0: corrente staccata).\n'+metadata['definition']+'\n'+metadata['limitations'],encoding='utf-8')
    print(f'Mappa Cp: {out}', flush=True)
    return out, metadata


def plot_boundary_layer(rotor, stator, path, rotor_profile, stator_profile=None):
    """Cp, Cf e distacco lungo la pala, per rotore e statore (strato_limite_XX.svg)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    path.parent.mkdir(parents=True, exist_ok=True)
    groups = [('rotore', rotor, rotor_profile)] + ([('statore', stator, stator_profile)] if stator else [])
    fig, axes = plt.subplots(3, len(groups), figsize=(7*len(groups), 12), squeeze=False)
    for col, (name, recs, prof) in enumerate(groups):
        ok = [r for r in recs if r['valid']]
        a_cp, a_cf, a_sep = axes[0][col], axes[1][col], axes[2][col]
        for r in ok[::max(1, len(ok)//5)]:
            x = [p[0] for p in r['xy']]
            lab = f"r = {1000*r['radius_m']:.1f} mm"
            a_cp.plot(x, [-c for c in r['cp']], lw=1.2, label=lab)
            if r.get('cf'):
                a_cf.plot(x, r['cf'], lw=1.2, label=lab)
        a_cf.axhline(0, color='r', lw=0.8)
        rr = [1000*r['radius_m'] for r in ok if r.get('separation')]
        for face, style in (('dorso', 'o-'), ('ventre', 's--')):
            xs = [r['separation'][face]['x_sep'] if r['separation'][face]['x_sep'] is not None else 1.0
                  for r in ok if r.get('separation')]
            a_sep.plot(rr, xs, style, ms=4, label=f'{face}: inizio distacco (1 = nessuno)')
        frac = [r['separation']['dorso']['frazione_staccata'] for r in ok if r.get('separation')]
        a_sep.plot(rr, frac, 'k:', label='dorso: quota di corda staccata')
        a_cp.set_title(f'{name} ({prof}): -Cp lungo la corda')
        a_cp.set_ylabel('-Cp [-]')
        a_cf.set_title(f'{name}: attrito Cf (sotto la linea rossa = staccato)')
        a_cf.set_ylabel('Cf [-]')
        a_cf.set_xlabel('x / c [-]')
        a_sep.set_title(f'{name}: distacco lungo la pala')
        a_sep.set_xlabel('raggio [mm]')
        a_sep.set_ylabel('x / c [-]')
        a_sep.set_ylim(-0.05, 1.05)
        for a in (a_cp, a_cf, a_sep):
            a.grid(True, ls=':', alpha=0.6)
            a.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, format='svg')
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    bundled = Path(__file__).resolve().parents[1]/'tools'/'xfoil'/'dist'/'xfoil.exe'
    parser.add_argument('--xfoil', type=Path, default=shutil.which('xfoil') or bundled)
    parser.add_argument('--sections', type=int, default=17)
    args = parser.parse_args(argv)
    try:
        _, meta = export_cp(args.report, args.xfoil, args.sections)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0 if all(p['file'] for p in meta['points']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
