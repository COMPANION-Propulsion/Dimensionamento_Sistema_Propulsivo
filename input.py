"""Inputs of the project. The values below are placeholders: replace them."""

VENTURI = {
    # --- operating point ----------------------------------------------------
    "fluid": "air_20C",        # key of the fluid table (python run_venturi.py --list-fluids)
    "V0": 0.0,                 # flight speed [m/s], 0 = static
    "p_amb": 101325.0,         # ambient pressure [Pa]

    # --- actuator disk, from the fan sizing ---------------------------------
    "dp_disk": 1000.0,         # total-pressure rise [Pa]
    "D_disk": 0.10,            # disk diameter [m]
    "L_disk": 0.02,            # axial length of the disk band [m]
    "z_disk": None,            # disk centre / total length, None = chosen by the optimiser

    # --- limits of the duct -------------------------------------------------
    "D_max": 0.16,             # largest diameter [m]
    "L_max": 0.60,             # largest total length [m]
    "P_max": None,             # largest power [W], None = no limit

    # --- optimisation -------------------------------------------------------
    "turbulence_model": "baldwin_lomax",
    "n_up": 5,                 # free control points of the intake
    "n_down": 8,               # free control points of the diffuser
    "grid": "medium",          # "coarse", "medium" or "fine", see GRID_LEVELS
    "jobs": 3,                 # grids solved at the same time in the final check
    "max_iter": 40,            # optimiser iterations per grid
}
