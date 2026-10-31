"""
Venturi design, flow check and shape optimisation for thrust.

    core/          inputs: fluids, Venturi sizing, propulsion case, actuator disk
    geometry/      wall profiles: analytic Venturi and morphed duct
    solver/        grid, projection, turbulence and time-marching flow solver
    optimization/  quick sizing, Newton solver, adjoint and shape optimisation
    analysis/      checks on a finished run and grid study
    export/        output files
    cli.py         command line and run pipelines
"""

from .core.config import VenturiConfig
from .core.fluids import FLUIDS, Fluid, list_fluids
from .core.propulsion import PropulsionCase
from .geometry import (MorphedGeometry, MorphLayout, VenturiGeometry,
                       create_venturi_geometry)
from .solver import FVResult, solve_fv, inlet_profile
from .solver.fvmesh import FVMesh, build_fvmesh, divergence
from .solver.projection import Projector
from .solver.turbulence import compute_nu_t, wall_y_plus, SUPPORTED as TURBULENCE_MODELS
from .analysis.validation import ValidationReport, validate, print_report, to_dict
from .export import export_all
from .optimization.sizing import run_optimization
from .optimization.shape_opt import DuctProblem, initial_design, optimise

__version__ = "3.1.0"

__all__ = [
    "VenturiConfig", "FLUIDS", "Fluid", "list_fluids", "PropulsionCase",
    "VenturiGeometry", "create_venturi_geometry", "MorphedGeometry", "MorphLayout",
    "FVMesh", "build_fvmesh", "divergence", "Projector",
    "FVResult", "solve_fv", "inlet_profile",
    "compute_nu_t", "wall_y_plus", "TURBULENCE_MODELS",
    "ValidationReport", "validate", "print_report", "to_dict",
    "export_all", "run_optimization",
    "DuctProblem", "initial_design", "optimise",
]
