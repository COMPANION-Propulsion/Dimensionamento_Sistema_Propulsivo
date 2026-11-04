"""Input in SI. Nessun dato aerodinamico viene sostituito con valori presunti."""
import json
import math
from .settings import sizing_settings
from pathlib import Path


def number(value, name, minimum=0.0, strict=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: richiesto un numero.")
    if not math.isfinite(value) or (value <= minimum if strict else value < minimum):
        raise ValueError(f"{name}: valore fuori intervallo o non finito.")
    return float(value)


def bounds(values, name):
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError(f"{name}: richiesti [minimo, massimo].")
    low, high = [number(v, name) for v in values]
    if low >= high:
        raise ValueError(f"{name}: minimo deve essere minore del massimo.")
    return low, high


def load_catalog():
    path = Path(__file__).parent / "airfoils" / "catalogo.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in data["profiles"]}


def operating_air(case, point):
    """Aria secca: condizioni globali con eventuali override del punto operativo."""
    base = case['air']
    overrides = point.get('air', {})
    if not isinstance(base, dict) or not isinstance(overrides, dict):
        raise ValueError('air deve essere un oggetto JSON.')
    allowed = {'temperature_K', 'static_pressure_Pa', 'relative_humidity'}
    if overrides.keys()-allowed:
        raise ValueError(f"Campi air del punto sconosciuti: {sorted(overrides.keys()-allowed)}")
    resolved = {**base, **overrides}
    number(resolved['temperature_K'], 'temperatura [K]')
    number(resolved['static_pressure_Pa'], 'pressione statica assoluta [Pa]')
    humidity = resolved.get('relative_humidity')
    if humidity is not None and (type(humidity) not in (int,float) or humidity != 0):
        raise ValueError('Il modello accetta solo aria secca: relative_humidity null o 0.')
    return resolved


def velocity_reference(case):
    reference = case.get('velocity_reference', 'far_upstream')
    if reference != 'far_upstream':
        raise ValueError('Il BEMT attuale richiede velocity_reference="far_upstream"; '
                         'la velocita sul disco o all\'ingresso del condotto non e supportata.')
    return reference


def load_case(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    try:
        air, rotor, points = data["air"], data["rotor"], data["operating_points"]
        number(air["temperature_K"], "temperatura [K]")
        number(air["static_pressure_Pa"], "pressione assoluta [Pa]")
        operating_air(data, {})
        data['velocity_reference'] = velocity_reference(data)
        diameter = number(rotor["outer_diameter_m"], "diametro esterno")
        _, hub_max = bounds(rotor["hub_diameter_bounds_m"], "diametro mozzo")
        if hub_max >= diameter:
            raise ValueError("Il mozzo massimo deve essere minore del diametro esterno.")
        bounds(rotor["shaft_speed_bounds_rpm"], "giri")
        blades = rotor["blade_count_candidates"]
        if not isinstance(blades, list) or not blades or any(type(b) is not int or b < 2 for b in blades):
            raise ValueError("Candidati pale: elenco non vuoto di interi >= 2.")
        if len(set(blades)) != len(blades):
            raise ValueError("Candidati pale duplicati.")
        profiles = rotor["airfoil_candidates"]
        catalog = load_catalog()
        if not isinstance(profiles, list) or not profiles or any(p not in catalog for p in profiles):
            raise ValueError("Profili assenti o non presenti nel catalogo.")
        if rotor.get("profile_constant_along_span") is not True:
            raise ValueError("Il prototipo usa un profilo costante lungo la pala.")
        if not isinstance(points, list) or not points:
            raise ValueError("Inserire almeno un punto operativo.")
        names = set()
        for point in points:
            operating_air(data, point)
            name = point["name"]
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError("Nomi dei punti operativi vuoti o duplicati.")
            names.add(name)
            number(point["minimum_rotor_thrust_N"], f"{name}: spinta")
            number(point["axial_inlet_velocity_m_s"], f"{name}: velocità", strict=False)
            number(point["duration_s"], f"{name}: durata")
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Struttura input incompleta o non valida: {exc}") from exc
    data['sizing'] = sizing_settings(data)
    return data
