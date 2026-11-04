"""BEMT assiale esplorativo, polari multi-Re; nessuna correzione condotto.

Convenzione: beta dal piano del rotore, phi=atan2(Va,Vt), alpha=beta-phi.
Confronto fra forza di pala e momento assiale/tangenziale annulari.
"""
import math

from .geometry import interpolate
from .polars import PolarDomainError
from .config import operating_air, velocity_reference
from .settings import sizing_settings
from .losses import prandtl_factors


ModelDomainError = PolarDomainError


def air_properties(temperature_K, pressure_Pa):
    rho = pressure_Pa/(287.05*temperature_K)
    mu = 1.716e-5*(temperature_K/273.15)**1.5*(273.15+110.4)/(temperature_K+110.4)
    sound_speed = math.sqrt(1.4*287.05*temperature_K)
    return rho, mu, sound_speed


def solve(case, design, point, polar, stations=32):
    """Restituisce T, Q, P e campo locale; alza errore se manca soluzione.

    Per ogni anello risolve per induzione assiale a e tangenziale b usando
    residuali di quantità di moto. Perdite Prandtl opzionali; condotto escluso.
    Solo prova di calcolo rotorico; non modello validato per la ventola.
    """
    if case.get('design_mode') == 'pressure_flow':
        from .pressure_bemt import solve_pressure
        return solve_pressure(case, design, point, polar, stations)
    polar.validate_profile(design["profile"])
    loss_model = sizing_settings(case)['loss_model']
    if type(stations) is not int or stations < 2:
        raise ValueError('Richiesti almeno due anelli radiali.')
    outer = design["outer_diameter_m"]/2
    hub = design["hub_diameter_m"]/2
    omega = design.get("rpm", 12000)*2*math.pi/60
    vin = point["axial_inlet_velocity_m_s"]
    if omega <= 0 or vin < 0:
        raise ValueError("Giri o velocità non validi.")
    reference = velocity_reference(case)
    air = operating_air(case, point)
    rho, mu, sos = air_properties(air["temperature_K"], air["static_pressure_Pa"])
    B = design["blade_count"]
    dr = (outer-hub)/stations
    total_t = total_q = 0.0
    local = []
    for i in range(stations):
        r = hub+(i+.5)*dr
        s = (r-hub)/(outer-hub)
        chord = interpolate(design["span_nodes"], design["chord_m"], s)
        beta = interpolate(design["span_nodes"], design["pitch_deg"], s)
        a, b = max(vin*.2, 1.0), 0.01*omega*r
        converged = False
        for iteration in range(300):
            va, vt = vin+a, omega*r-b
            if vt <= 0 or va <= 0:
                raise ModelDomainError("Velocità locale non fisica.")
            w = math.hypot(va,vt)
            phi = math.atan2(va,vt)
            ft, fh = prandtl_factors(B,r,hub,outer,phi) if loss_model == 'prandtl_free_rotor' else (1.,1.)
            loss = ft*fh
            if loss <= 0:
                raise ModelDomainError('Fattore di perdita nullo: anello non risolvibile.')
            alpha = beta-math.degrees(phi)
            cl, cd, confidence = polar.coefficients(alpha, rho*w*chord/mu, w/sos)
            q = .5*rho*w*w
            lift, drag = q*chord*cl, q*chord*cd
            dT_dr = B*(lift*math.cos(phi)-drag*math.sin(phi))
            dQ_dr = B*r*(lift*math.sin(phi)+drag*math.cos(phi))
            if dT_dr <= 0 or dQ_dr <= 0:
                raise ModelDomainError("Carico negativo o fuori regime propulsivo.")
            # F moltiplica entrambi i bilanci di quantita di moto.
            a_new = (-vin+math.sqrt(vin*vin+dT_dr/(math.pi*rho*r*loss)))/2
            b_new = dQ_dr/(4*math.pi*rho*r*r*loss*(vin+a_new))
            if b_new >= omega*r:
                raise ModelDomainError("Induzione tangenziale eccessiva.")
            if max(abs(a_new-a)/(1+a), abs(b_new-b)/(1+b)) < 1e-8:
                converged = True
                break
            a = .7*a+.3*a_new
            b = .7*b+.3*b_new
        if not converged:
            raise ModelDomainError(f"Anello {i}: induzione non convergente.")
        re = rho*w*chord/mu
        mach = w/sos
        total_t += dT_dr*dr
        total_q += dQ_dr*dr
        residual_t = abs(dT_dr-4*math.pi*rho*r*loss*a*(vin+a))/dT_dr
        residual_q = abs(dQ_dr-4*math.pi*rho*r*r*loss*b*(vin+a))/dQ_dr
        if max(residual_t,residual_q) > 1e-5:
            raise ModelDomainError("Bilancio di quantita di moto non convergente.")
        local.append({"r_m":r,"alpha_deg":alpha,"Re":re,"Mach":mach,"confidence":confidence,
                      "F_tip":ft,"F_hub":fh,"F":loss,
                      "momentum_residual":max(residual_t,residual_q),
                      "induced_axial_m_s":a,"induced_swirl_m_s":b})
    return {"thrust_rotor_N":total_t,"torque_Nm":total_q,
            "loss_model":loss_model,"loss_factor_min":min(x['F'] for x in local),
            "operating_point":point.get('name'),"velocity_reference":reference,
            "air_conditions":air,
            "shaft_power_W":omega*total_q,"rpm":design.get("rpm",12000),
            "Re_min":min(x["Re"] for x in local),"Re_max":max(x["Re"] for x in local),
            "Mach_max":max(x["Mach"] for x in local),"local":local,
            "confidence_min":min(x["confidence"] for x in local),
            "momentum_residual_max":max(x["momentum_residual"] for x in local),
            "polar_domain_covered":True,"model_status":"numerical_polars_no_experimental_validation"}
