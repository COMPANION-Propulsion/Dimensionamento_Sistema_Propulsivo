"""Elementi di pala a portata imposta, modello incomprimibile anulare.

Ingresso senza swirl, velocita assiale uniforme e costante attraverso il rotore.
Lo swirl al piano pala e metà dello swirl in uscita. Nessuna induzione assiale
da rotore libero. Ipotesi, bilanci e fonti: docs/VENTURI_INPUT.md.
"""
import math
from .config import number, operating_air
from .geometry import interpolate
from .polars import PolarDomainError
from .settings import sizing_settings


def annular_velocity(diameter, hub_diameter, flow):
    d = number(diameter, 'diametro')
    h = number(hub_diameter, 'diametro mozzo', strict=False)
    q = number(flow, 'portata')
    if h >= d:
        raise ValueError('Il mozzo deve lasciare area libera positiva.')
    area = math.pi*(d*d-h*h)/4
    return area, q/area


def solve_pressure(case, design, point, polar, stations=32):
    from .bemt import air_properties
    if type(stations) is not int or stations < 2:
        raise ValueError('Richiesti almeno due anelli.')
    if sizing_settings(case)['loss_model'] != 'none':
        raise ValueError('Prandtl da rotore libero non disponibile a portata imposta.')
    polar.validate_profile(design['profile'])
    flow = number(point['volume_flow_m3_s'], 'portata')
    area, va = annular_velocity(design['outer_diameter_m'], design['hub_diameter_m'], flow)
    air = operating_air(case, point)
    rho, mu, sound = air_properties(air['temperature_K'], air['static_pressure_Pa'])
    rho = number(point.get('density_kg_m3', rho), 'densita')
    omega = number(design['rpm'], 'rpm')*2*math.pi/60
    hub, tip = design['hub_diameter_m']/2, design['outer_diameter_m']/2
    count = design['blade_count']
    dr = (tip-hub)/stations
    thrust = torque = pressure_power = swirl_power = profile_loss = 0.
    local = []
    for i in range(stations):
        r = hub+(i+.5)*dr
        s = (r-hub)/(tip-hub)
        c = interpolate(design['span_nodes'], design['chord_m'], s)
        beta = interpolate(design['span_nodes'], design['pitch_deg'], s)
        swirl = 0.
        for iteration in range(300):
            vt = omega*r-swirl
            if vt <= 0:
                raise PolarDomainError('Swirl eccessivo nel triangolo delle velocita.')
            w = math.hypot(va, vt)
            phi = math.atan2(va, vt)
            alpha = beta-math.degrees(phi)
            re, mach = rho*w*c/mu, w/sound
            cl, cd, confidence = polar.coefficients(alpha, re, mach)
            lift, drag = .5*rho*w*w*c*cl, .5*rho*w*w*c*cd
            dt = count*(lift*math.cos(phi)-drag*math.sin(phi))
            dq = count*r*(lift*math.sin(phi)+drag*math.cos(phi))
            if dt <= 0 or dq <= 0:
                raise PolarDomainError('Carico non positivo nel regime di compressione.')
            updated = dq/(4*math.pi*rho*r*r*va)
            if updated >= omega*r:
                raise PolarDomainError('Induzione tangenziale eccessiva.')
            if abs(updated-swirl)/(1+abs(swirl)) < 1e-9:
                break
            swirl = .7*swirl+.3*updated
        else:
            raise PolarDomainError('Swirl non convergente a portata imposta.')
        residual = abs(dq-4*math.pi*rho*r*r*va*swirl)/dq
        if residual > 1e-5:
            raise PolarDomainError('Bilancio del momento angolare non convergente.')
        dp_static = dt/(2*math.pi*r)
        dp_swirl = .5*rho*(2*swirl)**2
        dp_total = dp_static+dp_swirl
        dflow = va*2*math.pi*r*dr
        thrust += dt*dr
        torque += dq*dr
        pressure_power += dp_total*dflow
        swirl_power += dp_swirl*dflow
        profile_loss += count*drag*w*dr
        local.append(dict(r_m=r, axial_velocity_m_s=va, exit_swirl_m_s=2*swirl,
            alpha_deg=alpha, Re=re, Mach=max(mach, math.hypot(va,2*swirl)/sound),
            confidence=confidence, momentum_residual=residual,
            static_pressure_rise_Pa=dp_static, total_pressure_rise_Pa=dp_total,
            dthrust_dr_N_m=dt, dtorque_dr_Nm_m=dq))
    power = omega*torque
    energy_error = abs(power-pressure_power-profile_loss)/power
    if energy_error > 1e-5:
        raise PolarDomainError('Bilancio energetico non convergente.')
    return dict(thrust_rotor_N=thrust, torque_Nm=torque, shaft_power_W=power,
        total_pressure_rise_Pa=pressure_power/flow,
        axial_total_pressure_rise_Pa=(pressure_power-swirl_power)/flow,
        static_pressure_rise_Pa=thrust/area,
        fluid_power_W=pressure_power, swirl_power_W=swirl_power,
        profile_loss_power_W=profile_loss, total_pressure_efficiency=pressure_power/power,
        volume_flow_m3_s=flow, mass_flow_kg_s=rho*flow, density_kg_m3=rho,
        annular_area_m2=area, axial_blade_velocity_m_s=va,
        full_disk_velocity_m_s=flow/(math.pi*tip*tip),
        operating_point=point.get('name'), rpm=design['rpm'], air_conditions=air,
        velocity_reference='full_disk_flow', loss_model='none', local=local,
        Re_min=min(x['Re'] for x in local), Re_max=max(x['Re'] for x in local),
        Mach_max=max(x['Mach'] for x in local),
        confidence_min=min(x['confidence'] for x in local),
        momentum_residual_max=max(x['momentum_residual'] for x in local),
        energy_residual=energy_error, polar_domain_covered=True,
        model_status='prescribed_flow_uniform_annulus_no_experimental_validation')
