"""
Potenza nel tempo lungo la manovra: quando la ventola lavora, quanto, e l'energia.

Manovra da fermo a fermo (0_spinta): la faccia posteriore spinge durante
l'accelerazione, nessuna spinta in crociera, la faccia anteriore frena. Ogni
faccia ha n ugelli, ciascuno con la potenza all'albero del punto di progetto.
Avvio e arresto dei motori sono istantanei (primo ordine).

L'energia e' un LIMITE SUPERIORE: la potenza e' quella del punto di progetto
(fattore di margine e disturbo residuo del volo parabolico inclusi) mantenuta
per tutto il tempo di accensione.

Accanto al limite superiore c'e la stima con i termini separati (con_disturbo):
la spinta che serve davvero in ogni fase, senza fattore di margine, con il
disturbo residuo SPINTA["disturbo_residuo_g"] costante e contrario al moto:

    accelerazione   faccia posteriore   m (a + a_d)
    crociera        faccia posteriore   m a_d            (tiene la velocita)
    frenata         faccia anteriore    m (a - a_d)      se a > a_d: il disturbo aiuta a frenare
                    faccia posteriore   m (a_d - a)      se a_d > a: frenerebbe troppo

La potenza alla spinta parziale viene dalla curva di potenza del sistema
(spinta dell'ugello in funzione della potenza all'albero) quando c'e,
altrimenti dalla legge del disco P = P* (T / T*)^1,5.
"""
import json

import numpy as np

G0 = 9.80665


def power_at(thrust_nozzle, t_star, p_star, curve=None):
    """Potenza all'albero di un ugello alla spinta data [W]."""
    if thrust_nozzle <= 0.0:
        return 0.0
    rows = [(r['spinta_ugello_N'], r['potenza_albero_W']) for r in (curve or {}).get('righe', [])
            if r.get('spinta_ugello_N') is not None and r.get('potenza_albero_W') is not None]
    rows = sorted(set(rows))
    if len(rows) >= 3 and thrust_nozzle <= rows[-1][0]:
        return float(np.interp(thrust_nozzle, [r[0] for r in rows], [r[1] for r in rows]))
    return p_star*(thrust_nozzle/t_star)**1.5


def with_disturbance(thrust, fan, curve=None):
    """Potenza ed energia con manovra e disturbo separati, senza margine; None se mancano i dati."""
    inp = thrust['input']
    if 'massa' not in inp or 'accelerazione_m_s2' not in thrust:
        return None
    n, m = inp['n_ugelli'], float(inp['massa'])
    t_end, t_a = float(inp['tempo']), float(thrust['t_accelerazione_s'])
    a, a_d = float(thrust['accelerazione_m_s2']), float(inp.get('disturbo_residuo_g', 0.0))*G0
    c = fan['best']['cases'][0]
    t_star, p_star = thrust['T_ugello_N'], c['shaft_power_W']

    def phase(name, t0, t1, force, face):
        p = n*power_at(force/n, t_star, p_star, curve)
        return dict(fase=name, faccia=face if force > 0 else '-', da_s=t0, a_s=t1,
                    spinta_faccia_N=force, potenza_faccia_W=p)

    def energy(a_dist):
        brake = m*(a - a_dist)
        ph = [phase('accelerazione', 0.0, t_a, m*(a + a_dist), 'posteriore'),
              phase('crociera', t_a, t_end - t_a, m*a_dist, 'posteriore'),
              phase('frenata', t_end - t_a, t_end, abs(brake), 'anteriore' if brake >= 0 else 'posteriore')]
        ph = [p for p in ph if p['a_s'] - p['da_s'] > 1e-12]
        return ph, sum(p['potenza_faccia_W']*(p['a_s'] - p['da_s']) for p in ph)

    phases, e_dist = energy(a_d)
    _, e_free = energy(0.0)
    hold = n*power_at(m*a_d/n, t_star, p_star, curve)
    return dict(
        disturbo_residuo_g=a_d/G0, accelerazione_manovra_m_s2=a, accelerazione_disturbo_m_s2=a_d,
        spinta_manovra_N=m*a, spinta_disturbo_N=m*a_d, fasi=phases,
        picco_W=max(p['potenza_faccia_W'] for p in phases),
        energia_J=e_dist, energia_senza_disturbo_J=e_free, energia_del_disturbo_J=e_dist - e_free,
        potenza_per_tenere_la_posizione_W=hold,
        modello_potenza=('curva di potenza del sistema' if (curve or {}).get('righe') else 'P = P* (T/T*)^1,5'),
        nota=('Senza fattore di margine. Disturbo costante e contrario al moto su un asse; '
              'potenza_per_tenere_la_posizione_W e quella di una faccia che compensa il solo '
              'disturbo, da contare per ogni asse e per tutto il tempo di volo libero.'))


def profile(thrust, fan, curve=None):
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
        con_disturbo=with_disturbance(thrust, fan, curve),
        nota=('Potenza all\'albero (elettrica = albero / rendimento di motore e '
              'regolatore, non incluso). Una faccia alla volta: picco = n ugelli x '
              'potenza di un ugello. Energia = limite superiore: potenza di '
              'progetto (margine e disturbo residuo inclusi) per tutto il tempo '
              'di accensione.'))


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


def export(case_data, curve=None):
    thrust, fan = case_data.thrust, case_data.fan
    prof = profile(thrust, fan, curve)
    (case_data.folder('00_sintesi')/'potenza_manovra.json').write_text(
        json.dumps(prof, indent=1, ensure_ascii=False), encoding='utf-8')
    plot(prof, thrust, case_data.folder('01_grafici')/'potenza_manovra.svg')
    return prof
