"""Struttura dei risultati coerente con il Venturi, senza conversioni di formato."""
from pathlib import Path
import shutil

FOLDERS = ('00_sintesi', '01_grafici', '02_excel', '03_cad', '04_cfd', '05_convergenza')


def organize_results(directory):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Serve una cartella di esecuzione.')
    mapping = {'report.json': '00_sintesi', 'RISULTATO.md': '00_sintesi',
               'preview.svg': '01_grafici', 'sections.csv': '02_excel',
               'blade_points.csv': '03_cad',
               'optimization.json': '05_convergenza', 'paraview': '04_cfd'}
    mapping.update({p.name: '03_cad' for p in root.glob('NACA*.dat')})
    mapping['CAD_info.json'] = '03_cad'
    mapping.update({f'{n}.{e}': '03_cad' for n in ('pala', 'ventola_A', 'ventola_B_speculare')
                    for e in ('step', 'stl')})
    moves = []
    for name, folder in mapping.items():
        source = root/name
        if not source.exists():
            continue
        target = root/folder/name if name != 'paraview' else root/folder
        if source.is_symlink() or root not in source.resolve().parents or root not in target.resolve().parents:
            raise ValueError('Percorso fuori dalla cartella risultati.')
        if target.exists():
            raise ValueError(f'Destinazione già presente: {target}')
        moves.append((source,target))
    for source,target in moves:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(source),str(target))
    for name in FOLDERS:
        (root/name).mkdir(exist_ok=True)
    return root
