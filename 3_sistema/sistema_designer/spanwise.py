"""Rotore e statore lungo il raggio: geometria e aerodinamica anello per anello (grafici)."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ventola_designer.geometry import interpolate


def rotor_rows(point, design):
    hub, tip = design['hub_diameter_m']/2, design['outer_diameter_m']/2
    rows = []
    for x in point['local']:
        s = (x['r_m'] - hub)/(tip - hub)
        rows.append(dict(r_mm=1e3*x['r_m'], corda_mm=1e3*interpolate(design['span_nodes'], design['chord_m'], s),
                         calettamento_deg=interpolate(design['span_nodes'], design['pitch_deg'], s),
                         incidenza_deg=x['alpha_deg'], Re=x['Re'], Mach=x['Mach'],
                         dp_statica_Pa=x['static_pressure_rise_Pa'],
                         dp_assiale_Pa=x['axial_total_pressure_rise_Pa'],
                         swirl_uscita_m_s=x['exit_swirl_m_s'], dT_dr_N_m=x['dthrust_dr_N_m']))
    return rows


def stator_rows(point):
    if not point.get('stator_enabled'):
        return []
    return [dict(r_mm=1e3*x['r_m'], corda_mm=1e3*x['stator_chord_m'],
                 calettamento_dall_asse_deg=x['stator_stagger_deg'], incidenza_deg=x['stator_alpha_deg'],
                 CL=x['stator_cl'], CD=x['stator_cd'], Re=x['stator_Re'],
                 perdita_Pa=x['stator_loss_Pa'], recupero_Pa=x['stator_recovered_Pa'],
                 swirl_tolto=x['stator_removed'], stallo=x['stator_stalled'])
            for x in point['local']]


def _grid(rows, panels, title, path):
    r = [x['r_mm'] for x in rows]
    fig, axs = plt.subplots(len(panels), 1, figsize=(9, 2.6*len(panels)), sharex=True)
    for a, (keys, label) in zip(axs, panels):
        for k in keys:
            a.plot(r, [x[k] for x in rows], lw=1.8, label=k)
        a.set_ylabel(label)
        a.grid(True, ls=':', alpha=0.6)
        if len(keys) > 1:
            a.legend(fontsize=8)
    axs[0].set_title(title)
    axs[-1].set_xlabel('raggio [mm]')
    fig.tight_layout()
    fig.savefig(path, format='svg')
    plt.close(fig)
    return path


def plot_rotor(rows, design, path):
    return _grid(rows, [
        (['corda_mm'], 'corda [mm]'),
        (['calettamento_deg', 'incidenza_deg'], 'angoli [gradi]'),
        (['Re'], 'Reynolds [-]'),
        (['dp_statica_Pa', 'dp_assiale_Pa'], 'Δp [Pa]'),
        (['swirl_uscita_m_s'], 'swirl in uscita [m/s]'),
    ], f"Rotore {design['profile']}, {design['blade_count']} pale, lungo il raggio", path)


def plot_stator(rows, path):
    if not rows:
        return None
    return _grid(rows, [
        (['corda_mm'], 'corda [mm]'),
        (['calettamento_dall_asse_deg', 'incidenza_deg'], 'angoli [gradi]'),
        (['CL', 'CD'], 'CL, CD [-]'),
        (['Re'], 'Reynolds [-]'),
        (['recupero_Pa', 'perdita_Pa'], 'Δp [Pa]'),
        (['swirl_tolto'], 'quota di swirl tolta [-]'),
    ], 'Statore lungo il raggio', path)
