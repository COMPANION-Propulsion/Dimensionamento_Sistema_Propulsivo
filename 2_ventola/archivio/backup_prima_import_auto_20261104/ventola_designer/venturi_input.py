"""Lettura del solo JSON esportato dal Venturi; nessuna importazione del suo codice."""
import hashlib
import json
import math
from pathlib import Path


def import_duties(data, input_path):
    from .config import number
    diameter = data['rotor'].get('outer_diameter_m')
    for point in data['operating_points']:
        source = point.get('venturi_result')
        if source is None:
            continue
        if data.get('design_mode') != 'pressure_flow':
            raise ValueError('venturi_result richiede design_mode=pressure_flow.')
        path = Path(source)
        if not path.is_absolute():
            path = Path(input_path).resolve().parent / path
        raw = path.read_bytes()
        result = json.loads(raw.decode('utf-8-sig'))
        fan = result['ventola']
        d = number(fan['D_ventola_m'], 'Venturi: diametro')
        dp = number(fan['dp_disk_Pa'], 'Venturi: pressione totale')
        q = number(fan['portata_m3_s'], 'Venturi: portata')
        v = number(fan['V_disco_m_s'], 'Venturi: velocita disco')
        rho = number(fan['densita_kg_m3'], 'Venturi: densita')
        if not math.isclose(q, v * math.pi * d*d/4, rel_tol=1e-4):
            raise ValueError('Venturi: Q, V_disco e diametro non coerenti.')
        if diameter is not None and not math.isclose(number(diameter, 'diametro'), d, rel_tol=1e-8):
            raise ValueError('Diametro diverso fra input ventola e risultati Venturi.')
        diameter = d
        imported = dict(volume_flow_m3_s=q, minimum_total_pressure_rise_Pa=dp,
                        density_kg_m3=rho, full_disk_velocity_m_s=v)
        for key, value in imported.items():
            if key in point and not math.isclose(number(point[key], key), value, rel_tol=1e-8):
                raise ValueError(f'{key}: valore manuale diverso dal risultato Venturi.')
        point.update(imported)
        point['venturi_source'] = {'path':str(path.resolve()),
            'sha256':hashlib.sha256(raw).hexdigest(),
            'dp_loop_converged':result.get('numerica', {}).get('ciclo_dp_convergito'),
            'thrust_grid_reliable':result.get('spinta', {}).get('affidabile')}
    if diameter is not None:
        data['rotor']['outer_diameter_m'] = diameter
