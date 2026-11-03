import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "1_venturi"))
import numpy as np
from venturi_designer.core.config import VenturiConfig
from venturi_designer.core.propulsion import PropulsionCase
from venturi_designer.geometry import MorphedGeometry
from venturi_designer.optimization.shape_opt import initial_design
from venturi_designer.export.cad_duct import export_duct_cad, inner_pieces

c = PropulsionCase(fluid="air_20C", V0=0.0, p_amb=101325.0, D_ext_max=0.07, L_max=0.15,
                   L_disk=0.01, dp_disk=40.0)
lay, d = initial_design(c)
g0 = MorphedGeometry(lay, d)
cfg = VenturiConfig(D=2 * g0.R_inlet, beta=0.9, fluid="air_20C", p_throat_target=None,
                    wall_thickness=c.spessore_parete)
g = MorphedGeometry(lay, d, cfg)
# exact spline = geometry?
for p, (z0, z1) in zip([inner_pieces(g)[1], inner_pieces(g)[3]], [(0, g.z_a), (g.z_b, g.L_total)]):
    pts = p.f(np.linspace(0, 1, 501))
    print("spline err mm", np.abs(pts[:, 1] - g.radius(pts[:, 0] / 1e3) * 1e3).max())
t = time.time()
out = os.path.join(os.path.dirname(__file__), "cad")
res = export_duct_cad(g, c.L_disk, out)
print(round(time.time() - t, 1), res["checks"])
for f in res["files"]:
    print(os.path.basename(f), os.path.getsize(f) // 1024, "kB")
import cadquery as cq
for n in ("tubo", "fluido", "zona_disco"):
    s = cq.importers.importStep(os.path.join(out, n + ".step")).val()
    print(n, s.isValid(), round(s.Volume(), 1), "mm3", len(s.Faces()), "faces")
