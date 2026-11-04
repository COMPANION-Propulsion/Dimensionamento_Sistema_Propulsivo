"""Esportazioni geometriche: nessuna prestazione aerodinamica presunta."""
import csv
import json
import math
from pathlib import Path
from .geometry import naca4


def export_geometry(directory, case, design, sections, catalog):
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "sections.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["radius_m", "chord_m", "pitch_deg", "profile"])
        for section in sections:
            writer.writerow([section[k] for k in ("radius_m", "chord_m", "pitch_deg")] + [design["profile"]])
    with (out / "blade_points.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["section", "point", "x_m", "y_m", "z_m"])
        for i, section in enumerate(sections):
            for j, point in enumerate(section["points"]):
                writer.writerow([i, j, *point])
    with (out / "blade_surface.obj").open("w", encoding="utf-8") as stream:
        stream.write("# Initial blade surface, metres. Open at root and tip; not a manufacturing solid.\n")
        for section in sections:
            for xyz in section["points"]:
                stream.write("v " + " ".join(f"{v:.10g}" for v in xyz) + "\n")
        n = len(sections[0]["points"])
        for i in range(len(sections)-1):
            for j in range(n):
                k = (j+1) % n
                a,b,c,d = i*n+j+1, i*n+k+1, (i+1)*n+k+1, (i+1)*n+j+1
                stream.write(f"f {a} {b} {c}\nf {a} {c} {d}\n")
    for profile in catalog:
        with (out / f"{profile}.dat").open("w", encoding="ascii") as stream:
            stream.write(f"{profile} analytic, finite trailing edge\n")
            for x,y in naca4(profile):
                stream.write(f"{x:.10f} {y:.10f}\n")
    report = {
        "status": "geometry_only_not_optimized", "design": design, "input_case": case,
        "thrust_N": None, "shaft_power_W": None, "energy_J": None,
        "polar_status": {p: catalog[p]["polar_status"] for p in case["rotor"]["airfoil_candidates"]},
        "geometry_convention": "Axis Z; pitch from rotation plane about quarter chord; sections wrapped on constant-radius cylinders.",
        "limitations": ["Initial geometry, not optimized to satisfy thrust.",
                        "No BEMT or optimization executed; aerodynamic polars missing.",
                        "OBJ is a blade skin, open at root and tip. No hub solid or blade-root attachment.",
                        "Duct contributions and mechanical integrity not evaluated."],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (out / "preview.svg").write_text(preview(design, sections, catalog), encoding="utf-8")
    from .stl_export import export_stl
    export_stl(out, design)


def preview(design, sections, catalog):
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650" viewBox="0 0 1000 650">',
                '<rect width="1000" height="650" fill="#f7f9fc"/>',
                '<g font-family="Arial,sans-serif" fill="#17233b">',
                '<text x="35" y="40" font-size="24">Ventola — geometria iniziale</text>',
                '<text x="35" y="68" font-size="15">Non ottimizzata — spinta e potenza ancora da calcolare</text>']
    scale = 350/design["outer_diameter_m"]
    def xy(x,y):
        return f"{245+scale*x:.2f},{305-scale*y:.2f}"
    for blade in range(design["blade_count"]):
        theta = blade*2*math.pi/design["blade_count"]
        co, si = math.cos(theta), math.sin(theta)
        for section in sections:
            pts = " ".join(xy(x*co-y*si, x*si+y*co) for x,y,z in section["points"])
            elements.append(f'<polygon points="{pts}" fill="#bfd9ed" fill-opacity="0.15" stroke="#16739b" stroke-width="0.7"/>')
    hub_px = design["hub_diameter_m"]/2*scale
    elements.append(f'<circle cx="245" cy="305" r="{hub_px:.2f}" fill="#d6dce6" stroke="#8793a6"/>')
    elements.append('<circle cx="245" cy="305" r="175" fill="none" stroke="#8793a6" stroke-dasharray="5 5"/>')
    elements.append(f'<text x="60" y="520" font-size="16">{design["blade_count"]} pale · {design["profile"]} · diametro {design["outer_diameter_m"]*1000:g} mm</text>')
    elements.append('<text x="550" y="120" font-size="19">Catalogo sezioni normalizzate</text>')
    for i,profile in enumerate(catalog):
        y0 = 180+i*100
        elements.append(f'<text x="550" y="{y0-20}" font-size="14">{profile}</text>')
        pts = " ".join(f"{550+350*x:.2f},{y0-350*y:.2f}" for x,y in naca4(profile))
        elements.append(f'<polygon points="{pts}" fill="#d2e7f4" stroke="#16739b"/>')
    elements.extend(['<text x="35" y="605" font-size="14">Vista assiale; mozzo schematico. Dati geometrici in metri nei file CSV e OBJ.</text>', '</g></svg>'])
    return "\n".join(elements)
