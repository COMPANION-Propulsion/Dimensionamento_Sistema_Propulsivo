import json
import math
import os
import tempfile
import unittest

from ventola_designer.indicatori import (area_naca, confronta, differenza_rumore_dB,
                                         fattore_squilibrio, indicatori, scrivi_confronto,
                                         tabella_confronto)

RHO = 1240.0


def run(rpm=10000.0, Z=3, corda=0.012, D=0.05, Dh=0.016, profilo='NACA0012'):
    return {'design': {'profile': profilo, 'blade_count': Z, 'outer_diameter_m': D,
                       'hub_diameter_m': Dh, 'span_nodes': [0.0, 0.5, 1.0],
                       'chord_m': [corda]*3, 'pitch_deg': [40.0, 30.0, 20.0]},
            'cases': [{'rpm': rpm}]}


def calcola(r, **kw):
    return indicatori(r['design'], r['cases'][0], **kw)


class IndicatoriTests(unittest.TestCase):
    def test_area_naca0012(self):
        self.assertAlmostEqual(area_naca('NACA0012'), 0.0822, delta=0.0822*0.02)

    def test_corda_costante_forza_e_sforzo(self):
        r = run()
        d = r['design']
        R, Rh = d['outer_diameter_m']/2, d['hub_diameter_m']/2
        om = r['cases'][0]['rpm']*2*math.pi/60
        A = area_naca('NACA0012')*0.012**2
        ind = calcola(r)
        F = RHO*A*om**2*(R*R-Rh*Rh)/2
        self.assertAlmostEqual(ind['forza_centrifuga_radice_N'], F, delta=1e-6*F)
        sigma = RHO*om**2*(R*R-Rh*Rh)/2
        self.assertAlmostEqual(ind['sforzo_centrifugo_radice_MPa']*1e6, sigma, delta=1e-6*sigma)
        self.assertAlmostEqual(ind['massa_pala_g'], RHO*A*(R-Rh)*1e3, delta=1e-6)
        self.assertAlmostEqual(ind['raggio_baricentro_mm'], (R+Rh)/2*1e3, delta=1e-6)

    def test_sforzo_indipendente_dalla_corda(self):
        s1 = calcola(run(corda=0.008))['sforzo_centrifugo_radice_MPa']
        s2 = calcola(run(corda=0.020))['sforzo_centrifugo_radice_MPa']
        self.assertAlmostEqual(s1, s2, delta=1e-9*s1)

    def test_raddoppio_giri(self):
        a, b = calcola(run(rpm=8000.0)), calcola(run(rpm=16000.0))
        self.assertAlmostEqual(b['sforzo_centrifugo_radice_MPa']/a['sforzo_centrifugo_radice_MPa'], 4.0, places=9)
        self.assertAlmostEqual(b['forza_rotante_squilibrio_N']/a['forza_rotante_squilibrio_N'], 4.0, places=9)
        self.assertAlmostEqual(b['velocita_punta_m_s']/a['velocita_punta_m_s'], 2.0, places=9)

    def test_fattore_caso_peggiore(self):
        self.assertAlmostEqual(fattore_squilibrio(2), 1.0)
        self.assertAlmostEqual(fattore_squilibrio(3), 1.0)
        self.assertAlmostEqual(fattore_squilibrio(4), math.sqrt(2))
        u3 = calcola(run(Z=3))['squilibrio_caso_peggiore_g_mm']
        u4 = calcola(run(Z=4))['squilibrio_caso_peggiore_g_mm']
        self.assertAlmostEqual(u4/u3, math.sqrt(2), places=9)

    def test_squilibrio_formula(self):
        ind = calcola(run(), tolleranza_densita=0.04)
        self.assertAlmostEqual(ind['squilibrio_caso_peggiore_g_mm'],
                               0.08*ind['massa_pala_g']*ind['raggio_baricentro_mm'], delta=1e-9)

    def test_frequenze_e_mach(self):
        ind = calcola(run(rpm=12000.0, Z=4))
        self.assertAlmostEqual(ind['frequenza_rotazione_Hz'], 200.0)
        self.assertAlmostEqual(ind['frequenza_passaggio_pale_Hz'], 800.0)
        self.assertAlmostEqual(ind['mach_punta'], ind['velocita_punta_m_s']/343.1, delta=1e-3)

    def test_inerzia_e_momento_angolare(self):
        r = run()
        d = r['design']
        R, Rh = d['outer_diameter_m']/2, d['hub_diameter_m']/2
        om = r['cases'][0]['rpm']*2*math.pi/60
        A = area_naca('NACA0012')*0.012**2
        ind = calcola(r)
        I = 3*RHO*A*(R**3-Rh**3)/3
        self.assertAlmostEqual(ind['inerzia_pale_kg_m2'], I, delta=1e-4*I)
        self.assertAlmostEqual(ind['momento_angolare_pale_kg_m2_s'], I*om, delta=1e-4*I*om)

    def test_rumore(self):
        self.assertEqual(differenza_rumore_dB(50.0, 50.0), 0.0)
        self.assertLess(differenza_rumore_dB(50.0, 40.0), 0)
        self.assertAlmostEqual(differenza_rumore_dB(1.0, 2.0, 5.0), 50*math.log10(2))
        with self.assertRaises(ValueError):
            differenza_rumore_dB(0.0, 1.0)

    def test_confronta(self):
        c = confronta(run(Z=3), run(Z=4, rpm=9000.0))
        self.assertAlmostEqual(c['velocita_punta_m_s_diff_pct'], -10.0, places=9)
        self.assertLess(c['rumore_diff_dB'], 0)
        self.assertAlmostEqual(c['frequenza_passaggio_pale_Hz_diff_pct'], 100*(36000/30000-1), places=9)

    def test_ipotesi_presente(self):
        self.assertIn('densita', calcola(run())['ipotesi'])


def run_conf(Z, rpm, energia, accettato=True):
    r = run(rpm=rpm, Z=Z)
    r['accepted'] = accettato
    r['energy_J'] = energia
    r['cases'] = [{'rpm': rpm, 'shaft_power_W': energia, 'torque_Nm': 1e-3}]
    return r


class ConfrontoTests(unittest.TestCase):
    def report(self, accettati=True):
        a, b = run_conf(3, 10000.0, 0.5, accettati), run_conf(4, 9000.0, 0.6, accettati)
        return {'runs': [a, b], 'best': a if accettati else None}

    def test_tabella(self):
        tab = tabella_confronto(self.report())
        self.assertEqual(tab['pale'], [3, 4])
        self.assertEqual(tab['scelta'], 3)
        self.assertEqual(len(tab['righe']), 16)
        for riga in tab['righe']:
            self.assertEqual(len(riga['valori']), 2)
        self.assertEqual(len(tab['rumore_dB']), 1)
        self.assertEqual(tab['rumore_dB'][0]['rispetto_a'], 3)
        self.assertLess(tab['rumore_dB'][0]['diff_dB'], 0)

    def test_nessun_accettato(self):
        rep = self.report(accettati=False)
        rep['best'] = run_conf(3, 10000.0, 0.5, False)
        self.assertIsNone(tabella_confronto(rep))

    def test_scrivi(self):
        with tempfile.TemporaryDirectory() as tmp:
            percorso = os.path.join(tmp, 'report.json')
            with open(percorso, 'w', encoding='utf-8') as f:
                json.dump(self.report(), f)
            out = os.path.join(tmp, 'out')
            os.mkdir(out)
            tab = scrivi_confronto(percorso, cartella=out)
            self.assertEqual(tab['pale'], [3, 4])
            with open(os.path.join(out, 'confronto_pale.json'), encoding='utf-8') as f:
                self.assertEqual(json.load(f)['scelta'], 3)
            with open(os.path.join(out, 'CONFRONTO_PALE.md'), encoding='utf-8') as f:
                self.assertIn('(scelta)', f.read())


if __name__ == '__main__':
    unittest.main()
