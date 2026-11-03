
CASO = dict(nome="prova_e2e", sovrascrivi=True)
SPINTA = dict(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
VENTURI = dict(fluid="air_20C", V0=0.0, p_amb=101325.0, T_ugello=None, D_ext_max=0.07,
               L_max=0.15, gap_parete=0.005, spessore_parete=0.002, L_disk=0.01,
               D_disk_min_ratio=0.4, P_max=None, turbulence_model="baldwin_lomax",
               n_up=4, n_down=5, grid="coarse", jobs=3, max_iter=3,
               tol_dp=0.01, max_cicli_dp=3)
