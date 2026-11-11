"""
Confronto terra / volo e note sui limiti del dimensionamento (solo uscite, nessun ricalcolo).

Terra / volo. Il caso e dimensionato alla pressione VENTURI["p_amb"]. In cabina, durante
le parabole, la pressione e VENTURI["p_cabina"] e l'aria e meno densa: sigma = rho_volo /
rho_terra = p_cabina / p_amb (stessa temperatura). Con geometria e giri fissati, per le
leggi di similitudine delle ventole (portata in volume invariata, pressioni proporzionali
alla densita):

    spinta, dp, potenza all'albero   x sigma
    Reynolds delle pale              x sigma

Per riavere la spinta di progetto servono giri x 1/sqrt(sigma), e allora

    potenza all'albero   x 1/sqrt(sigma)        Reynolds   x sqrt(sigma)

Primo ordine: l'effetto del Reynolds piu basso sul rendimento delle pale non e incluso.
"""
import json
import math

G0 = 9.80665


def flight(case, p_cabin):
    """Stima delle perdite in volo di un caso dimensionato a terra; None se p_cabina manca."""
    if not p_cabin:
        return None
    design = json.loads(case.design_file.read_text(encoding='utf-8'))['case']
    p_amb = float(design['p_amb'])
    thrust, c = case.thrust, case.fan['best']['cases'][0]
    rho = case.venturi['ventola']['densita_kg_m3']
    sigma = float(p_cabin)/p_amb
    k = float(thrust['input'].get('fattore_margine', 1.0))
    T, P, n, re = thrust['T_ugello_N'], c['shaft_power_W'], c['rpm'], c['Re_min']
    return dict(
        p_progetto_Pa=p_amb, p_cabina_Pa=float(p_cabin), densita_progetto_kg_m3=rho,
        densita_volo_kg_m3=rho*sigma, rapporto_densita=sigma,
        a_giri_di_progetto=dict(rpm=n, spinta_ugello_N=T*sigma, variazione_spinta_pct=100*(sigma - 1),
                                potenza_albero_W=P*sigma, margine_effettivo=k*sigma, Re_min=re*sigma),
        a_spinta_di_progetto=dict(rpm=n/math.sqrt(sigma), variazione_giri_pct=100*(1/math.sqrt(sigma) - 1),
                                  spinta_ugello_N=T, potenza_albero_W=P/math.sqrt(sigma),
                                  variazione_potenza_pct=100*(1/math.sqrt(sigma) - 1), Re_min=re*math.sqrt(sigma)),
        margine_di_progetto=k,
        nota=('Leggi di similitudine delle ventole a geometria fissa, stessa temperatura. '
              'Il calo di rendimento delle pale al Reynolds piu basso non e incluso.'))


def notes(case, power=None, coupled=None, fl=None):
    """Note da riportare negli output: cosa il dimensionamento non copre."""
    thrust = case.thrust
    inp = thrust['input']
    out = []
    n = inp['n_ugelli']
    if power:
        d = power.get('con_disturbo') or {}
        hold = (f", e tenere la posizione contro il solo disturbo costa {d['potenza_per_tenere_la_posizione_W']:.2f} W "
                f"all'albero per asse" if d else '')
        out.append(f"Potenza con piu assi: il dimensionamento calcola una faccia ({n} ugelli, picco "
                   f"{power['picco_W']:.2f} W all'albero). Il disturbo residuo agisce su tutti gli assi insieme e per "
                   f"tutto il volo libero, non solo durante la manovra: con 3 facce accese insieme il picco e "
                   f"{3*power['picco_W']:.2f} W{hold}. Batteria e corrente di picco vanno verificate su questo, fuori "
                   f"dal dimensionamento.")
    a_d = float(inp.get('disturbo_residuo_g', 0.0))*G0
    if a_d > 0 and 'massa' in inp and 'accelerazione_m_s2' in thrust:
        need = inp['massa']*(thrust['accelerazione_m_s2'] + 2*a_d)
        out.append(f"Margine: il disturbo e un valore costante di {inp['disturbo_residuo_g']:g} g. Con picchi doppi "
                   f"({2*inp['disturbo_residuo_g']:g} g) servirebbero {need:.3f} N per faccia senza margine, contro "
                   f"{thrust['T_totale_N']:.3f} N di progetto: il fattore di margine {inp.get('fattore_margine', 1):g} "
                   f"e cio che assorbe i picchi del disturbo, non una riserva in piu.")
    if fl:
        a = fl['a_giri_di_progetto']
        out.append(f"Densita: dimensionato a {fl['p_progetto_Pa']:.0f} Pa; in cabina ({fl['p_cabina_Pa']:.0f} Pa) "
                   f"la spinta a pari giri scende del {-a['variazione_spinta_pct']:.1f} % (vedi il confronto terra / volo).")
    limits = []
    if coupled:
        limits.append(f"con la ventola vera nel condotto la spinta e {coupled['scarto_spinta_pct']:+.1f} % rispetto al "
                      f"disco uniforme usato per dimensionare")
    limits += ["la bocca d'imbocco e fuori dal dominio di calcolo del condotto",
               'la perdita per il gioco di punta delle pale non e nel modello',
               f"le polari dei profili a basso Reynolds sono incerte (Reynolds minimo sulle pale "
               f"{case.fan['best']['cases'][0]['Re_min']:.0f})",
               "l'ottimizzatore della ventola e locale: l'ottimo globale non e garantito",
               'potenza all\'albero: quella elettrica richiede il rendimento di motore e regolatore']
    out.append('Limiti del modello: ' + '; '.join(limits) + '.')
    return out


def export(case, p_cabin=None, power=None, coupled=None):
    fl = flight(case, p_cabin)
    out = dict(terra_volo=fl, note=notes(case, power, coupled, fl))
    (case.folder('00_sintesi')/'note_e_limiti.json').write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
    return out


def markdown(out, level='##'):
    """Sezioni markdown del confronto terra / volo e delle note."""
    L = []
    fl = out.get('terra_volo')
    if fl:
        a, b = fl['a_giri_di_progetto'], fl['a_spinta_di_progetto']
        L += [f'{level} Dimensionato a terra, usato in volo', '',
              f"Progetto a {fl['p_progetto_Pa']:.0f} Pa (ρ = {fl['densita_progetto_kg_m3']:.3f} kg/m³); in cabina "
              f"{fl['p_cabina_Pa']:.0f} Pa (ρ = {fl['densita_volo_kg_m3']:.3f} kg/m³, rapporto {fl['rapporto_densita']:.3f}).", '',
              '| in volo | giri [rpm] | spinta per ugello [N] | potenza all\'albero [W] | Reynolds minimo |', '|---|---|---|---|---|',
              f"| agli stessi giri | {a['rpm']:.0f} | {a['spinta_ugello_N']:.4f} ({a['variazione_spinta_pct']:+.1f} %) | "
              f"{a['potenza_albero_W']:.3f} | {a['Re_min']:.0f} |",
              f"| alla stessa spinta | {b['rpm']:.0f} ({b['variazione_giri_pct']:+.1f} %) | {b['spinta_ugello_N']:.4f} | "
              f"{b['potenza_albero_W']:.3f} ({b['variazione_potenza_pct']:+.1f} %) | {b['Re_min']:.0f} |", '',
              f"Agli stessi giri il margine {fl['margine_di_progetto']:g} diventa {a['margine_effettivo']:.2f}. {fl['nota']}", '']
    if out.get('note'):
        L += [f'{level} Note e limiti', ''] + [f'- {x}' for x in out['note']] + ['']
    return L
