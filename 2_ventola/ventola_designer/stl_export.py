"""STL binari in mm delle pale, chiuse a radice e punta; mozzo non modellato."""
from collections import Counter
import json
import math
from pathlib import Path
import struct
import numpy as np
from .geometry import blade_sections


def closed_blade(design):
    sections = blade_sections(design)
    vertices = np.array([p for section in sections for p in section['points']])*1000
    n, ns = len(sections[0]['points']), len(sections)
    faces = []
    for i in range(ns-1):
        for j in range(n):
            k = (j+1)%n
            a,b,c,d = i*n+j,i*n+k,(i+1)*n+k,(i+1)*n+j
            faces.extend(((a,b,c),(a,c,d)))
    # NACA: TE superiore -> LE -> TE inferiore. Chiusura con strisce
    # fra nodi corrispondenti dei due lati, sulla superficie cilindrica.
    caps = []
    for j in range((n-1)//2):
        lower = n-1-j
        if j+1 == lower-1:
            caps.append((j,j+1,lower))
        else:
            caps.extend(((j,j+1,lower-1),(j,lower-1,lower)))
    faces.extend(tuple(reversed(f)) for f in caps)
    faces.extend(tuple(v+(ns-1)*n for v in f) for f in caps)
    triangles = vertices[np.asarray(faces)]
    volume = np.einsum('ij,ij->i',triangles[:,0],np.cross(triangles[:,1],triangles[:,2])).sum()/6
    if volume < 0:
        faces = [tuple(reversed(f)) for f in faces]
    edges = Counter((a,b) for f in faces for a,b in zip(f,f[1:]+f[:1]))
    if any(count != 1 or edges[(b,a)] != 1 for (a,b),count in edges.items()):
        raise ValueError('Mesh non chiusa o orientamento incoerente')
    if abs(volume) <= 1e-9:
        raise ValueError('Volume della pala nullo')
    return vertices[np.asarray(faces)], abs(float(volume))


def write_stl(path, triangles):
    # Validazione dopo quantizzazione float32, come nel file STL binario.
    triangles = np.asarray(triangles,dtype=np.float32)
    normals = np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    lengths = np.linalg.norm(normals,axis=1)
    if not np.isfinite(triangles).all() or np.any(lengths <= 1e-12):
        raise ValueError('Triangoli degeneri o coordinate non finite')
    normals /= lengths[:,None]
    with Path(path).open('wb') as stream:
        stream.write(b'Ventola: units mm, axis Z, closed blades, no hub'.ljust(80,b' '))
        stream.write(struct.pack('<I',len(triangles)))
        for normal,triangle in zip(normals,triangles):
            stream.write(struct.pack('<12fH',*normal,*triangle.ravel(),0))


def export_stl(directory, design):
    out = Path(directory)
    out.mkdir(parents=True,exist_ok=True)
    blade, volume = closed_blade(design)
    all_blades = []
    for index in range(design['blade_count']):
        angle = 2*math.pi*index/design['blade_count']
        c,s = math.cos(angle),math.sin(angle)
        rotation = np.array([[c,-s,0],[s,c,0],[0,0,1]])
        all_blades.append(blade @ rotation.T)
    assembly = np.concatenate(all_blades)
    write_stl(out/'pala_mm.stl',blade)
    write_stl(out/'ventola_pale_mm.stl',assembly)
    info = dict(units='mm',axis='Z',blade_count=design['blade_count'],
                triangles_per_blade=len(blade),closed_shells=design['blade_count'],
                blade_volume_mm3=volume,diameter_mm=design['outer_diameter_m']*1000,
                bounds_mm=[assembly.min(axis=(0,1)).tolist(),assembly.max(axis=(0,1)).tolist()],
                limitations='Pale separate chiuse a radice e punta. Mozzo e attacchi non modellati. Mesh triangolata, non CAD parametrico. Nessun campo Cp.')
    (out/'STL_info.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    return info
