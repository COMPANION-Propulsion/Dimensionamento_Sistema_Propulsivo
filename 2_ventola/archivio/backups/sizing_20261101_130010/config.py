"""Input in SI. Nessun dato aerodinamico viene sostituito con valori presunti."""
import json
import math
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


def load_case(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    try:
        air, rotor, points = data["air"], data["rotor"], data["operating_points"]
        number(air["temperature_K"], "temperatura [K]")
        number(air["static_pressure_Pa"], "pressione assoluta [Pa]")
        if air.get("relative_humidity") not in (None, 0):
            raise ValueError("Il prototipo accetta solo aria secca.")
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
            name = point["name"]
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError("Nomi dei punti operativi vuoti o duplicati.")
            names.add(name)
            number(point["minimum_rotor_thrust_N"], f"{name}: spinta")
            number(point["axial_inlet_velocity_m_s"], f"{name}: velocità", strict=False)
            number(point["duration_s"], f"{name}: durata")
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Struttura input incompleta o non valida: {exc}") from exc
    return data
