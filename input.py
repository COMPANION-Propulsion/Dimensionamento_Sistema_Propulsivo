
CASO = {
    # Results folder risultati/<nome>/. With a series (see above) it is the series folder and
    # every case is risultati/<nome>/<etichetta>/.
    "nome": "Run_20261113_fine_Ottimizzato",         # None = name built from the inputs + hash, or a string of your choice
    # A folder with a name whose stored inputs differ from these is refused unless this is True.
    "sovrascrivi": True,  # True = reuse a named folder even if its inputs were different
}

SPINTA = {
    # Used by 0_spinta only: the result is the thrust per nozzle, passed to the venturi
    # (unless VENTURI["T_ugello"] is a number).
    "distanza": 0.2,         # [m] distance to cover, from rest to rest
    "tempo": 5,             # [s] time available
    "massa": "4; 6",             # [kg] mass of the cube
    "n_ugelli": 2,             # nozzles that push on one face: T_ugello = T / n_ugelli
    "profilo": "bang_bang",    # "bang_bang" (accelerate then brake: smallest thrust) or "trapezio"
                               #   (with a cruise at constant speed: more thrust, lower peak speed)
    "frazione_crociera": 0.0,  # [-] "trapezio" only: share of the time at constant speed, 0..0.9
    "fattore_margine": 2,    # [-] multiplies the thrust needed (margin chosen by the team), 1 = none
    "disturbo_residuo_g": 0.02,  # [g] residual acceleration of the parabolic flight the thrust must overcome, 0 = free fall
}

VENTURI = {
    # Step 1_venturi. The tube is axisymmetric; the fan is an actuator disk (uniform dp) that the
    # optimiser sizes and places. The result for the fan step is dp, flow rate and diameter.

    # --- operating point ----------------------------------------------------
    "fluid": "air_20C",        # key of the fluid table (python run_venturi.py --list-fluids)
    "V0": 0.0,                 # flight speed [m/s], 0 = static
    "p_amb": 101325.0,         # ambient pressure the duct and the fan are sized at [Pa]
    "p_cabina": 82500.0,       # [Pa] cabin pressure during the parabolas (rho 0.98 kg/m3 at 20 C): only for the
                               #     ground / flight comparison in 4_sistema (run_sistema.py), None = no comparison

    # --- thrust -------------------------------------------------------------
    "T_ugello": None,          # [N] thrust per nozzle the duct must give; None = from
                               #     risultati/<caso>/1_spinta/spinta.json (the normal use);
                               #     a number overrides the mission and is used as it is

    # --- size of the tube ---------------------------------------------------
    "D_ext_max": 0.07,         # [m] largest OUTER diameter of the tube
    "L_max": 0.160,             # [m] largest overall length, bell mouth included
    "L_min": 0.07,             # [m] smallest overall length (motor, supports), None = free.
                               #     "griglia+forma": the length is optimised in [L_min, L_max] and the
                               #     alternatives cover this range; "griglia": the scan fills the
                               #     tube down to L_min; must be < L_max
    "gap_parete": 0.003,       # [m] from the outer edge to the inner duct (wall + margin)
    "spessore_parete": 0.003,  # [m] wall of the CAD tube, at most gap_parete (thick walls
                               #     shrink the inlet through the bell mouth)
    "raggio_bocca_su_D": 0.2,  # [-] bell-mouth radius / inlet diameter (0.05-0.5): smaller leaves
                               #     more diameter to the fan, below ~0.15 the inlet loss grows

    # --- fan band and fan diameter -------------------------------------------
    "semiangolo_max_deg": 5.0,  # [deg] steepest diffuser wall (half angle): the scan skips steeper
                                #     diffusers and the optimiser is held to it; keep it at 5 or below:
                                #     above ~4-5 deg the flow may separate (warning printed above 5)
    "L_disk": 0.032,           # [m] axial length of the fan band; straight section = 2 L_disk
                               #     holds rotor + gap + stator; needs 4 L_disk < L_max.
                               #     run_sistema.py takes it as the STARTING value only: after each
                               #     venturi + fan pass it is reset to the real length of rotor and
                               #     stator from the fan CAD + VENTOLA["margine_fascia_m"] (at least
                               #     VENTOLA["fascia_min_m"], at most L_max/4), at most
                               #     SISTEMA["iterazioni_fascia"] passes (history in fascia.json).
                               #     Run alone (run_venturi.py) it is used as it is
    "D_disk_min_ratio": 0.4,   # [-] smallest duct and fan diameter / largest inner diameter (0-1)
    "D_ventola": None,         # [m] fixed fan diameter for the scan, None = largest the inlet allows
                               #     ("griglia" and the scan of "griglia+forma")
    "P_max": None,             # [W] largest power, None = no limit

    # --- fan model in the duct ----------------------------------------------
    "curva_ventola": None,     # None = fixed dp, set for the wanted thrust (the normal use). Or a fan curve:
                               #   {"Q_m3_s": [...], "dp_Pa": [...], "fittizia": False, "fonte": "..."}
                               #   then the thrust is a RESULT (operating point on the curve); only
                               #   with "ottimizzatore": "griglia".
                               # EXAMPLE, FICTITIOUS, do not use for the design:
                               #   {"Q_m3_s": [0.0, 0.005, 0.010, 0.015, 0.020],
                               #    "dp_Pa": [80.0, 75.0, 60.0, 35.0, 0.0], "fittizia": True}
    "mozzo_su_D_disco": 0.0,   # [-] no dp inside this share of the disk radius (hub): pessimistic,
                               #     the hub body is not in the flow; 0 = off
    "perdita_swirl": 0.0,      # [-] share of dp lost as swirl in the duct (0-1), 0 = off. Keep 0 in the
                               #     chain: the dp is axial and the swirl is computed in the fan step
                               #     (rotor alone, or removed by the stator, see 5_confronto_statore).
                               #     Use it only for a duct-only run (run_venturi.py) of a fan without stator

    # --- optimisation -------------------------------------------------------
    "ottimizzatore": "griglia+forma",  # "griglia": scan of exit diameter x diffuser length, every case solved,
                                 #   separated diffusers (negative wall shear) discarded; robust and fast;
                                 #   "griglia+forma": scan, then adjoint shape optimisation (SLSQP) from the
                                 #     best scan case (free length in [L_min, L_max], fan diameter and
                                 #     position, intake, diffuser); the most complete, and the only one
                                 #     with alternatives; no fan curve;
                                 #   "slsqp": adjoint shape optimisation from the default shape, no scan
                                 #     (can wander); no fan curve
    "alternative_L_tubo": 6,   # only with "griglia+forma": optimum re-solved at fixed tube lengths.
                               #   int = n lengths equally spaced between L_min and L_max
                               #   (0.6 L_max if L_min is None; 1 = L_max only),
                               #   list [m] = explicit lengths, None or 0 = no alternatives.
                               #   Skipped in the intermediate band passes of run_sistema.py (last pass only)
    "alternative_max_cicli_dp": 3,  # dp loops per alternative (fewer than max_cicli_dp: saves time)
    "scansione_D_uscita": 5,   # exit diameters of the initial scan ("griglia" and "griglia+forma")
    "scansione_L_diffusore": 4,# diffuser lengths of the initial scan; the scan has n_D x n_L cases,
                               #   each solved on the finest "optimise" grid of "grid"
    "scansione_uscita": 7,     # (not read by the code at the moment: the exit scan of the optimum is not
                               #   called in cli.py) points of the converging/diverging exit scan, 0 = no scan
    "turbulence_model": "baldwin_lomax",   # turbulence model of the duct flow
    "n_up": 8,                 # free control points of the intake (5-8: more only adds time)
    "n_down": 10,               # free control points of the diffuser (8-10)
    "grid": "fine",        # "coarse" (optimise on 64x26, check up to 128x51), "medium" or "fine"
                           #   (optimise up to 128x51, check up to 256x102): finer = slower, the longest
                           #   step of the chain; the check gives the error on dp
    "jobs": 3,                 # grids solved at the same time in the final check (3 grids)
    "max_iter": 60,            # optimiser iterations per grid
    "tol_dp": 0.01,            # [-] the dp loop stops when dp changes less than this
    "max_cicli_dp": 4,         # largest number of shape optimisations in the dp loop (2 usually)

    # --- advanced (defaults of the code: leave them unless you know why) ----
    "L_target": None,          # [m] hold the tube length (+/- 0.5 mm), None = free; the alternatives
                               #     set it themselves
    "Nz": 64,                  # axial cells of the base grid (the "grid" level sets the real ones)
    "Nr": 26,                  # radial cells of the base grid (as above)
    "wall_clustering": 3.5,    # [-] cell clustering at the wall, keeps y+ below 5 on every grid level
    "throat_refine": 3.0,      # [-] extra axial refinement at the throat, "auto" or a number >= 1
}

VENTOLA = {
    # Step 2_ventola. Diameter, dp, flow rate and density come from the venturi of the same case.
    # Unknown keys here or in "statore" are refused. VENTOLA is not in the case hash.
    "temperatura_K": 293.15,                 # air temperature [K], consistent with VENTURI["fluid"]
    "mozzo_su_D": [0.38, 0.45],              # hub diameter / fan diameter, min and max (0 < min < max < 1): the hub holds
                                             #   the 1404 motor (18 mm + 2 x 2 mm wall = 22 mm on a ~58 mm fan)
    "statore": {                             # fixed vanes after the rotor (straighten the flow)
        "presente": True,                    #   False = rotor only, the swirl leaves with the jet.
                                             #   With SISTEMA["confronto_statore"] = True this flag is
                                             #   overridden per variant (Statore: True, NoStatore: False)
        "pale": None,                        #   vanes, None = first number >= 7 coprime with rotor
        "solidita": 0.7,                     #   chord x vanes / circumference (0.6-1.5; accepted 0.2-3); low Re:
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
    "pale_candidate": [3, 4, 5, 6, 7],       # blade counts tried: each one (with each profile) is a run
                                             #   of the optimiser; fewer = faster
    "nodi_pala": 3,                          # nodes of chord and pitch along the blade:
                                             #   2 = smooth S-shaped from root to tip (not linear), 3-4 = more freedom
    "profili_candidati": ["NACA0012", "NACA2412", "NACA4412", "NACA4415"],   # blade sections tried
    "durata_s": 1.0,                         # duration of the operating point (scales the energy)
    "gioco_punta_m": 0.0005,                 # tip clearance of the CAD blades to the duct [m]
    "potenza_max_W": None,                   # end of the power curve, None = 2 x design power
    "margine_fascia_m": 0.001,               # clearance added to the real fan length to set VENTURI["L_disk"] [m]
                                             #   (band loop of run_sistema.py)
    "fascia_min_m": None,                    # smallest L_disk [m] (e.g. motor support 1404), None = none
    "jobs": None,                            # pairs profile/blades in parallel, None = auto (at most 4,
                                             #   fewer if memory is low; each process reloads scipy)
    "sizing": {"minimum_rotor_stall_margin_deg": None,   # None = diagnostica, oppure gradi richiesti
               "minimum_section_thickness_m": 0.001,     # thinnest blade section [m]: 1 mm keeps the root
                                                         #   printable (chord >= 8.3 mm with a 12 % profile)
               # --- advanced (defaults of 2_ventola/ventola_designer/settings.py; other keys of
               #     that file are accepted too; the bounds above are already set by the keys
               #     corda_su_D_min_max and calettamento_min_max_deg, do not repeat them here)
               "minimum_circumferential_gap_m": 0.0,   # smallest gap between neighbouring blades [m]
               "max_solidity": 0.8,                    # [-] largest blade solidity
               "max_Mach": 0.3,                        # [-] largest Mach number allowed
               "loss_model": "none",                   # "none" or "prandtl_free_rotor" (tip losses)
               "maxiter": 80,                          # SLSQP iterations
               "starts": 3,                            # SLSQP starts per profile/blades pair
               "seed_samples": 48,                     # random samples to choose the starts from
               "random_seed": 42},                     # seed: same input = same result
}

SISTEMA = {
    # Read by run_sistema.py and 3_sistema.
    "confronto_statore": True,   # True = chain run twice (Statore/, NoStatore/) + 5_confronto_statore/;
                                 #   the stator flag of VENTOLA is overridden per variant; about twice the
                                 #   time (1_spinta is shared). False = one chain with VENTOLA["statore"]
    "iterazioni_fascia": 3,      # most venturi+fan passes to fit the band L_disk to the real fan (stops
                                 #   earlier when L_disk changes by less than 0.5 mm; then one last venturi
                                 #   pass with alternatives); 1 = no loop, L_disk as written
    "combinazioni": "tutte",     # series of cases ("4; 6" values): "tutte" = every combination,
                                 #   "accoppiate" = i-th value of each key with the i-th of the others
    "densita_kg_m3": 1240.0,     # [kg/m3] material of the tube and the blades (PLA), for the mass estimate
                                 #   (tube + blades; motor, screws, electronics excluded)
    "riempimento": 1.0,          # [-] solid share of the print (thin walls = 1.0)
    "n_propulsori": None,        # thrusters mounted on the vehicle (their mass is added to the vehicle in the
                                 #   mass -> power decision); None = SPINTA["n_ugelli"]
    "esponente_potenza_massa": 1.5,  # [-] power ~ mass^e at fixed geometry (actuator disk: thrust ~ mass,
                                 #   power ~ thrust^1.5); SPINTA["massa"] is the vehicle mass with the reference variant
    "processi": None,            # most processes of the whole run (series, variants, scan, grid study, fan
                                 #   together; the cap is split going inwards); None = automatic:
                                 #   min(physical cores, floor(0.6 x free RAM / 1.5 GB)), at least 1;
                                 #   1 = everything in sequence, as before
}
