"""
Potenza nel tempo lungo la manovra: quando la ventola lavora, quanto, e l'energia.

Manovra da fermo a fermo (0_spinta): la faccia posteriore spinge durante
l'accelerazione, nessuna spinta in crociera, la faccia anteriore frena. Ogni
faccia ha n ugelli, ciascuno con la potenza all'albero del punto di progetto.
Avvio e arresto dei motori sono istantanei (primo ordine).
"""
import json

import numpy as np


def profile(thrust, fan):
    n = thrust['input']['n_ugelli']
    t_end = float(thrust['input']['tempo'])
    t_a = float(thrust['t_accelerazione_s'])
    c = fan['best']['cases'][0]
    p_nozzle = c['shaft_power_W']
    p_face = n*p_nozzle
    phases = [
        dict(fase='accelerazione', faccia='posteriore', da_s=0.0, a_s=t_a, potenza_faccia_W=p_face),
        dict(fase='crociera', faccia='-', da_s=t_a, a_s=t_end - t_a, potenza_faccia_W=0.0),
        dict(fase='frenata', faccia='anteriore', da_s=t_end - t_a, a_s=t_end, potenza_faccia_W=p_face),
    ]
    phases = [p for p in phases if p['a_s'] - p['da_s'] > 1e-12]
    energy = sum(p['potenza_faccia_W']*(p['a_s'] - p['da_s']) for p in phases)
    return dict(
        ugelli_per_faccia=n, potenza_ugello_W=p_nozzle, potenza_faccia_W=p_face,
        picco_W=p_face, rpm=c['rpm'], coppia_ugello_Nm=c['torque_Nm'],
        spinta_ugello_N=thrust['T_ugello_N'], durata_manovra_s=t_end,
        tempo_con_motori_accesi_s=sum(p['a_s'] - p['da_s'] for p in phases if p['potenza_faccia_W'] > 0),
        energia_manovra_J=energy, energia_manovra_Wh=energy/3600.0,
        potenza_media_W=energy/t_end, fasi=phases,
        nota=('Potenza all\'albero (elettrica = albero / rendimento di motore e '
              'regolatore, non incluso). Una faccia alla volta: picco = n ugelli x '
              'potenza di un ugello.'))


def plot(prof, thrust, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    t_end = prof['durata_manovra_s']
    t = np.linspace(0.0, t_end, 1001)
    rear = np.zeros_like(t)
    front = np.zeros_like(t)
    for p in prof['fasi']:
        on = (t >= p['da_s']) & (t <= p['a_s'])
        if p['faccia'] == 'posteriore':
            rear[on] = p['potenza_faccia_W']
        elif p['faccia'] == 'anteriore':
            front[on] = p['potenza_faccia_W']
    energy = np.concatenate(([0.0], np.cumsum(0.5*(rear[1:] + rear[:-1] + front[1:] + front[:-1])*np.diff(t))))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
    a1.fill_between(t, rear, step='mid', alpha=0.5, label='faccia posteriore (spinge)')
    a1.fill_between(t, front, step='mid', alpha=0.5, label='faccia anteriore (frena)')
    a1.axhline(prof['picco_W'], color='r', ls=':', lw=1, label=f"picco {prof['picco_W']:.2f} W")
    a1.set_ylabel('potenza all\'albero [W]')
    a1.set_title(f"Potenza nella manovra: {thrust['input']['distanza']:g} m in {t_end:g} s, "
                 f"{prof['ugelli_per_faccia']} ugelli da {prof['potenza_ugello_W']:.3f} W, "
                 f"{prof['rpm']:.0f} rpm")
    a2.plot(t, energy, 'k-', lw=2)
    a2.set_ylabel('energia cumulata [J]')
    a2.set_xlabel('tempo [s]')
    a2.set_title(f"Energia della manovra {prof['energia_manovra_J']:.2f} J "
                 f"({1000*prof['energia_manovra_Wh']:.2f} mWh), media {prof['potenza_media_W']:.2f} W")
    for a in (a1, a2):
        a.grid(True, ls=':', alpha=0.6)
    a1.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(path, format='svg')
    plt.close(fig)
    return path


def export(case_data):
    thrust, fan = case_data.thrust, case_data.fan
    prof = profile(thrust, fan)
    (case_data.folder('00_sintesi')/'potenza_manovra.json').write_text(
        json.dumps(prof, indent=1, ensure_ascii=False), encoding='utf-8')
    plot(prof, thrust, case_data.folder('01_grafici')/'potenza_manovra.svg')
    return prof
