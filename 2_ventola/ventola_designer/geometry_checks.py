"""Screening delle sezioni cilindriche; non collision detection 3D o analisi strutturale."""
from functools import lru_cache
import math
from .geometry import naca4, interpolate


@lru_cache(maxsize=32)
def profile_data(profile):
    contour = naca4(profile,80)
    upper = list(reversed(contour[:81]))
    lower = contour[80:]
    thickness = max(math.hypot(u[0]-l[0],u[1]-l[1]) for u,l in zip(upper,lower))
    return tuple(contour), thickness


def screen_geometry(design, count=65, min_thickness=0., min_gap=0.):
    if type(count) is not int or count<3:
        raise ValueError('Almeno tre stazioni geometriche richieste.')
    if any(not math.isfinite(v) or v<0 for v in (min_thickness,min_gap)):
        raise ValueError('Limiti geometrici non negativi e finiti richiesti.')
    d,hub = design['outer_diameter_m'],design['hub_diameter_m']
    b = design['blade_count']
    if not all(math.isfinite(v) for v in (d,hub)) or not 0<hub<d or type(b) is not int or b<2:
        raise ValueError('Diametri o numero di pale non validi.')
    nodes,chords,angles = (design[k] for k in ('span_nodes','chord_m','pitch_deg'))
    if not len(nodes)==len(chords)==len(angles) or len(nodes)<2:
        raise ValueError('Nodi, corde e angoli non compatibili.')
    if any(not math.isfinite(v) for seq in (nodes,chords,angles) for v in seq):
        raise ValueError('Geometria non finita.')
    if nodes[0]!=0 or nodes[-1]!=1 or any(y<=x for x,y in zip(nodes,nodes[1:])) or min(chords)<=0:
        raise ValueError('Nodi crescenti fra 0 e 1 e corde positive richiesti.')
    contour, t = profile_data(design['profile'])
    margins, sections = [], []
    for i in range(count):
        s=i/(count-1)
        r=(hub+(d-hub)*s)/2
        c=interpolate(nodes,chords,s)
        beta=math.radians(interpolate(nodes,angles,s))
        # Identico sviluppo tangenziale usato da blade_sections, prima dell'avvolgimento.
        co,si=math.cos(beta),math.sin(beta)
        tangential=[c*((x-.25)*co-y*si) for x,y in contour]
        gap=2*math.pi*r/b-(max(tangential)-min(tangential))
        thick=c*t
        margins.extend(((gap-min_gap)/d,(thick-min_thickness)/d))
        sections.append({'r_m':r,'circumferential_envelope_gap_m':gap,'section_max_thickness_m':thick})
    return margins, {'stations':count,'min_circumferential_envelope_gap_m':min(s['circumferential_envelope_gap_m'] for s in sections),
                     'min_section_max_thickness_m':min(s['section_max_thickness_m'] for s in sections),
                     'required_gap_m':min_gap,'required_thickness_m':min_thickness,
                     'min_normalized_margin':min(margins),'structural_verification':'not_performed',
                     'method':'sampled_cylindrical_section_envelopes'}
