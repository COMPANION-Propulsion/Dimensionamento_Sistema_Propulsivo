"""Wall profiles: the analytic Venturi and the morphed duct."""
from .venturi import Segment, VenturiGeometry, arc_segment, create_venturi_geometry
from .morph import MorphedGeometry, MorphLayout, fit_design
