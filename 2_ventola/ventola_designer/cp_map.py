"""Cp sezionale XFOIL viscoso, mappato sulle pale del candidato accettato."""
import argparse
from datetime import datetime
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
                f'PACC\npolar.dat\n\nALFA {alpha:.10g}\nCPWR cp.dat\n\nQUIT\n')
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
        return {'valid': True, 'xy': xy, 'cp': [r[-1] for r in cp],
                'CL_xfoil': polar[-1][1], 'CD_xfoil': polar[-1][2]}
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return {'valid': False, 'reason': str(exc)}


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
    out = cfd_root/datetime.now().strftime('cp_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
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
        points, faces, values, ids = [], [], [], []
        # Ogni striscia ha estremi convergenti: nessun ponte su sezioni fallite.
        for blade in range(design['blade_count']):
            for left,right in zip(records, records[1:]):
                if not (left['valid'] and right['valid']) or len(left['xy']) != len(right['xy']):
                    continue
                first, count = len(points), len(left['xy'])
                for rec in (left,right):
                    beta = math.radians(rec['pitch_deg'])
                    for (x,y), cp in zip(rec['xy'],rec['cp']):
                        t = rec['chord_m']*((x-.25)*math.cos(beta)-y*math.sin(beta))
                        z = rec['chord_m']*((x-.25)*math.sin(beta)+y*math.cos(beta))
                        theta = t/rec['radius_m']+2*math.pi*blade/design['blade_count']
                        points.append((rec['radius_m']*math.cos(theta),rec['radius_m']*math.sin(theta),z))
                        values.append(cp)
                for j in range(count-1):
                    faces.append((first+j, first+j+1, first+count+j+1, first+count+j))
                    ids.append(blade)
        filename = f'fan_cp_point_{pi:02d}.vtp' if faces else None
        if filename:
            _write_polydata(out/filename, points, polys=faces, point_data={'Cp':values}, cell_data={'blade_id':ids})
        metadata['points'].append({'name':point['name'], 'file':filename, 'valid_sections':sum(r['valid'] for r in records), 'sections':records})
    (out/'cp_manifest.json').write_text(json.dumps(metadata,indent=2,allow_nan=False),encoding='utf-8')
    (out/'LEGGIMI.txt').write_text('Aprire fan_cp_point_00.vtp in ParaView, Apply, scegliere Cp.\n'+metadata['definition']+'\n'+metadata['limitations'],encoding='utf-8')
    print(f'Mappa Cp: {out}', flush=True)
    return out, metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    bundled = Path(__file__).resolve().parents[2]/'tools'/'xfoil'/'dist'/'xfoil.exe'
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
