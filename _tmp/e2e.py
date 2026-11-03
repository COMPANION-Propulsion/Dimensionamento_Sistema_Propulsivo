import argparse, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "1_venturi"))
sys.path.insert(0, os.path.join(HERE, "..", "0_spinta"))
from venturi_designer import cli
from venturi_designer.core.propulsion import GRID_LEVELS
import spinta_designer

INPUT = '''
CASO = dict(nome="prova_e2e", sovrascrivi=True)
SPINTA = dict(distanza=1.0, tempo=10.0, massa=10.0, n_ugelli=2)
VENTURI = dict(fluid="air_20C", V0=0.0, p_amb=101325.0, T_ugello=None, D_ext_max=0.07,
               L_max=0.15, gap_parete=0.005, spessore_parete=0.002, L_disk=0.01,
               D_disk_min_ratio=0.4, P_max=None, turbulence_model="baldwin_lomax",
               n_up=4, n_down=5, grid="coarse", jobs=3, max_iter=MAXIT,
               tol_dp=0.01, max_cicli_dp=3)
'''
if __name__ == "__main__":
    GRID_LEVELS["coarse"] = dict(optimise=[(40, 18)], verify=[(40, 18), (56, 24), (80, 34)])
    path = os.path.join(HERE, "input_e2e.py")
    open(path, "w").write(INPUT.replace("MAXIT", sys.argv[1] if len(sys.argv) > 1 else "3"))
    res = os.path.join(HERE, "risultati")
    assert spinta_designer.run(path, res) == 0
    t = time.time()
    rc = cli.run_target_thrust(argparse.Namespace(input=path, output_dir=None, results_dir=res))
    print("rc", rc, round(time.time() - t), "s")
