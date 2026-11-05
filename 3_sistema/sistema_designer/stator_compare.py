"""
Ventola con e senza statore, allo stesso Δp assiale richiesto dal condotto.

Rotore fisso (quello dimensionato); per ciascuna variante si cercano i giri che
danno il Δp assiale del Venturi, poi si confrontano potenza, coppia netta sul
veicolo e perdite. Primo ordine: il rotore non viene ridisegnato per la variante.
"""
import json
from copy import deepcopy

from scipy.optimize import brentq

from ventola_designer.polars import PolarDomainError


def _at_rpm(case_data, stator_on, rpm):
    case = deepcopy(case_data.fan['input_case'])
    st = dict(case.get('stator') or {})
    st['enabled'] = stator_on
    case['stator'] = st
    return case_data.fan_point(case=case, rpm=rpm)


def variant(case_data, stator_on, dp_target, rpm0):
    def f(rpm):
        return _at_rpm(case_data, stator_on, rpm)['axial_total_pressure_rise_Pa'] - dp_target
    # a portata fissa il BEMT ha soluzione solo in una fascia di giri: si scandisce
    # attorno al progetto e si cerca il cambio di segno fra punti validi
    prev, bracket = None, None
    for k in [0.80 + 0.02*i for i in range(41)]:          # 0.80 .. 1.60 x rpm di progetto
        try:
            value = f(k*rpm0)
        except PolarDomainError:
            continue
        if prev is not None and (prev[1] < 0.0) != (value < 0.0):
            bracket = (prev[0], k*rpm0)
            break
        prev = (k*rpm0, value)
    if bracket is None:
        return dict(statore=stator_on, errore=f'nessun regime fra {0.8*rpm0:.0f} e '
                                              f'{1.6*rpm0:.0f} rpm che dia {dp_target:.1f} Pa')
    try:
        rpm = brentq(f, *bracket, xtol=0.5)
    except (ValueError, PolarDomainError) as exc:
        return dict(statore=stator_on, errore=str(exc))
    r = _at_rpm(case_data, stator_on, rpm)
    q = r['volume_flow_m3_s']
    return dict(statore=stator_on, rpm=rpm, potenza_albero_W=r['shaft_power_W'],
                dp_assiale_Pa=r['axial_total_pressure_rise_Pa'],
                coppia_rotore_Nm=r['torque_Nm'], coppia_netta_Nm=r['net_torque_Nm'],
                perdita_profili_Pa=r['profile_loss_power_W']/q,
                perdita_statore_Pa=r['stator_loss_power_W']/q,
                rendimento=r['axial_total_pressure_rise_Pa']*q/r['shaft_power_W'],
                Mach_max=r['Mach_max'])


def compare(case_data):
    rep = case_data.fan
    dp = rep['input_case']['operating_points'][0]['minimum_total_pressure_rise_Pa']
    rpm0 = rep['best']['cases'][0]['rpm']
    rows = [variant(case_data, True, dp, rpm0), variant(case_data, False, dp, rpm0)]
    for r in rows:     # swirl lasciato nel getto: tutto senza statore, il residuo di stallo con
        if 'errore' in r:
            continue
        res = _at_rpm(case_data, r['statore'], r['rpm'])
        q = res['volume_flow_m3_s']
        lost = res['swirl_power_W']/q
        if r['statore']:
            removed = [x.get('stator_removed', 1.0) for x in res['local']]
            lost *= (1.0 - sum(removed)/len(removed))**2
        r['swirl_perso_Pa'] = lost
    out = dict(dp_richiesto_Pa=dp, rotore=rep['best']['design']['profile'],
               pale_rotore=rep['best']['design']['blade_count'], varianti=rows,
               nota=('Rotore fisso, giri cercati per dare lo stesso dp assiale. Senza statore lo '
                     'swirl esce col getto; con lo statore si paga il suo attrito ma la coppia '
                     'netta sul veicolo scende.'))
    ok = [r for r in rows if 'errore' not in r]
    if len(ok) == 2:
        con, senza = ok
        out['differenza_potenza_pct'] = 100*(con['potenza_albero_W']/senza['potenza_albero_W'] - 1)
        out['conviene_statore_per_potenza'] = con['potenza_albero_W'] < senza['potenza_albero_W']
    return out


def plot(cmp, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ok = [r for r in cmp['varianti'] if 'errore' not in r]
    if len(ok) < 2:
        return None
    names = ['con statore' if r['statore'] else 'senza statore' for r in ok]
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.5))
    axs[0].bar(names, [r['potenza_albero_W'] for r in ok], color=['tab:blue', 'tab:orange'])
    axs[0].set_ylabel('potenza all\'albero [W]')
    axs[1].bar(names, [1e3*r['coppia_netta_Nm'] for r in ok], color=['tab:blue', 'tab:orange'])
    axs[1].set_ylabel('coppia netta sul veicolo [mN·m]')
    w = 0.25
    x = range(len(ok))
    for k, (key, lab) in enumerate((('perdita_profili_Pa', 'attrito rotore'),
                                    ('perdita_statore_Pa', 'attrito statore'),
                                    ('swirl_perso_Pa', 'swirl perso nel getto'))):
        axs[2].bar([i + (k - 1)*w for i in x], [r[key] for r in ok], w, label=lab)
    axs[2].set_xticks(list(x), names)
    axs[2].set_ylabel('perdite [Pa]')
    axs[2].legend(fontsize=8)
    for a in axs:
        a.grid(True, axis='y', ls=':', alpha=0.6)
    fig.suptitle(f"Con e senza statore allo stesso Δp ({cmp['dp_richiesto_Pa']:.1f} Pa)")
    fig.tight_layout()
    fig.savefig(path, format='svg')
    plt.close(fig)
    return path


def export(case_data):
    cmp = compare(case_data)
    (case_data.folder('00_sintesi')/'confronto_statore.json').write_text(
        json.dumps(cmp, indent=1, ensure_ascii=False), encoding='utf-8')
    plot(cmp, case_data.folder('01_grafici')/'confronto_statore.svg')
    return cmp
