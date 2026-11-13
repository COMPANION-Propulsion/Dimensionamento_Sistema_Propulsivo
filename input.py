"""
Inputs of the whole project. The values below are PLACEHOLDERS: replace them.

    CASO      name of the results folder, risultati/<nome>/
    SPINTA    mission: distance, time, mass, nozzles -> thrust per nozzle (0_spinta)
    VENTURI   size limits and numerics of the duct -> dp of the fan (1_venturi)
    VENTOLA   search bounds of the fan, sized for the dp of the venturi (2_ventola)
    SISTEMA   how the chain is run: stator yes/no comparison, band iterations (run_sistema.py)

run_sistema.py writes the fan input from VENTOLA in risultati/<caso>/input_ventola.json.

Series of cases. Any value of SPINTA, VENTURI, VENTOLA, SISTEMA (also inside nested
dictionaries, e.g. VENTOLA["statore"]["presente"]) can be a string with several values
separated by ";":

    "massa": "4; 6; 8"                     numbers, None, True, lists: each part is read with
    "D_ext_max": "None; 0.07"              ast.literal_eval; what is not a literal stays text
    "profilo": "bang_bang; trapezio"
    "statore": {"presente": "True; False"}

Every combination is a complete chain in risultati/<nome>/<etichetta>/ (<etichetta> = e.g.
massa_4 or massa_4__D_ext_max_0.07). SISTEMA["combinazioni"] = "tutte" runs all the
combinations of the keys with several values, "accoppiate" pairs the i-th value of each key
(the lists must have the same length). A string without ";" is a plain value.
python run_sistema.py --elenca prints the cases without running anything.
"""

CASO = {
    "nome": "Run_20261113_fine_4kg-Ottimizzato",         # None = name built from the inputs + hash, or a string of your choice
    "sovrascrivi": True,  # True = reuse a named folder even if its inputs were different
}

SPINTA = {
    "distanza": 0.2,         # [m] distance to cover, from rest to rest
    "tempo": 5,             # [s] time available
    "massa": 4,             # [kg] mass of the cube
    "n_ugelli": 2,             # nozzles that push on one face: T_ugello = T / n_ugelli
    "profilo": "bang_bang",    # "bang_bang" (smallest thrust) or "trapezio"
    "frazione_crociera": 0.0,  # [-] "trapezio" only: share of the time at constant speed, 0..0.9
    "fattore_margine": 2,    # [-] multiplies the thrust needed (margin chosen by the team)
    "disturbo_residuo_g": 0.02,  # [g] residual acceleration of the parabolic flight the thrust must overcome, 0 = free fall
}

VENTURI = {
    # --- operating point ----------------------------------------------------
    "fluid": "air_20C",        # key of the fluid table (python run_venturi.py --list-fluids)
    "V0": 0.0,                 # flight speed [m/s], 0 = static
    "p_amb": 101325.0,         # ambient pressure the duct and the fan are sized at [Pa]
    "p_cabina": 82500.0,       # [Pa] cabin pressure during the parabolas (rho 0.98 kg/m3 at 20 C): only for the
                               #     ground / flight comparison in the outputs, None = no comparison

    # --- thrust -------------------------------------------------------------
    "T_ugello": None,          # [N] None = from risultati/<caso>/1_spinta/spinta.json

    # --- size of the tube ---------------------------------------------------
    "D_ext_max": 0.07,         # [m] largest OUTER diameter of the tube
    "L_max": 0.160,             # [m] largest overall length, bell mouth included
    "L_min": 0.07,             # [m] smallest overall length (motor, supports), None = free;
                               #     the optimiser stays close to it: shorter = less friction
    "gap_parete": 0.003,       # [m] from the outer edge to the inner duct (wall + margin)
    "spessore_parete": 0.003,  # [m] wall of the CAD tube, at most gap_parete (thick walls
                               #     shrink the inlet through the bell mouth)
    "raggio_bocca_su_D": 0.2,  # [-] bell-mouth radius / inlet diameter (0.05-0.5): smaller leaves
                               #     more diameter to the fan, below ~0.15 the inlet loss grows

    # --- fan (actuator disk): diameter and position are chosen by the optimiser
    "semiangolo_max_deg": 5.0,  # [deg] steepest diffuser wall; keep it at 5 or below: above ~4-5 deg it may separate
    "L_disk": 0.032,           # [m] axial length of the fan band; straight section = 2 L_disk
                               #     holds rotor + gap + stator,
                               #     must be < L_max / 4; run_sistema.py takes it as the starting
                               #     value and adjusts it to the real fan (SISTEMA, VENTOLA margins)
    "D_disk_min_ratio": 0.4,   # [-] smallest duct and fan diameter / largest inner diameter
    "P_max": None,             # [W] largest power, None = no limit

    # --- fan model in the duct ----------------------------------------------
    "curva_ventola": None,     # None = fixed dp, set for the wanted thrust. Or a fan curve:
                               #   {"Q_m3_s": [...], "dp_Pa": [...], "fittizia": False, "fonte": "..."}
                               #   then the thrust is a RESULT (operating point on the curve).
                               # EXAMPLE, FICTITIOUS, do not use for the design:
                               #   {"Q_m3_s": [0.0, 0.005, 0.010, 0.015, 0.020],
                               #    "dp_Pa": [80.0, 75.0, 60.0, 35.0, 0.0], "fittizia": True}
    "mozzo_su_D_disco": 0.0,   # no dp inside this share of the disk diameter (0 = off)
    "perdita_swirl": 0.0,      # share of dp lost as swirl without stator (0 = off)

    # --- optimisation -------------------------------------------------------
    "ottimizzatore": "griglia+forma",  # "griglia": scan of exit diameter x diffuser length (robust);
                                 #   "griglia+forma": scan, then adjoint shape optimisation from the
                                 #     best scan case (free length, fan diameter/position, intake, diffuser);
                                 #   "slsqp": adjoint shape optimisation from the default shape (can wander)
    "alternative_L_tubo": 6,   # only with "griglia+forma": optimum re-solved at fixed tube lengths.
                               #   int = n lengths equally spaced between L_min and L_max,
                               #   list [m] = explicit lengths, None or 0 = no alternatives
    "alternative_max_cicli_dp": 3,  # dp loops per alternative (fewer than max_cicli_dp: saves time)
    "D_ventola": None,         # [m] fixed fan diameter for the scan, None = largest the inlet allows
    "scansione_D_uscita": 5,   # exit diameters scanned
    "scansione_L_diffusore": 4,# diffuser lengths scanned
    "scansione_uscita": 7,     # points of the converging/diverging exit scan on the optimum, 0 = no scan
    "turbulence_model": "baldwin_lomax",
    "n_up": 8,                 # free control points of the intake (5-8: more only adds time)
    "n_down": 10,               # free control points of the diffuser (8-10)
    "grid": "fine",        # "coarse", "medium" or "fine"
    "jobs": 3,                 # grids solved at the same time in the final check (3 grids)
    "max_iter": 60,            # optimiser iterations per grid
    "tol_dp": 0.01,            # [-] the dp loop stops when dp changes less than this
    "max_cicli_dp": 4,         # largest number of shape optimisations in the dp loop (2 usually)
}

VENTOLA = {
    # Diameter, dp, flow rate and density come from the venturi of the same case.
    "temperatura_K": 293.15,                 # air temperature, consistent with VENTURI["fluid"]
    "mozzo_su_D": [0.38, 0.45],              # hub diameter / fan diameter, min and max: the hub holds
                                             #   the 1404 motor (18 mm + 2 x 2 mm wall = 22 mm on a ~58 mm fan)
    "statore": {                             # fixed vanes after the rotor (straighten the flow)
        "presente": True,                    #   False = rotor only, the swirl leaves with the jet
        "pale": None,                        #   vanes, None = first number >= 7 coprime with rotor
        "solidita": 0.7,                     #   chord x vanes / circumference (0.6-1.5); low Re:
                                             #   less vane area = less friction
        "profilo": "NACA4412",               #   section of the vanes
        "gioco_assiale_m": 0.002,            #   axial gap rotor -> stator [m]
    },
    "giri_min_max_rpm": [5000.0, 40000.0],   # shaft speed bounds [rpm]; faster = higher Re
                                             #   on the blades = less separation
    "calettamento_min_max_deg": [0.0, 75.0], # blade pitch bounds [deg]; small hubs need a
                                             #   steep root (flow angle up to 60-70 deg)
    "corda_su_D_min_max": [0.04, 0.40],      # blade chord / fan diameter bounds (it was 0.22 at most,
                                             #   and the 3-blade design sat on it); the solidity limit
                                             #   (0.8) and the gap between blades still cap the root
    "pale_candidate": [3, 4, 5, 6, 7],
    "nodi_pala": 3,                          # nodes of chord and pitch along the blade:
                                             #   2 = smooth S-shaped from root to tip (not linear), 3-4 = more freedom
    "profili_candidati": ["NACA0012", "NACA2412", "NACA4412", "NACA4415"],
    "durata_s": 1.0,                         # duration of the operating point (scales the energy)
    "gioco_punta_m": 0.0005,                 # tip clearance of the CAD blades to the duct [m]
    "potenza_max_W": None,                   # end of the power curve, None = 2 x design power
    "margine_fascia_m": 0.001,               # clearance added to the real fan length to set VENTURI["L_disk"] [m]
    "fascia_min_m": None,                    # smallest L_disk [m] (e.g. motor support 1404), None = none
    "jobs": None,                            # pairs profile/blades in parallel, None = auto (at most 4,
                                             #   fewer if memory is low; each process reloads scipy)
    "sizing": {"minimum_rotor_stall_margin_deg": None,   # None = diagnostica, oppure gradi richiesti
               "minimum_section_thickness_m": 0.001},    # thinnest blade section [m]: 1 mm keeps the root
                                                         #   printable (chord >= 8.3 mm with a 12 % profile)
}

SISTEMA = {
    "confronto_statore": True,   # True = chain run twice (Statore/, NoStatore/) + 5_confronto_statore/
    "iterazioni_fascia": 3,      # most venturi+fan passes to fit the band L_disk to the real fan
    "combinazioni": "tutte",     # series of cases ("4; 6" values): "tutte" = every combination,
                                 #   "accoppiate" = i-th value of each key with the i-th of the others
    "densita_kg_m3": 1240.0,     # [kg/m3] material of the tube and the blades (PLA), for the mass estimate
    "riempimento": 1.0,          # [-] solid share of the print (thin walls = 1.0)
}
