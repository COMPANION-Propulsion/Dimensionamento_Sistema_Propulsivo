"""
Decisione fra varianti con la massa sulla stessa scala delle prestazioni ("massa -> potenza").

Ogni grammo del sistema propulsivo va spinto anch'esso: la spinta richiesta e proporzionale alla
massa totale, e a geometria fissa la potenza cresce come la spinta^1.5 (disco attuatore:
T ~ rho Q^2 / A, P = Q dp ~ T^1.5 / sqrt(rho A)). Per ogni variante:

    m_tot = massa_rif + n_propulsori * (m_unita - m_unita_rif)
    P_eff = P_albero * (m_tot / massa_rif) ** esponente
    E_eff = energia della manovra * (m_tot / massa_rif) ** esponente

massa_rif = massa totale del veicolo con la variante di riferimento (SPINTA["massa"], valore fisso).
Vince la P_eff minore; in parita entro lo 0.5 % vince la variante piu leggera.

Funzioni pubbliche (tutte pure, senza file, tranne parametri_caso):
    valuta_varianti(...)   -> dict con una riga per variante, vincitore e verdetto
    valuta_alternative(...) -> lo stesso per le lunghezze del tubo (riferimento: l'ottimo)
    parametri_caso(...)    -> massa di riferimento, n. propulsori, esponente di un caso
    markdown(...), scrivi_foglio(...), righe_breve(...) -> presentazione
"""
from __future__ import annotations

import json
from pathlib import Path

TOLLERANZA_PARITA = 0.005          # 0.5 % su P_eff
ESPONENTE_DEFAULT = 1.5
ETICHETTE_STATORE = {'Statore': 'con statore', 'NoStatore': 'senza statore'}


# ---------------------------------------------------------------------------
# parametri del caso
# ---------------------------------------------------------------------------
def _json(path):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    except (OSError, ValueError):
        return None


def spinta_input(case_root):
    """Dizionario `input` di 1_spinta/spinta.json del caso (o di una sua catena), None se manca."""
    root = Path(case_root)
    for cand in (root, root/'Statore', root/'NoStatore'):
        data = _json(cand/'1_spinta'/'spinta.json')
        if data and isinstance(data.get('input'), dict):
            return data['input']
    return None


def parametri_caso(case_root, n_propulsori=None, esponente=ESPONENTE_DEFAULT):
    """dict(massa_rif_kg, n_propulsori, esponente, nota): da spinta.json e da input.

    massa_rif_kg e None (con la nota) se spinta.json non c'e; n_propulsori None = n_ugelli.
    """
    inp = spinta_input(case_root) or {}
    nota = None
    massa = inp.get('massa')
    if massa is None:
        nota = '1_spinta/spinta.json assente: massa di riferimento non nota'
    n = n_propulsori if n_propulsori is not None else inp.get('n_ugelli')
    if n is None and nota is None:
        nota = 'numero di propulsori non noto (SISTEMA["n_propulsori"] o SPINTA["n_ugelli"])'
    return dict(massa_rif_kg=None if massa is None else float(massa),
                n_propulsori=None if n is None else float(n),
                esponente=float(esponente if esponente is not None else ESPONENTE_DEFAULT),
                nota=nota)


# ---------------------------------------------------------------------------
# formule
# ---------------------------------------------------------------------------
def _pct(x, ref):
    return None if (x is None or not ref) else 100.0*x/ref


def _s(x, dec):
    """Numero con segno, meno tipografico."""
    return f'{x:+.{dec}f}'.replace('-', '−')


def _vincitore(righe):
    """Nome con P_eff minore; entro lo 0.5 % dal minimo vince la massa totale minore."""
    ok = {n: r for n, r in righe.items() if r.get('P_eff_W') is not None}
    if not ok:
        return None
    pmin = min(r['P_eff_W'] for r in ok.values())
    vicini = {n: r for n, r in ok.items() if r['P_eff_W'] <= pmin*(1 + TOLLERANZA_PARITA)}
    return min(vicini, key=lambda n: (vicini[n]['m_tot_kg'], ok[n]['P_eff_W']))


def _maiuscolo(etichetta):
    """'con statore' -> 'CON statore' (la parola che decide, in evidenza)."""
    parti = etichetta.split(' ', 1)
    if parti[0].lower() in ('con', 'senza'):
        return parti[0].upper() + (' ' + parti[1] if len(parti) > 1 else '')
    return etichetta


def valuta_varianti(varianti, massa_rif_kg, n_propulsori, esponente, riferimento,
                    etichette=None, pezzo=None, massa_pezzo_g=None):
    """Confronto "massa -> potenza" fra varianti.

    varianti: {nome: dict(P_albero_W, energia_J|None, m_unita_g, coppia_netta_mNm|None)}
    massa_pezzo_g: massa [g] del pezzo che differenzia le varianti (es. lo statore) nella variante
    di riferimento; con `pezzo` ("lo statore") serve alla frase sulla massa di pareggio.
    Ritorna dict(parametri, varianti={nome: riga}, vincitore, verdetto, riferimento).
    """
    etichette = etichette or {}
    lab = lambda n: etichette.get(n, n)
    par = dict(massa_rif_kg=massa_rif_kg, n_propulsori=n_propulsori, esponente=esponente,
               riferimento=riferimento)
    if (not massa_rif_kg or massa_rif_kg <= 0 or not n_propulsori or n_propulsori <= 0
            or not esponente or esponente <= 0):
        return dict(disponibile=False, parametri=par, varianti={}, vincitore=None, verdetto=None,
                    motivo='parametri non validi (massa di riferimento, propulsori, esponente)')
    if riferimento not in varianti:
        return dict(disponibile=False, parametri=par, varianti={}, vincitore=None, verdetto=None,
                    motivo=f'variante di riferimento {riferimento!r} assente')
    ref = varianti[riferimento]
    mref = ref.get('m_unita_g')
    pref = ref.get('P_albero_W')
    righe, scartate = {}, []

    def _eta(v):
        t, pp = v.get('spinta_N'), v.get('P_albero_W')
        return t/pp if (t and pp and pp > 0) else None

    eta_ref = _eta(ref)
    for nome, v in varianti.items():
        m, p = v.get('m_unita_g'), v.get('P_albero_W')
        if m is None or p is None or mref is None or pref is None:
            scartate.append(nome)
            continue
        dm = m - mref
        dm_veicolo = n_propulsori*dm
        m_tot = massa_rif_kg + dm_veicolo*1e-3
        if m_tot <= 0:
            scartate.append(nome)
            continue
        fattore = (m_tot/massa_rif_kg)**esponente
        p_eff = p*fattore
        e = v.get('energia_J')
        e_ref = ref.get('energia_J')
        e_eff = None if e is None else e*fattore
        e_eff_ref = e_ref                      # il riferimento ha fattore 1
        riga = dict(
            m_unita_g=m, d_m_unita_g=dm, d_m_unita_pct=_pct(dm, mref),
            d_m_veicolo_g=dm_veicolo, d_m_veicolo_pct=_pct(dm_veicolo*1e-3, massa_rif_kg),
            m_tot_kg=m_tot, fattore_potenza=fattore,
            P_albero_W=p, d_P_W=p - pref, d_P_pct=_pct(p - pref, pref),
            P_eff_W=p_eff, d_P_eff_W=p_eff - pref, d_P_eff_pct=_pct(p_eff - pref, pref),
            energia_J=e, E_eff_J=e_eff,
            d_E_eff_pct=None if (e_eff is None or not e_eff_ref) else _pct(e_eff - e_eff_ref, e_eff_ref),
            coppia_netta_mNm=v.get('coppia_netta_mNm'),
            risparmio_g=-dm, risparmio_pareggio_g=None)
        eta = _eta(v)
        riga.update(eta_N_W=eta,
                    d_eta_pct=None if (eta is None or not eta_ref) else _pct(eta - eta_ref, eta_ref),
                    L_tubo_mm=v.get('L_tubo_mm'), dp_Pa=v.get('dp_Pa'), perdita_Pa=v.get('perdita_Pa'))
        for k_in, k_d, k_p in (('L_tubo_mm', 'd_L_mm', None), ('dp_Pa', 'd_dp_Pa', 'd_dp_pct'),
                               ('perdita_Pa', 'd_perdita_Pa', None)):
            a, b = v.get(k_in), ref.get(k_in)
            riga[k_d] = None if (a is None or b is None) else a - b
            if k_p:
                riga[k_p] = None if (a is None or not b) else _pct(a - b, b)
        riga['g_per_W'] = None if abs(p - pref) < 1e-12 else (-dm)/(p - pref)
        riga['W_per_g'] = None if abs(dm) < 1e-12 else (p - pref)/(-dm)
        if nome != riferimento and p > 0:
            # risparmio di massa per propulsore con cui P_eff(variante) = P(riferimento)
            riga['risparmio_pareggio_g'] = (massa_rif_kg*1e3/n_propulsori
                                            * (1 - (pref/p)**(1.0/esponente)))
        righe[nome] = riga
    if riferimento not in righe:
        return dict(disponibile=False, parametri=par, varianti=righe, vincitore=None, verdetto=None,
                    motivo='dati del riferimento incompleti (potenza o massa)')
    vinc = _vincitore(righe)
    ordine = sorted(righe, key=lambda n: righe[n]['P_eff_W'])
    if vinc in ordine:
        ordine.remove(vinc)
        ordine.insert(0, vinc)
    out = dict(disponibile=True, parametri=par, varianti=righe, vincitore=vinc, scartate=scartate,
               ordine=ordine, verdetto=None, motivo=None)
    out['verdetto'] = _verdetto(out, etichette, pezzo, massa_pezzo_g)
    return out


def _verdetto(dec, etichette, pezzo, massa_pezzo_g):
    righe, ref, par = dec['varianti'], dec['parametri']['riferimento'], dec['parametri']
    lab = lambda n: etichette.get(n, n)
    altri = [n for n in righe if n != ref]
    if not altri:
        return f"Una sola variante ({lab(ref)}): nessun confronto."
    due = len(righe) == 2
    frasi = []
    for n in altri:
        r = righe[n]
        testo = (f"{lab(n)[:1].upper() + lab(n)[1:]}: {_s(r['d_m_unita_g'], 1)} g per propulsore "
                 f"({_s(r['d_m_veicolo_g'], 0)} g sul veicolo, {_s(r['d_m_veicolo_pct'], 1)} %), "
                 f"potenza all'albero {_s(r['d_P_W'], 2)} W ({_s(r['d_P_pct'], 1)} %); "
                 f"a parità di manovra, contando la massa, potenza equivalente "
                 f"{_s(r['d_P_eff_W'], 2)} W ({_s(r['d_P_eff_pct'], 1)} %)")
        if r.get('d_E_eff_pct') is not None:
            testo += f", energia equivalente {_s(r['d_E_eff_pct'], 1)} %"
        if due:
            testo += f": conviene {_maiuscolo(lab(dec['vincitore']))}."
        else:
            testo += '.'
        frasi.append(testo)
    for n in altri:
        r = righe[n]
        be = r.get('risparmio_pareggio_g')
        if be is None:
            continue
        sav = r['risparmio_g']
        if pezzo and massa_pezzo_g is not None:
            t = massa_pezzo_g - sav + be
            if t <= 0:
                frasi.append(f"Massa di pareggio: {lab(n)} conviene anche se {pezzo} non pesasse nulla "
                             f"(le altre differenze di massa già bastano).")
            else:
                frasi.append(f"Massa di pareggio: {pezzo} converrebbe togliendolo solo se pesasse "
                             f"più di {t:.1f} g (pesa {massa_pezzo_g:.1f} g).")
        else:
            frasi.append(f"Massa di pareggio: {lab(n)} è alla pari con {lab(ref)} con un risparmio di "
                         f"massa di {_s(be, 1)} g per propulsore (ora {_s(sav, 1)} g).")
    if not due:
        frasi.append(f"Conviene: {_maiuscolo(lab(dec['vincitore']))}.")
    return ' '.join(frasi)


def _esito(r):
    d = r['d_P_eff_pct']
    if d is None:
        return None
    return ('CONVIENE' if d < -100*TOLLERANZA_PARITA else
            'NON conviene' if d > 100*TOLLERANZA_PARITA else 'indifferente (entro 0.5 %)')


def _frase_alternativa(r):
    dl = r.get('d_L_mm')
    verbo = 'Accorciando' if (dl or 0) < 0 else 'Allungando'
    t = (f"{verbo} a {r['L_tubo_mm']:.0f} mm ({_s(dl, 0)} mm): {_s(r['d_m_unita_g'], 1)} g per propulsore "
         f"({_s(r['d_m_veicolo_g'], 0)} g sul veicolo), potenza {_s(r['d_P_pct'], 1)} % ({_s(r['d_P_W'], 2)} W)")
    if r.get('d_eta_pct') is not None:
        t += f", rendimento {_s(r['d_eta_pct'], 1)} %"
    t += f"; contando la massa P_eff {_s(r['d_P_eff_pct'], 1)} %: {r['esito']}"
    be = r.get('risparmio_pareggio_g')
    if be is not None:
        t += (f" (pareggio: il tubo dovrebbe risparmiare almeno {_s(be, 1)} g per propulsore, "
              f"ora {_s(r['risparmio_g'], 1)} g)")
    return t + '.'


def valuta_alternative(righe_alt, m_catena_g, massa_rif_kg, n_propulsori, esponente):
    """Lunghezze del tubo contando la massa (riferimento: l'ottimo), una frase per riga.

    righe_alt: righe di masses_of_chain()['alternative'] (id, L_tubo_mm, dp_Pa, potenza_W,
    delta_massa_g, spinta_N, perdita_totale_Pa); m_catena_g: massa tubo + rotore + statore
    della catena (l'ottimo).
    """
    var, etich = {}, {}
    for a in righe_alt:
        if a.get('potenza_W') is None or a.get('delta_massa_g') is None or m_catena_g is None:
            continue
        var[a['id']] = dict(P_albero_W=a['potenza_W'], energia_J=None, m_unita_g=m_catena_g + a['delta_massa_g'],
                            coppia_netta_mNm=None, spinta_N=a.get('spinta_N'), dp_Pa=a.get('dp_Pa'),
                            perdita_Pa=a.get('perdita_totale_Pa'), L_tubo_mm=a.get('L_tubo_mm'))
        etich[a['id']] = (f"lunghezza {a['id']}" if a.get('L_tubo_mm') is None
                          else f"lunghezza {a['id']} ({a['L_tubo_mm']:.0f} mm)")
    if 'ottimo' not in var:
        return dict(disponibile=False, parametri=dict(riferimento='ottimo'), varianti={},
                    vincitore=None, verdetto=None,
                    motivo='ottimo senza potenza o massa: alternative non valutabili')
    dec = valuta_varianti(var, massa_rif_kg, n_propulsori, esponente, 'ottimo', etich)
    if not dec['disponibile']:
        return dec
    frasi = {}
    for n, r in dec['varianti'].items():
        r['esito'] = None if n == 'ottimo' else _esito(r)
        if n != 'ottimo' and r['L_tubo_mm'] is not None and r['d_L_mm'] is not None:
            r['frase'] = _frase_alternativa(r)
            frasi[n] = r['frase']
    dec['frasi'] = frasi
    v = dec['vincitore']
    r = dec['varianti'][v]
    if v == 'ottimo':
        dec['verdetto'] = (f"Lunghezza più conveniente contando la massa: l'ottimo "
                           f"({etich['ottimo']}), potenza equivalente {r['P_eff_W']:.3f} W; "
                           f"nessuna alternativa fa meglio.")
    else:
        dec['verdetto'] = (f"Lunghezza più conveniente contando la massa: {etich[v]}, potenza equivalente "
                           f"{r['P_eff_W']:.3f} W ({_s(r['d_P_eff_pct'], 1)} % sull'ottimo), "
                           f"massa {_s(r['d_m_unita_g'], 1)} g per propulsore, potenza all'albero "
                           f"{_s(r['d_P_pct'], 1)} %.")
    return dec


def _candidati(catene):
    """{chiave: dati} di ogni catena x lunghezza (ottimo + alternative). La potenza di un'alternativa
    e quella all'albero della catena scalata col rapporto di potenza del venturi."""
    cand, etich, rif = {}, {}, None
    for nome, c in catene.items():
        base = nome or 'catena'
        alt = [a for a in (c.get('alternative') or []) if a.get('potenza_W') is not None
               and a.get('delta_massa_g') is not None]
        ott = next((a for a in alt if a.get('id') == 'ottimo'), None)
        if ott is None or not ott['potenza_W'] or c.get('m_unita_g') is None or c.get('P_albero_W') is None:
            cand[base] = dict(P_albero_W=c.get('P_albero_W'), energia_J=c.get('energia_J'),
                              m_unita_g=c.get('m_unita_g'), coppia_netta_mNm=c.get('coppia_netta_mNm'),
                              spinta_N=c.get('spinta_N'), L_tubo_mm=c.get('L_tubo_mm'),
                              variante=base, id='ottimo')
            etich[base] = base
            if nome in ('Statore', '') or rif is None:
                rif = base
            continue
        for a in alt:
            ratio = a['potenza_W']/ott['potenza_W']
            L = a.get('L_tubo_mm')
            key = f"{base} @ {L:.0f} mm" if L is not None else f"{base} @ {a['id']}"
            if key in cand:
                key += f" ({a['id']})"
            e = c.get('energia_J')
            cand[key] = dict(P_albero_W=c['P_albero_W']*ratio, energia_J=None if e is None else e*ratio,
                             m_unita_g=c['m_unita_g'] + a['delta_massa_g'],
                             coppia_netta_mNm=c.get('coppia_netta_mNm'),
                             spinta_N=a.get('spinta_N') or c.get('spinta_N'), L_tubo_mm=L,
                             dp_Pa=a.get('dp_Pa'), perdita_Pa=a.get('perdita_totale_Pa'),
                             variante=base, id=a['id'])
            etich[key] = ((f"{base} a {L:.0f} mm" if L is not None else f"{base} ({a['id']})")
                          + (' (ottimo)' if a['id'] == 'ottimo' else ''))
            if a['id'] == 'ottimo' and (nome in ('Statore', '') or rif is None):
                rif = key
    return cand, etich, rif


def classifica(catene, massa_rif_kg, n_propulsori, esponente):
    """Classifica generale: ogni variante x lunghezza, ordinata per P_eff (riferimento: Statore, ottimo)."""
    cand, etich, rif = _candidati(catene)
    cand = {k: v for k, v in cand.items() if v.get('P_albero_W') is not None and v.get('m_unita_g') is not None}
    if rif not in cand:
        rif = next(iter(cand), None)
    if rif is None:
        return dict(disponibile=False, parametri={}, varianti={}, vincitore=None, verdetto=None,
                    motivo='nessun candidato con potenza e massa', candidati={}, etichette=etich)
    dec = valuta_varianti(cand, massa_rif_kg, n_propulsori, esponente, rif, etich)
    dec.update(candidati=cand, etichette=etich)
    if not dec['disponibile']:
        return dec
    v, r = dec['vincitore'], dec['varianti'][dec['vincitore']]
    if v == rif:
        dec['verdetto'] = (f"Migliore in assoluto: {etich[rif]}, il riferimento; contando la massa nessuna "
                           f"delle altre {len(cand) - 1} combinazioni fa meglio "
                           f"(potenza equivalente {r['P_eff_W']:.3f} W).")
    else:
        t = (f"Migliore in assoluto: {etich[v]}: potenza equivalente {r['P_eff_W']:.3f} W "
             f"({_s(r['d_P_eff_pct'], 1)} % su {etich[rif]}), {_s(r['d_m_unita_g'], 1)} g per propulsore "
             f"({_s(r['d_m_veicolo_g'], 0)} g sul veicolo), potenza all'albero {_s(r['d_P_pct'], 1)} %")
        if r.get('d_eta_pct') is not None:
            t += f", rendimento {_s(r['d_eta_pct'], 1)} %"
        dec['verdetto'] = t + '.'
    return dec


def decisione_completa(catene, par, pezzo='lo statore'):
    """Tutto il caso: Statore/NoStatore, alternative per catena, classifica generale.

    catene: {nome: dict(P_albero_W, energia_J, coppia_netta_mNm, m_unita_g, m_statore_g, spinta_N,
    alternative=[righe])}; par = parametri_caso(...). Ogni parte puo risultare non disponibile.
    """
    def nd(motivo):
        return dict(disponibile=False, motivo=motivo, parametri=par, varianti={}, vincitore=None,
                    verdetto=None)

    if par.get('nota') or not par.get('massa_rif_kg'):
        m = par.get('nota') or 'massa di riferimento assente'
        return dict(disponibile=False, motivo=m, parametri=par, statore=nd(m), alternative={},
                    classifica=nd(m))
    M, n, e = par['massa_rif_kg'], par['n_propulsori'], par['esponente']
    out = dict(disponibile=True, motivo=None, parametri=par, statore=None, alternative={}, classifica=None)
    if 'Statore' in catene and 'NoStatore' in catene:
        data = {k: dict(P_albero_W=catene[k].get('P_albero_W'), energia_J=catene[k].get('energia_J'),
                        m_unita_g=catene[k].get('m_unita_g'), coppia_netta_mNm=catene[k].get('coppia_netta_mNm'))
                for k in ('Statore', 'NoStatore')}
        out['statore'] = valuta_varianti(data, M, n, e, 'Statore', ETICHETTE_STATORE, pezzo=pezzo,
                                         massa_pezzo_g=catene['Statore'].get('m_statore_g'))
    elif catene:
        out['statore'] = nd('serve la coppia Statore / NoStatore')
    for nome, c in catene.items():
        alt = c.get('alternative') or []
        out['alternative'][nome or 'catena'] = (
            valuta_alternative(alt, c.get('m_unita_g'), M, n, e) if alt else
            nd('alternative di lunghezza assenti'))
    out['classifica'] = classifica(catene, M, n, e) if catene else nd('nessuna catena')
    return out


def righe_schermo(dec, prefisso=''):
    """Al piu 3 righe del verdetto per lo schermo e il riepilogo: classifica, statore, lunghezza."""
    if not dec:
        return []
    out = []
    cl = dec.get('classifica')
    if cl and cl.get('disponibile') and cl.get('verdetto'):
        out.append(prefisso + cl['verdetto'])
    st = dec.get('statore')
    if st and st.get('disponibile') and st.get('verdetto'):
        out.append(prefisso + st['verdetto'].split(' Massa di pareggio')[0])
    alt = [a for a in (dec.get('alternative') or {}).values() if a.get('disponibile') and a.get('verdetto')]
    if alt:
        out.append(prefisso + alt[0]['verdetto'])
    return out[:3]


def vincitore_etichetta(dec, etichette=None):
    if not dec or not dec.get('vincitore'):
        return None
    return (etichette or {}).get(dec['vincitore'], dec['vincitore'])


# ---------------------------------------------------------------------------
# presentazione
# ---------------------------------------------------------------------------
COLONNE = (
    ('variante', None, 0), ('massa unità [g]', 'm_unita_g', 2), ('Δ massa unità [g]', 'd_m_unita_g', 2),
    ('Δ massa unità [%]', 'd_m_unita_pct', 2), ('Δ massa veicolo [g]', 'd_m_veicolo_g', 1),
    ('Δ massa veicolo [%]', 'd_m_veicolo_pct', 2), ('massa veicolo [kg]', 'm_tot_kg', 4),
    ('fattore (m/m0)^esp', 'fattore_potenza', 4), ('P albero [W]', 'P_albero_W', 3),
    ('Δ P [W]', 'd_P_W', 3), ('Δ P [%]', 'd_P_pct', 2), ('P equivalente [W]', 'P_eff_W', 3),
    ('Δ P eq. [W]', 'd_P_eff_W', 3), ('Δ P eq. [%]', 'd_P_eff_pct', 2),
    ('energia manovra [J]', 'energia_J', 2), ('energia eq. [J]', 'E_eff_J', 2),
    ('Δ energia eq. [%]', 'd_E_eff_pct', 2), ('coppia netta [mN·m]', 'coppia_netta_mNm', 3),
    ('risparmio di pareggio [g/propulsore]', 'risparmio_pareggio_g', 2))


def _cella(x, dec):
    return None if x is None else round(x, dec)


def parametri_testo(dec):
    p = dec.get('parametri') or {}
    if not p.get('massa_rif_kg'):
        return None
    return (f"massa di riferimento {p['massa_rif_kg']:g} kg (veicolo con {p.get('riferimento')}), "
            f"{p['n_propulsori']:g} propulsori, potenza ∝ massa^{p['esponente']:g}")


def markdown(dec, titolo='## Decisione', intro=None, etichette=None):
    """Righe markdown della sezione Decisione."""
    L = [titolo, '']
    if intro:
        L += [intro, '']
    if not dec or not dec.get('disponibile'):
        L += [f"Decisione non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}.", '']
        return L
    pt = parametri_testo(dec)
    L += [f"**{dec['verdetto']}**", '']
    if pt:
        L += [f"Criterio massa → potenza: {pt}. Parità entro 0.5 % su P equivalente: vince la più leggera.", '']
    L += ['| variante | Δ massa unità [g] | Δ massa veicolo [%] | P albero [W] | Δ P [%] | '
          'P equivalente [W] | Δ P eq. [%] | energia eq. [J] |', '|---|---|---|---|---|---|---|---|']
    f = lambda x, d: '—' if x is None else f'{x:.{d}f}'
    for n, r in dec['varianti'].items():
        etic = (etichette or {}).get(n, n)
        L.append(f"| {etic}{' (rif.)' if n == dec['parametri']['riferimento'] else ''}"
                 f"{' **←**' if n == dec['vincitore'] else ''} | {f(r['d_m_unita_g'], 1)} | "
                 f"{f(r['d_m_veicolo_pct'], 2)} | {f(r['P_albero_W'], 3)} | {f(r['d_P_pct'], 1)} | "
                 f"{f(r['P_eff_W'], 3)} | {f(r['d_P_eff_pct'], 1)} | {f(r['E_eff_J'], 2)} |")
    L.append('')
    return L


def scrivi_blocco(ws, riga, titolo, dec):
    """Scrive un blocco (titolo, tabella, verdetto) in un foglio da `riga`; ritorna la riga libera."""
    from openpyxl.styles import Font, PatternFill
    ws.cell(row=riga, column=1, value=titolo).font = Font(bold=True)
    riga += 1
    if not dec or not dec.get('disponibile'):
        ws.cell(row=riga, column=1, value=f"non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}")
        return riga + 2
    cols = [c for c in COLONNE if c[1] != 'L_tubo_mm']
    extra = any(r.get('L_tubo_mm') is not None for r in dec['varianti'].values())
    head = [c[0] for c in cols] + (['L tubo [mm]'] if extra else [])
    for c, k in enumerate(head, 1):
        cell = ws.cell(row=riga, column=c, value=k)
        cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
    riga += 1
    for n, r in dec['varianti'].items():
        vals = [n] + [_cella(r.get(k), d) for _, k, d in cols[1:]] + ([r.get('L_tubo_mm')] if extra else [])
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=riga, column=c, value=v)
            if n == dec['vincitore']:
                cell.font, cell.fill = Font(bold=True), PatternFill('solid', fgColor='E2EFDA')
        riga += 1
    ws.cell(row=riga, column=1, value=dec['verdetto'])
    pt = parametri_testo(dec)
    if pt:
        ws.cell(row=riga + 1, column=1, value=f'Parametri: {pt}')
    return riga + 3


def foglio_decisione(wb, blocchi, nome='Decisione'):
    """Foglio con piu blocchi [(titolo, dec)]; ritorna il foglio."""
    ws = wb.create_sheet(nome)
    ws.column_dimensions['A'].width = 34
    for c in range(2, 22):
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = 18
    riga = 1
    for titolo, dec in blocchi:
        riga = scrivi_blocco(ws, riga, titolo, dec)
    return ws


def righe_breve(dec, etichette=None, prefisso=''):
    """Una riga di testo per lo schermo / il riepilogo; None se non disponibile."""
    if not dec or not dec.get('disponibile') or not dec.get('verdetto'):
        return None
    return prefisso + dec['verdetto']


# ---------------------------------------------------------------------------
# presentazione: classifica e tabella di compromesso delle lunghezze
# ---------------------------------------------------------------------------
def _f(x, d):
    return '—' if x is None else f'{x:.{d}f}'


def markdown_classifica(dec, titolo='### Classifica generale (variante × lunghezza)'):
    if not dec or not dec.get('disponibile'):
        return [titolo, '', f"Non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}.", '']
    et = dec.get('etichette') or {}
    L = [titolo, '', f"**{dec['verdetto']}**", '',
         '| # | candidato | massa unità [g] | Δ massa unità [g] | Δ massa veicolo [g] | P albero [W] | '
         'P equivalente [W] | Δ P eq. [%] | rendimento [N/W] | Δ rend. [%] |',
         '|---|---|---|---|---|---|---|---|---|---|']
    for i, n in enumerate(dec['ordine'], 1):
        r = dec['varianti'][n]
        L.append(f"| {i} | {et.get(n, n)}{' (rif.)' if n == dec['parametri']['riferimento'] else ''} | "
                 f"{_f(r['m_unita_g'], 1)} | {_f(r['d_m_unita_g'], 1)} | {_f(r['d_m_veicolo_g'], 0)} | "
                 f"{_f(r['P_albero_W'], 3)} | {_f(r['P_eff_W'], 3)} | {_f(r['d_P_eff_pct'], 1)} | "
                 f"{_f(r['eta_N_W'], 3)} | {_f(r['d_eta_pct'], 1)} |")
    L += ['', 'Per le alternative di lunghezza la potenza all\'albero è quella della catena scalata col '
          'rapporto di potenza del venturi (alternativa / ottimo).', '']
    return L


COLONNE_ALT = (('lunghezza [mm]', 'L_tubo_mm', 1), ('Δ L [mm]', 'd_L_mm', 1),
               ('Δ massa tubo/propulsore [g]', 'd_m_unita_g', 2), ('Δ massa tubo/propulsore [%]', 'd_m_unita_pct', 2),
               ('Δ massa veicolo [g]', 'd_m_veicolo_g', 1), ('Δ massa veicolo [%]', 'd_m_veicolo_pct', 2),
               ('Δp [Pa]', 'dp_Pa', 2), ('Δ Δp [Pa]', 'd_dp_Pa', 2), ('Δ Δp [%]', 'd_dp_pct', 2),
               ('P albero [W]', 'P_albero_W', 3), ('Δ P [W]', 'd_P_W', 3), ('Δ P [%]', 'd_P_pct', 2),
               ('rendimento [N/W]', 'eta_N_W', 4), ('Δ rendimento [%]', 'd_eta_pct', 2),
               ('Δ perdite [Pa]', 'd_perdita_Pa', 2), ('P equivalente [W]', 'P_eff_W', 3),
               ('Δ P eq. [W]', 'd_P_eff_W', 3), ('Δ P eq. [%]', 'd_P_eff_pct', 2),
               ('g risparmiati per W perso', 'g_per_W', 2), ('W persi per g risparmiato', 'W_per_g', 4),
               ('massa di pareggio: risparmio [g/propulsore]', 'risparmio_pareggio_g', 2),
               ('esito', 'esito', 0))


def markdown_alternative(dec, titolo='### Lunghezza del tubo: compromesso rispetto all\'ottimo'):
    if not dec or not dec.get('disponibile'):
        return [titolo, '', f"Non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}.", '']
    L = [titolo, '', f"**{dec['verdetto']}**", '']
    cols = [(h, k, d) for h, k, d in COLONNE_ALT if k in ('L_tubo_mm', 'd_L_mm', 'd_m_unita_g', 'd_m_veicolo_g',
                                                         'd_dp_Pa', 'd_P_pct', 'd_eta_pct', 'd_perdita_Pa',
                                                         'P_eff_W', 'd_P_eff_pct', 'g_per_W', 'esito')]
    L += ['| ' + ' | '.join(h for h, _, _ in cols) + ' |', '|' + '---|'*len(cols)]
    for n, r in dec['varianti'].items():
        cells = [(r.get(k) if k == 'esito' else _f(r.get(k), d)) or '—' for _, k, d in cols]
        L.append('| ' + ' | '.join(cells) + ' |')
    L += [''] + [f'- {t}' for t in (dec.get('frasi') or {}).values()] + ['']
    return L


def scrivi_blocco_alternative(ws, riga, titolo, dec):
    from openpyxl.styles import Font, PatternFill
    ws.cell(row=riga, column=1, value=titolo).font = Font(bold=True)
    riga += 1
    if not dec or not dec.get('disponibile'):
        ws.cell(row=riga, column=1, value=f"non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}")
        return riga + 2
    for c, (h, _, _) in enumerate((('id', 0, 0),) + COLONNE_ALT, 1):
        cell = ws.cell(row=riga, column=c, value=h)
        cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
    riga += 1
    for n, r in dec['varianti'].items():
        vals = [n] + [r.get(k) if k == 'esito' else _cella(r.get(k), d) for _, k, d in COLONNE_ALT]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=riga, column=c, value=v)
            if n == dec['vincitore']:
                cell.font, cell.fill = Font(bold=True), PatternFill('solid', fgColor='E2EFDA')
        riga += 1
    ws.cell(row=riga, column=1, value=dec['verdetto'])
    for i, t in enumerate((dec.get('frasi') or {}).values(), 1):
        ws.cell(row=riga + i, column=1, value=t)
    return riga + len(dec.get('frasi') or {}) + 2


def scrivi_blocco_classifica(ws, riga, titolo, dec):
    from openpyxl.styles import Font, PatternFill
    ws.cell(row=riga, column=1, value=titolo).font = Font(bold=True)
    riga += 1
    if not dec or not dec.get('disponibile'):
        ws.cell(row=riga, column=1, value=f"non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}")
        return riga + 2
    ws.cell(row=riga, column=1, value=dec['verdetto']).font = Font(bold=True)
    riga += 1
    cols = (('posizione', None, 0), ('candidato', None, 0), ('massa unità [g]', 'm_unita_g', 2),
            ('Δ massa unità [g]', 'd_m_unita_g', 2), ('Δ massa veicolo [g]', 'd_m_veicolo_g', 1),
            ('Δ massa veicolo [%]', 'd_m_veicolo_pct', 2), ('P albero [W]', 'P_albero_W', 3),
            ('P equivalente [W]', 'P_eff_W', 3), ('Δ P eq. [W]', 'd_P_eff_W', 3), ('Δ P eq. [%]', 'd_P_eff_pct', 2),
            ('rendimento [N/W]', 'eta_N_W', 4), ('Δ rendimento [%]', 'd_eta_pct', 2),
            ('Δ P albero [%]', 'd_P_pct', 2), ('energia eq. [J]', 'E_eff_J', 2))
    for c, (h, _, _) in enumerate(cols, 1):
        cell = ws.cell(row=riga, column=c, value=h)
        cell.fill, cell.font = PatternFill('solid', fgColor='1F4E78'), Font(bold=True, color='FFFFFF')
    riga += 1
    et = dec.get('etichette') or {}
    for i, n in enumerate(dec['ordine'], 1):
        r = dec['varianti'][n]
        vals = [i, et.get(n, n)] + [_cella(r.get(k), d) for _, k, d in cols[2:]]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=riga, column=c, value=v)
            if i == 1:
                cell.font, cell.fill = Font(bold=True), PatternFill('solid', fgColor='E2EFDA')
        riga += 1
    return riga + 1


def foglio_caso(wb, dec, nome='Decisione'):
    """Foglio Decisione di un caso: classifica generale in cima, poi Statore/NoStatore, poi le lunghezze."""
    ws = wb.create_sheet(nome)
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 30
    for c in range(3, 26):
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = 18
    riga = scrivi_blocco_classifica(ws, 1, 'Classifica generale: variante × lunghezza del tubo', dec.get('classifica'))
    if dec.get('statore') is not None:
        riga = scrivi_blocco(ws, riga, 'Statore contro NoStatore (massa → potenza)', dec['statore'])
    for n, a in (dec.get('alternative') or {}).items():
        riga = scrivi_blocco_alternative(ws, riga, f'Lunghezza del tubo{": " + n if n != "catena" else ""} '
                                         f'(riferimento: ottimo)', a)
    return ws


def markdown_caso(dec, etichette=None):
    """Sezione markdown 'Decisione' di un caso, classifica in cima."""
    L = ['## Decisione', '']
    if not dec or not dec.get('disponibile'):
        return L + [f"Decisione non calcolabile: {(dec or {}).get('motivo', 'dati assenti')}.", '']
    pt = parametri_testo(dec['classifica']) if dec.get('classifica') and dec['classifica'].get('disponibile') else None
    if pt:
        L += [f'Criterio massa → potenza: {pt}. Parità entro 0.5 % su P equivalente: vince la più leggera.', '']
    L += markdown_classifica(dec.get('classifica'))
    if dec.get('statore') is not None:
        L += markdown(dec['statore'], '### Statore contro NoStatore', etichette=etichette or ETICHETTE_STATORE)
    for n, a in (dec.get('alternative') or {}).items():
        L += markdown_alternative(a, f"### Lunghezza del tubo{': ' + n if n != 'catena' else ''} "
                                     f"(compromesso rispetto all'ottimo)")
    return L


def spinta_ugello(case_root):
    """T_ugello_N di 1_spinta/spinta.json del caso (o di una catena), None se manca."""
    root = Path(case_root)
    for cand in (root, root/'Statore', root/'NoStatore'):
        data = _json(cand/'1_spinta'/'spinta.json')
        if data and data.get('T_ugello_N') is not None:
            return float(data['T_ugello_N'])
    return None


def energia_manovra(chain_folder):
    data = _json(Path(chain_folder)/'4_sistema'/'00_sintesi'/'potenza_manovra.json') or {}
    return data.get('energia_manovra_J')
