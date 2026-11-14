"""decisione "massa -> potenza": numeri scritti a mano, poi cartelle finte (md, json, xlsx, serie)."""
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "3_sistema"), os.path.join(ROOT, "2_ventola")]

from sistema_designer import decisione as dc
from sistema_designer import masse
from sistema_designer import confronto_varianti as cv

M, N, E = 4.0, 6, 1.5          # kg di riferimento, propulsori, esponente
LAB = dc.ETICHETTE_STATORE


def stat(p, m, e=None, spinta=None):
    return dict(P_albero_W=p, energia_J=e, m_unita_g=m, coppia_netta_mNm=None, spinta_N=spinta)


# ---------------------------------------------------------------------------
# valuta_varianti
# ---------------------------------------------------------------------------
def test_statore_leggero_che_fa_risparmiare_molto_vince():
    # senza statore -2 g (-12 g sul veicolo): ratio 3.988/4 = 0.997, ^1.5 = 0.995509
    d = dc.valuta_varianti({'Statore': stat(9.0, 100.0), 'NoStatore': stat(9.6, 98.0)},
                           M, N, E, 'Statore', LAB, 'lo statore', 2.0)
    r = d['varianti']['NoStatore']
    assert r['d_m_veicolo_g'] == pytest.approx(-12.0)
    assert r['d_m_veicolo_pct'] == pytest.approx(-0.3)
    assert r['P_eff_W'] == pytest.approx(9.6*0.995509, rel=1e-4)
    assert d['vincitore'] == 'Statore'
    assert 'conviene CON statore' in d['verdetto']


def test_statore_pesante_che_fa_risparmiare_poco_perde():
    # senza statore -60 g (-360 g sul veicolo): ratio 0.91, ^1.5 = 0.868113
    d = dc.valuta_varianti({'Statore': stat(9.0, 130.0), 'NoStatore': stat(9.05, 70.0)},
                           M, N, E, 'Statore', LAB, 'lo statore', 60.0)
    assert d['varianti']['NoStatore']['P_eff_W'] == pytest.approx(9.05*0.868113, rel=1e-4)
    assert d['vincitore'] == 'NoStatore'
    assert 'conviene senza statore' not in d['verdetto'] or 'conviene' in d['verdetto']
    assert 'Senza statore: −10.0 g' not in d['verdetto']          # -60 g, non -10
    assert 'Senza statore: −60.0 g per propulsore (−360 g sul veicolo, −9.0 %)' in d['verdetto']


def test_parita_vince_la_piu_leggera():
    # P_eff di NoStatore = 9.04*0.9985^1.5 = 9.0197: +0.22 % su 9.0, entro lo 0.5 %: vince il piu leggero
    d = dc.valuta_varianti({'Statore': stat(9.0, 100.0), 'NoStatore': stat(9.04, 99.0)},
                           M, N, E, 'Statore', LAB)
    assert d['varianti']['NoStatore']['d_P_eff_pct'] == pytest.approx(0.22, abs=0.01)
    assert d['vincitore'] == 'NoStatore'
    # a pari massa e parita di potenza vince il riferimento solo se piu leggero: qui piu pesante e peggiore
    d2 = dc.valuta_varianti({'Statore': stat(9.0, 99.0), 'NoStatore': stat(9.03, 100.0)},
                            M, N, E, 'Statore', LAB)
    assert d2['vincitore'] == 'Statore'
    # oltre lo 0.5 % vince la potenza equivalente minore anche se piu pesante
    d3 = dc.valuta_varianti({'Statore': stat(9.0, 100.0), 'NoStatore': stat(9.1, 99.0)},
                            M, N, E, 'Statore', LAB)
    assert d3['vincitore'] == 'Statore'


def test_massa_di_pareggio_coerente():
    # risparmio di pareggio = M/n * (1 - (Pref/Px)^(1/e)) = 666.667 * (1 - 0.9375^(2/3)) = 28.08 g
    d = dc.valuta_varianti({'Statore': stat(9.0, 100.0), 'NoStatore': stat(9.6, 90.0)},
                           M, N, E, 'Statore', LAB, 'lo statore', 10.0)
    be = d['varianti']['NoStatore']['risparmio_pareggio_g']
    assert be == pytest.approx(28.08, abs=0.02)
    assert 'più di 28.1 g (pesa 10.0 g)' in d['verdetto']       # 10 - 10 + 28.08
    # con quel risparmio la P_eff e uguale al riferimento
    d2 = dc.valuta_varianti({'Statore': stat(9.0, 100.0), 'NoStatore': stat(9.6, 100.0 - be)},
                            M, N, E, 'Statore', LAB)
    assert d2['varianti']['NoStatore']['d_P_eff_W'] == pytest.approx(0.0, abs=1e-6)


def test_verdetto_esteso_con_i_numeri_e_energia():
    d = dc.valuta_varianti({'Statore': stat(9.4, 100.0, e=100.0, spinta=0.5),
                            'NoStatore': stat(10.0, 84.8, e=106.0, spinta=0.5)},
                           M, N, E, 'Statore', LAB, 'lo statore', 15.2)
    r = d['varianti']['NoStatore']
    # m_tot = 4 - 0.0912 = 3.9088; ratio 0.9772; ^1.5 = 0.965993
    assert r['fattore_potenza'] == pytest.approx(0.965993, rel=1e-4)
    assert r['E_eff_J'] == pytest.approx(106.0*0.965993, rel=1e-4)
    assert r['d_eta_pct'] == pytest.approx(100*(9.4/10.0 - 1), rel=1e-6)
    t = d['verdetto']
    assert t.startswith('Senza statore: −15.2 g per propulsore (−91 g sul veicolo, −2.3 %), '
                        "potenza all'albero +0.60 W (+6.4 %); a parità di manovra, contando la massa, "
                        'potenza equivalente +0.26 W (+2.8 %)')
    assert 'conviene CON statore' in t and 'Massa di pareggio' in t


def test_parametri_non_validi_e_riferimento_assente():
    d = dc.valuta_varianti({'Statore': stat(9.0, 100.0)}, 0, N, E, 'Statore')
    assert not d['disponibile']
    d = dc.valuta_varianti({'NoStatore': stat(9.0, 100.0)}, M, N, E, 'Statore')
    assert not d['disponibile'] and 'assente' in d['motivo']


# ---------------------------------------------------------------------------
# lunghezze del tubo e classifica generale
# ---------------------------------------------------------------------------
def alt(id_, L, p, dm, dp=170.0, spinta=0.5, perd=10.0):
    return dict(id=id_, L_tubo_mm=L, potenza_W=p, delta_massa_g=dm, dp_Pa=dp, spinta_N=spinta,
                perdita_totale_Pa=perd)


def test_alternativa_accorciare_non_conviene_e_conviene():
    # -18 g per propulsore (-108 g sul veicolo): ratio 3.892/4 = 0.973, ^1.5 = 0.959776
    righe = [alt('ottimo', 137.0, 10.0, 0.0), alt('L115', 115.0, 10.60, -18.0, dp=180.0, perd=12.0)]
    d = dc.valuta_alternative(righe, 100.0, M, N, E)
    r = d['varianti']['L115']
    assert r['d_L_mm'] == pytest.approx(-22.0)
    assert r['P_eff_W'] == pytest.approx(10.6*0.959776, rel=1e-4)
    assert r['d_P_eff_pct'] == pytest.approx(100*(10.6*0.959776/10.0 - 1), rel=1e-3)
    assert r['d_eta_pct'] == pytest.approx(100*(10.0/10.6 - 1), rel=1e-6)
    assert r['d_perdita_Pa'] == pytest.approx(2.0) and r['d_dp_Pa'] == pytest.approx(10.0)
    assert r['g_per_W'] == pytest.approx(18.0/0.6) and r['W_per_g'] == pytest.approx(0.6/18.0)
    assert r['esito'] == 'NON conviene'
    assert r['frase'].startswith('Accorciando a 115 mm (−22 mm): −18.0 g per propulsore (−108 g sul veicolo), '
                                 'potenza +6.0 % (+0.60 W), rendimento −5.7 %; contando la massa P_eff +1.7 %: '
                                 'NON conviene')
    assert d['vincitore'] == 'ottimo' and 'nessuna alternativa' in d['verdetto']
    # pareggio: il tubo dovrebbe risparmiare M/n (1 - (10/10.6)^(2/3)) = 25.5 g
    assert r['risparmio_pareggio_g'] == pytest.approx(666.667*(1 - (10.0/10.6)**(2.0/3)), rel=1e-6)
    assert 'almeno +25.' in r['frase']
    # con una potenza di +3.5 % il tubo corto conviene
    righe[1] = alt('L115', 115.0, 10.35, -18.0)
    d = dc.valuta_alternative(righe, 100.0, M, N, E)
    assert d['varianti']['L115']['esito'] == 'CONVIENE' and d['vincitore'] == 'L115'
    assert 'lunghezza L115' in d['verdetto']


def catene_rank():
    return {'Statore': dict(P_albero_W=9.0, energia_J=None, m_unita_g=100.0, m_statore_g=15.0,
                            spinta_N=0.5, alternative=[alt('ottimo', 137.0, 9.0, 0.0),
                                                       alt('L115', 115.0, 9.45, -18.0)]),
            'NoStatore': dict(P_albero_W=9.1, energia_J=None, m_unita_g=40.0, m_statore_g=0.0,
                              spinta_N=0.5, alternative=[alt('ottimo', 120.0, 9.1, 0.0),
                                                         alt('L100', 100.0, 9.555, -15.0)])}


def test_classifica_generale_vince_senza_statore_125():
    c = catene_rank()
    c['NoStatore']['alternative'][0]['L_tubo_mm'] = 125.0
    d = dc.classifica(c, M, N, E)
    # NoStatore, dm = 40 - 100 = -60 g: ratio 0.91, ^1.5 = 0.868113 -> P_eff = 9.1*0.868113 = 7.9998
    assert d['vincitore'] == 'NoStatore @ 125 mm'
    assert d['varianti'][d['vincitore']]['P_eff_W'] == pytest.approx(9.1*0.868113, rel=1e-4)
    assert d['ordine'][0] == d['vincitore'] and len(d['ordine']) == 4
    assert d['parametri']['riferimento'] == 'Statore @ 137 mm'
    assert d['verdetto'].startswith('Migliore in assoluto: NoStatore a 125 mm (ottimo)')
    assert 'su Statore a 137 mm (ottimo)' in d['verdetto']
    # alternativa NoStatore L100: P = 9.1 * 9.555/9.1 = 9.555, dm = -75 g
    r = d['varianti']['NoStatore @ 100 mm']
    assert r['P_albero_W'] == pytest.approx(9.555) and r['d_m_unita_g'] == pytest.approx(-75.0)


def test_classifica_vince_il_riferimento():
    c = catene_rank()
    c['NoStatore']['m_unita_g'] = 100.0            # nessun risparmio di massa, potenza peggiore
    d = dc.classifica(c, M, N, E)
    assert d['vincitore'] == 'Statore @ 137 mm'
    assert 'il riferimento' in d['verdetto']


def test_decisione_completa_e_righe_schermo():
    par = dict(massa_rif_kg=M, n_propulsori=N, esponente=E, nota=None)
    d = dc.decisione_completa(catene_rank(), par)
    righe = dc.righe_schermo(d)
    assert 1 <= len(righe) <= 3 and righe[0].startswith('Migliore in assoluto')
    assert d['statore']['vincitore'] == 'NoStatore'
    assert set(d['alternative']) == {'Statore', 'NoStatore'}
    md = '\n'.join(dc.markdown_caso(d))
    assert 'Classifica generale' in md and 'Accorciando a 115 mm' in md
    assert not dc.decisione_completa(catene_rank(), dict(par, massa_rif_kg=None, nota='manca'))['disponibile']


# ---------------------------------------------------------------------------
# integrazione su cartelle finte
# ---------------------------------------------------------------------------
def spinta_json(root, massa=4.0):
    p = root/'1_spinta'/'spinta.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'T_ugello_N': 0.3, 'input': {'distanza': 0.2, 'tempo': 5, 'massa': massa,
                                                           'n_ugelli': 2, 'profilo': 'bang_bang'}}),
                 encoding='utf-8')


def caso_finto(root, massa=4.0):
    from test_confronto_varianti import variant
    from test_masse import fake_chain, fake_chain_json
    spinta_json(root, massa)
    for n in ('Statore', 'NoStatore'):
        fake_chain(root/n/'_x', stator=(n == 'Statore'), scale=1.0 if n == 'Statore' else 1.1)
        for sub in ('2_venturi/03_cad', '3_ventola/03_cad'):
            for f in (root/n/'_x'/sub).iterdir():
                dest = root/n/sub
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dest/f.name)
        shutil.rmtree(root/n/'_x')
        fake_chain_json(root/n, n == 'Statore', 9.96 if n == 'Statore' else 9.4, 137.0 if n == 'Statore' else 120.0)
        variant(root/n, n == 'Statore', 9.96 if n == 'Statore' else 9.4)      # completes the fake chain
        d = root/n/'2_venturi'/'05_convergenza'/'alternative'/'L100'
        d.mkdir(parents=True, exist_ok=True)
        (d/'design.json').write_text('{}', encoding='utf-8')


@pytest.fixture
def volumi_finti(monkeypatch):
    monkeypatch.setattr(masse, 'tube_volume_from_design',
                        lambda p: 6e-7 if 'L100' in str(p) else 1e-6)


def test_confronto_ha_la_sezione_decisione(tmp_path, volumi_finti):
    caso_finto(tmp_path)
    out = cv.run(tmp_path, n_propulsori=None, esponente=1.5)
    md = (out/'RISULTATO.md').read_text(encoding='utf-8')
    assert '## Decisione' in md and 'Classifica generale' in md and 'Migliore in assoluto' in md
    assert 'conviene' in md and 'Accorciando a 100 mm' in md
    data = json.loads((out/'confronto_statore.json').read_text(encoding='utf-8'))
    dec = data['decisione']
    assert dec['disponibile'] and dec['parametri']['n_propulsori'] == 2 and dec['parametri']['massa_rif_kg'] == 4.0
    assert dec['statore']['vincitore'] in ('Statore', 'NoStatore')
    assert data['sintesi'][0].startswith('Migliore in assoluto')
    from openpyxl import load_workbook
    wb = load_workbook(out/'confronto_statore.xlsx')
    assert 'Decisione' in wb.sheetnames
    celle = [str(c.value) for row in wb['Decisione'].iter_rows() for c in row if c.value is not None]
    assert any(x.startswith('Migliore in assoluto') for x in celle[:6])      # classifica in cima
    assert any('Accorciando a 100 mm' in x for x in celle)


def test_riepilogo_masse_ha_il_foglio_decisione(tmp_path, volumi_finti):
    caso_finto(tmp_path)
    path = masse.write_mass_summary(tmp_path, n_propulsori=3, esponente=1.5)
    from openpyxl import load_workbook
    wb = load_workbook(path)
    assert wb.sheetnames == ['Alternative', 'Statore', 'Decisione', 'Parametri']
    celle = [str(c.value) for row in wb['Decisione'].iter_rows() for c in row if c.value is not None]
    assert any(x.startswith('Migliore in assoluto') for x in celle)
    assert any(x.startswith('Lunghezza più conveniente') for x in celle)
    data = json.loads((tmp_path/'RIEPILOGO_masse.json').read_text(encoding='utf-8'))
    assert data['decisione']['parametri']['n_propulsori'] == 3.0
    assert data['decisione']['statore']['verdetto'].startswith('Senza statore:')


def test_serie_decisione_stessa_spinta_e_spinta_diversa(tmp_path, volumi_finti):
    from openpyxl import load_workbook
    caso_finto(tmp_path/'a', 4.0)
    caso_finto(tmp_path/'b', 4.0)
    out = masse.write_series_summary([tmp_path/'a', tmp_path/'b'], tmp_path/'s'/'confronto_casi.xlsx', ['a', 'b'])
    ws = load_workbook(out)['Decisione']
    celle = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert any('Classifica fra i casi' in x for x in celle)
    sd = json.loads((tmp_path/'s'/'confronto_casi.json').read_text(encoding='utf-8'))
    assert set(sd['casi']) == {'a', 'b'} and sd['classifica_casi']['verdetto'].startswith('Migliore fra i casi')
    # il primo caso e il riferimento dei delta: Δ massa e Δ potenza del primo sono 0
    riga_a = [c.value for c in ws[3]]
    assert riga_a[0] == 'a' and riga_a[7] == 0 and riga_a[9] == 0
    caso_finto(tmp_path/'c', 6.0)
    masse.write_series_summary([tmp_path/'a', tmp_path/'c'], tmp_path/'s2'/'confronto_casi.xlsx', ['a', 'c'])
    sd = json.loads((tmp_path/'s2'/'confronto_casi.json').read_text(encoding='utf-8'))
    assert sd['classifica_casi'] is None and 'SPINTA differente' in sd['motivo_classifica']
    assert 'massa' in sd['motivo_classifica']
