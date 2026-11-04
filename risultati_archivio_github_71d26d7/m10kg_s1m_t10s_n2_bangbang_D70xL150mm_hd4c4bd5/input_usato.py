"""
Inputs of the whole project. The values below are PLACEHOLDERS: replace them.

    CASO      name of the results folder, risultati/<nome>/
    SPINTA    mission: distance, time, mass, nozzles -> thrust per nozzle (0_spinta)
    VENTURI   size limits and numerics of the duct -> dp of the fan (1_venturi)

The fan (2_ventola) still reads its own input file: the link comes later.
"""

CASO = {
    "nome": None,          # None = name built from the inputs + hash, or a string of your choice
    "sovrascrivi": False,  # True = reuse a named folder even if its inputs were different
}

SPINTA = {
    "distanza": 1.0,           # [m] distance to cover, from rest to rest
    "tempo": 10.0,             # [s] time available
    "massa": 10.0,             # [kg] mass of the cube
    "n_ugelli": 2,             # nozzles that push on one face: T_ugello = T / n_ugelli
    "profilo": "bang_bang",    # "bang_bang" (smallest thrust) or "trapezio"
    "frazione_crociera": 0.0,  # [-] "trapezio" only: share of the time at constant speed, 0..0.9
    "fattore_margine": 1.0,    # [-] multiplies the thrust needed
}

VENTURI = {
    # --- operating point ----------------------------------------------------
    "fluid": "air_20C",        # key of the fluid table (python run_venturi.py --list-fluids)
    "V0": 0.0,                 # flight speed [m/s], 0 = static
    "p_amb": 101325.0,         # ambient pressure [Pa]

    # --- thrust -------------------------------------------------------------
    "T_ugello": None,          # [N] None = from risultati/<caso>/1_spinta/spinta.json

    # --- size of the tube ---------------------------------------------------
    "D_ext_max": 0.07,         # [m] largest OUTER diameter of the tube
    "L_max": 0.15,             # [m] largest overall length, bell mouth included
    "gap_parete": 0.005,       # [m] from the outer edge to the inner duct
    "spessore_parete": 0.002,  # [m] wall of the CAD tube, at most gap_parete

    # --- fan (actuator disk): diameter and position are chosen by the optimiser
    "L_disk": 0.01,            # [m] axial length of the fan band
    "D_disk_min_ratio": 0.4,   # [-] smallest duct and fan diameter / largest inner diameter
    "P_max": None,             # [W] largest power, None = no limit

    # --- optimisation -------------------------------------------------------
    "turbulence_model": "baldwin_lomax",
    "n_up": 5,                 # free control points of the intake
    "n_down": 8,               # free control points of the diffuser
    "grid": "medium",          # "coarse", "medium" or "fine"
    "jobs": 3,                 # grids solved at the same time in the final check
    "max_iter": 40,            # optimiser iterations per grid
    "tol_dp": 0.01,            # [-] the dp loop stops when dp changes less than this
    "max_cicli_dp": 4,         # largest number of shape optimisations in the dp loop
}
