"""Impostazioni del dimensionatore: default espliciti e validazione centralizzata."""
from copy import deepcopy
import math

DEFAULTS = {
    'pressure_numerical_margin':.002, 'max_pressure_grid_change':.01,
    'geometry_stations':65, 'minimum_section_thickness_m':0., 'minimum_circumferential_gap_m':0.,
    'loss_model':'none',
    'chord_over_D_bounds':[.04,.22], 'pitch_deg_bounds':[0.,45.],
    'max_solidity':.8, 'max_Mach':.3, 'thrust_numerical_margin':.002,
    'stations_optimization':32, 'stations_verification':64, 'stations_final':128,
    'solidity_stations':65, 'maxiter':80, 'starts':3, 'seed_samples':48,
    'random_seed':42, 'ftol':1e-6, 'finite_difference_step':1e-5,
    'constraint_tolerance':1e-6, 'max_thrust_grid_change':.01,
}


def sizing_settings(case):
    supplied = case.get('sizing',{})
    if not isinstance(supplied,dict):
        raise ValueError('sizing deve essere un oggetto JSON.')
    unknown = supplied.keys()-DEFAULTS.keys()
    if unknown:
        raise ValueError(f'Impostazioni sizing sconosciute: {sorted(unknown)}')
    cfg = deepcopy(DEFAULTS)
    cfg.update(deepcopy(supplied))
    if cfg['loss_model'] not in ('none','prandtl_free_rotor'):
        raise ValueError('loss_model deve essere none oppure prandtl_free_rotor.')
    for name in ('chord_over_D_bounds','pitch_deg_bounds'):
        value = cfg[name]
        if not isinstance(value,list) or len(value)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in value) or value[0]>=value[1]:
            raise ValueError(f'{name}: richiesti due numeri finiti crescenti.')
    if cfg['chord_over_D_bounds'][0]<=0 or not -90<cfg['pitch_deg_bounds'][0]<cfg['pitch_deg_bounds'][1]<90:
        raise ValueError('Corde positive e calettamenti strettamente fra -90 e 90 gradi richiesti.')
    integer_min = {'geometry_stations':3,'stations_optimization':4,'stations_verification':4,'stations_final':4,
                   'solidity_stations':3,'maxiter':1,'starts':1,'seed_samples':1,'random_seed':0}
    for key,minimum in integer_min.items():
        if type(cfg[key]) is not int or cfg[key]<minimum:
            raise ValueError(f'{key}: richiesto intero >= {minimum}.')
    if not cfg['stations_optimization']<cfg['stations_verification']<cfg['stations_final']:
        raise ValueError('Le griglie devono crescere: optimization < verification < final.')
    if cfg['starts']>cfg['seed_samples']:
        raise ValueError('starts non puo superare seed_samples.')
    for key in ('minimum_section_thickness_m','minimum_circumferential_gap_m'):
        if type(cfg[key]) not in (int,float) or not math.isfinite(cfg[key]) or cfg[key]<0:
            raise ValueError(f'{key}: richiesto valore finito non negativo in metri.')
    for key in ('max_solidity','max_Mach','ftol','finite_difference_step','constraint_tolerance','max_thrust_grid_change','thrust_numerical_margin','pressure_numerical_margin','max_pressure_grid_change'):
        v=cfg[key]
        if type(v) not in (int,float) or not math.isfinite(v) or (v<0 if key.endswith('_numerical_margin') else v<=0):
            raise ValueError(f'{key}: valore non valido.')
    if cfg['max_Mach']>=1 or cfg['finite_difference_step']>=1 or cfg['max_thrust_grid_change']>=1 or cfg['max_pressure_grid_change']>=1:
        raise ValueError('Mach, passo normalizzato e variazione di griglia devono essere < 1.')
    if cfg['constraint_tolerance']>=1e-2 or cfg['ftol']>=1e-2:
        raise ValueError('Tolleranze numeriche richieste < 0.01.')
    return cfg
