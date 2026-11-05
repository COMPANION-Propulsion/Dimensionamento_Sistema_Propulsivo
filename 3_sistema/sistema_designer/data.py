"""Letture dei risultati di un caso (solo file JSON, nessun ricalcolo dei moduli a monte)."""

import json
from dataclasses import dataclass
from pathlib import Path

from ventola_designer.polars import PolarGrid
from ventola_designer.pressure_bemt import solve_pressure

POLARS = Path(__file__).resolve().parents[2]/'2_ventola'/'ventola_designer'/'airfoils'/'polars_neuralfoil'
FOLDERS = ('00_sintesi', '01_grafici', '02_excel', '03_cad', '04_cfd')


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@dataclass
class Case:
    root: Path

    @property
    def out(self) -> Path:
        return self.root/'4_sistema'

    def folder(self, name: str) -> Path:
        p = self.out/name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def thrust(self) -> dict:
        return _json(self.root/'1_spinta'/'spinta.json')

    @property
    def venturi_file(self) -> Path:
        return self.root/'2_venturi'/'00_sintesi'/'risultati.json'

    @property
    def venturi(self) -> dict:
        return _json(self.venturi_file)

    @property
    def design_file(self) -> Path:
        return self.root/'2_venturi'/'05_convergenza'/'design.json'

    @property
    def fan_dir(self) -> Path:
        return self.root/'3_ventola'

    @property
    def fan(self) -> dict:
        return _json(self.fan_dir/'00_sintesi'/'report.json')

    def fan_point(self, stations=64, case=None, rpm=None):
        """BEMT del rotore scelto al punto di progetto, anello per anello."""
        rep = self.fan
        case = case or rep['input_case']
        d = rep['best']['design']
        polar = PolarGrid.load(POLARS/f"{d['profile']}.json")
        return solve_pressure(case, {**d, 'rpm': rpm or rep['best']['cases'][0]['rpm']},
                              case['operating_points'][0], polar, stations=stations)
