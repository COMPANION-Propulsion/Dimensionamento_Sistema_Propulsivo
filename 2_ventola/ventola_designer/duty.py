"""Grandezza richiesta per il dimensionamento: spinta oppure pressione totale."""

def pressure_mode(case):
    return case.get('design_mode', 'thrust') == 'pressure_flow'


def metric_key(case):
    return 'total_pressure_rise_Pa' if pressure_mode(case) else 'thrust_rotor_N'


def target_key(case):
    return 'minimum_total_pressure_rise_Pa' if pressure_mode(case) else 'minimum_rotor_thrust_N'


def margin_key(case):
    return 'pressure_numerical_margin' if pressure_mode(case) else 'thrust_numerical_margin'


def grid_limit_key(case):
    return 'max_pressure_grid_change' if pressure_mode(case) else 'max_thrust_grid_change'
