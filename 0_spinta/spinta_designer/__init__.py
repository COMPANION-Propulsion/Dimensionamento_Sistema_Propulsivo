"""
Thrust needed to cover a distance in a given time, per nozzle.

    caso.py      results folder of the case, shared by every module
    profilo.py   motion profiles and thrust
    export.py    output files
    cli.py       command line
"""

from .profilo import PROFILES, Motion
from .cli import load_motion, run

__all__ = ["Motion", "PROFILES", "load_motion", "run"]
