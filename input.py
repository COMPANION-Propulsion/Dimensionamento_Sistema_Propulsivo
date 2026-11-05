"""
Inputs of the whole project. The values below are PLACEHOLDERS: replace them.

    CASO      name of the results folder, risultati/<nome>/
    SPINTA    mission: distance, time, mass, nozzles -> thrust per nozzle (0_spinta)
    VENTURI   size limits and numerics of the duct -> dp of the fan (1_venturi)
    VENTOLA   search bounds of the fan, sized for the dp of the venturi (2_ventola)

run_sistema.py writes the fan input from VENTOLA in risultati/<caso>/input_ventola.json.
"""

CASO = {
    "nome": "TEST_2",          # None = name built from the inputs + hash, or a string of your choice
    "sovrascrivi": True,  # True = reuse a named folder even if its inputs were different
}

SPINTA = {
    "distanza": 0.25,           # [m] distance to cover, from rest to rest
    "tempo": 5,             # [s] time available
    "massa": 4.5,             # [kg] mass of the cube
    "n_ugelli": 2,             # nozzles that push on one face: T_ugello = T / n_ugelli
    "profilo": "bang_bang",    # "bang_bang" (smallest thrust) or "trapezio"
    "frazione_crociera": 0.0,  # [-] "trapezio" only: share of the time at constant speed, 0..0.9
    "fattore_margine": 1.5,    # [-] multiplies the thrust needed
}

VENTURI = {
    # --- operating point ----------------------------------------------------
    "fluid": "air_20C",        # key of the fluid table (python run_venturi.py --list-fluids)
    "V0": 0.0,                 # flight speed [m/s], 0 = static
    "p_amb": 101325.0,         # ambient pressure [Pa]

    # --- thrust -------------------------------------------------------------
    "T_ugello": None,          # [N] None = from risultati/<caso>/1_spinta/spinta.json

    # --- size of the tube ---------------------------------------------------
    "D_ext_max": 0.05,         # [m] largest OUTER diameter of the tube
    "L_max": 0.20,             # [m] largest overall length, bell mouth included
    "L_min": 0.08,             # [m] smallest overall length (motor, supports), None = free;
                               #     the optimiser stays close to it: shorter = less friction
    "gap_parete": 0.003,       # [m] from the outer edge to the inner duct (wall + margin)
    "spessore_parete": 0.002,  # [m] wall of the CAD tube, at most gap_parete (thick walls
                               #     shrink the inlet through the bell mouth)

    # --- fan (actuator disk): diameter and position are chosen by the optimiser
    "L_disk": 0.02,            # [m] axial length of the fan band; straight section = 2 L_disk
                               #     holds rotor + gap + stator,
                               #     must be < L_max / 4
    "D_disk_min_ratio": 0.4,   # [-] smallest duct and fan diameter / largest inner diameter
    "P_max": None,             # [W] largest power, None = no limit

    # --- optimisation -------------------------------------------------------
    "turbulence_model": "baldwin_lomax",
    "n_up": 5,                 # free control points of the intake (5-8: more only adds time)
    "n_down": 8,               # free control points of the diffuser (8-10)
    "grid": "medium",          # "coarse", "medium" or "fine"
    "jobs": 3,                 # grids solved at the same time in the final check (3 grids)
    "max_iter": 40,            # optimiser iterations per grid
    "tol_dp": 0.01,            # [-] the dp loop stops when dp changes less than this
    "max_cicli_dp": 4,         # largest number of shape optimisations in the dp loop (2 usually)
}

VENTOLA = {
    # Diameter, dp, flow rate and density come from the venturi of the same case.
    "temperatura_K": 293.15,                 # air temperature, consistent with VENTURI["fluid"]
    "mozzo_su_D": [0.15, 0.25],              # hub diameter / fan diameter, min and max
    "statore": {                             # fixed vanes after the rotor (straighten the flow)
        "presente": True,                    #   False = rotor only, the swirl leaves with the jet
        "pale": None,                        #   vanes, None = first number >= 7 coprime with rotor
        "solidita": 1.0,                     #   chord x vanes / circumference (0.6-1.5)
        "profilo": "NACA4412",               #   section of the vanes
        "gioco_assiale_m": 0.002,            #   axial gap rotor -> stator [m]
    },
    "giri_min_max_rpm": [5000.0, 30000.0],   # shaft speed bounds [rpm]
    "calettamento_min_max_deg": [0.0, 75.0], # blade pitch bounds [deg]; small hubs need a
                                             #   steep root (flow angle up to 60-70 deg)
    "pale_candidate": [2, 3, 4, 5, 6, 7, 8],
    "profili_candidati": ["NACA0012", "NACA2412", "NACA4412", "NACA4415"],
    "durata_s": 1.0,                         # duration of the operating point (scales the energy)
    "gioco_punta_m": 0.0005,                 # tip clearance of the CAD blades to the duct [m]
    "potenza_max_W": None,                   # end of the power curve, None = 2 x design power
    "jobs": None,                            # pairs profile/blades in parallel, None = all cores
    "sizing": {},                            # overrides of the fan sizing settings (see 2_ventola)
}
