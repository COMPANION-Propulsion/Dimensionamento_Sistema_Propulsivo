"""Esportazione VTK XML per ParaView dei risultati BEMT e della geometria.

I campi aerodinamici sono campionati sugli anelli BEMT: non sono un volume CFD.
"""
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

from .geometry import blade_sections
from .polars import PolarGrid, PolarDomainError
from .settings import sizing_settings


def _numbers(values):
    return " ".join(f"{float(value):.12g}" for value in values)


def _write_polydata(path, points, polys=(), lines=(), point_data=None, cell_data=None):
    """Scrive un VTP ASCII portabile, senza dipendenze da VTK."""
    point_data = point_data or {}
    cell_data = cell_data or {}
    connectivity, offsets = [], []
    offset = 0
    for cell in list(polys) + list(lines):
        connectivity.extend(cell)
        offset += len(cell)
        offsets.append(offset)
    polygons = list(polys)
    polylines = list(lines)
    def arrays(values):
        return "\n".join(
            f'<DataArray type="Float64" Name="{escape(name)}" format="ascii">{_numbers(data)}</DataArray>'
            for name, data in values.items())
    polygon_connectivity = []
    polygon_offsets = []
    offset = 0
    for cell in polygons:
        polygon_connectivity.extend(cell)
        offset += len(cell)
        polygon_offsets.append(offset)
    line_connectivity = []
    line_offsets = []
    offset = 0
    for cell in polylines:
        line_connectivity.extend(cell)
        offset += len(cell)
        line_offsets.append(offset)
    content = f'''<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
  <PolyData><Piece NumberOfPoints="{len(points)}" NumberOfVerts="0" NumberOfLines="{len(polylines)}" NumberOfStrips="0" NumberOfPolys="{len(polygons)}">
    <PointData>{arrays(point_data)}</PointData>
    <CellData>{arrays(cell_data)}</CellData>
    <Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">{_numbers(v for point in points for v in point)}</DataArray></Points>
    <Lines><DataArray type="Int64" Name="connectivity" format="ascii">{' '.join(map(str, line_connectivity))}</DataArray><DataArray type="Int64" Name="offsets" format="ascii">{' '.join(map(str, line_offsets))}</DataArray></Lines>
    <Polys><DataArray type="Int64" Name="connectivity" format="ascii">{' '.join(map(str, polygon_connectivity))}</DataArray><DataArray type="Int64" Name="offsets" format="ascii">{' '.join(map(str, polygon_offsets))}</DataArray></Polys>
  </Piece></PolyData>
</VTKFile>'''
    path.write_text(content, encoding="utf-8")


def export_geometry_vtp(directory, design):
    """Esporta tutte le pale come superficie triangolata, in metri."""
    sections = blade_sections(design)
    section_points = len(sections[0]["points"])
    points, faces, blade_ids = [], [], []
    for blade in range(design["blade_count"]):
        theta = 2 * math.pi * blade / design["blade_count"]
        cosine, sine = math.cos(theta), math.sin(theta)
        first = len(points)
        for section in sections:
            for x, y, z in section["points"]:
                points.append((x * cosine - y * sine, x * sine + y * cosine, z))
        for radial in range(len(sections) - 1):
            for chordwise in range(section_points):
                following = (chordwise + 1) % section_points
                a = first + radial * section_points + chordwise
                b = first + radial * section_points + following
                c = first + (radial + 1) * section_points + following
                d = first + (radial + 1) * section_points + chordwise
                faces.extend(((a, b, c), (a, c, d)))
                blade_ids.extend((blade, blade))
    filename = "fan_geometry.vtp"
    _write_polydata(Path(directory) / filename, points, polys=faces,
                    cell_data={"blade_id": blade_ids})
    return filename


def _safe_name(value):
    return "".join(character if character.isalnum() else "_" for character in str(value))


def export_paraview_results(directory, case, runs, best=None):
    """Esporta tutti i candidati calcolabili e le loro condizioni operative.

    Ogni VTP di risultato contiene una linea radiale e grandezze locali BEMT.
    I candidati esclusi restano esportati, con ``accepted`` uguale a zero.
    """
    out = Path(directory) / "paraview"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "VTK XML PolyData", "length_unit": "m",
                "field_description": "Campi locali sugli anelli BEMT; non volume CFD.",
                "geometry": None, "datasets": [], "skipped_runs": []}
    if best:
        manifest["geometry"] = export_geometry_vtp(out, best["design"])
    collections = []
    for run_index, run in enumerate(runs):
        design = run.get("design")
        if not design:
            manifest["skipped_runs"].append({"profile": run["profile"], "blades": run["blades"],
                                             "reason": "nessuna geometria calcolabile"})
            continue
        try:
            from .optimizer import evaluate  # evita un'importazione circolare al caricamento
            polar = PolarGrid.load(Path(__file__).parent / "airfoils" / "polars_neuralfoil" /
                                   f'{run["profile"]}.json')
            _, _, cases = evaluate(case, design, polar, stations=sizing_settings(case)['stations_final'])
        except (OSError, ValueError, PolarDomainError) as exc:
            manifest["skipped_runs"].append({"profile": run["profile"], "blades": run["blades"],
                                             "reason": str(exc)})
            continue
        for point_index, result in enumerate(cases):
            local = result["local"]
            filename = f'run_{run_index:03d}_{_safe_name(run["profile"])}_{run["blades"]}pale_point_{point_index:02d}.vtp'
            fields = {key: [row[key] for row in local] for key in local[0] if key != "r_m"}
            _write_polydata(out / filename, [(row["r_m"], 0.0, 0.0) for row in local],
                            lines=[tuple(range(len(local)))], point_data=fields,
                            cell_data={"accepted": [1.0 if run.get("accepted") else 0.0],
                                       "blade_count": [float(run["blades"])],
                                       "thrust_rotor_N": [result["thrust_rotor_N"]],
                                       "shaft_power_W": [result["shaft_power_W"]],
                                       "rpm": [result["rpm"]],
                                       **{k:[result[k]] for k in ('volume_flow_m3_s','mass_flow_kg_s',
                                           'total_pressure_rise_Pa','static_pressure_rise_Pa',
                                           'axial_blade_velocity_m_s','fluid_power_W','swirl_power_W',
                                           'total_pressure_efficiency') if k in result}})
            entry = {"file": filename, "run_index": run_index, "profile": run["profile"],
                     "blade_count": run["blades"], "accepted": bool(run.get("accepted")),
                     "status": run.get("status"), "operating_point": result["operating_point"],
                     "thrust_rotor_N": result["thrust_rotor_N"], "shaft_power_W": result["shaft_power_W"]}
            manifest["datasets"].append(entry)
            collections.append((point_index, run_index, filename))
    pvd = ['<?xml version="1.0"?>', '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">', '<Collection>']
    for point_index, run_index, filename in collections:
        pvd.append(f'<DataSet timestep="{point_index}" group="run_{run_index:03d}" part="0" file="{filename}"/>')
    pvd.extend(['</Collection>', '</VTKFile>'])
    (out / "results.pvd").write_text("\n".join(pvd) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return manifest
