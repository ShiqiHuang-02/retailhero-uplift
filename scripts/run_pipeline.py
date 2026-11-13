"""Run all notebooks using this interpreter, with a fresh kernel for each."""
import json
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    1: '01_data_exploration.ipynb',
    2: '02_modeling.ipynb',
    3: '03_policy_evaluation.ipynb',
    5: '05_robustness_and_business.ipynb',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', nargs='+', type=int, choices=NOTEBOOKS,
                        default=list(NOTEBOOKS), help='Ordered analysis steps; 04 is the existing portfolio viewer')
    parser.add_argument('--engine', choices=['kernel', 'inprocess'], default='kernel',
                        help='inprocess uses an isolated IPython process per notebook without Jupyter sockets')
    args = parser.parse_args()
    if args.steps != sorted(set(args.steps)):
        parser.error('Steps must be unique and ascending')
    os.chdir(ROOT)
    cache = ROOT / 'work/runtime'
    kernel_dir = cache / 'kernels/project'
    kernel_dir.mkdir(parents=True, exist_ok=True)
    (kernel_dir / 'kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-B', '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': 'RetailHero project', 'language': 'python',
    }), encoding='utf-8')
    os.environ['MPLCONFIGDIR'] = str(cache / 'matplotlib')
    os.environ['IPYTHONDIR'] = str(cache / 'ipython')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    # Cap threads to avoid oversubscription on large laptops; no model parameter changes.
    for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
        os.environ.setdefault(key, '4')
    required = []
    if 1 in args.steps:
        required += [ROOT / 'data/raw' / name for name in ['clients.csv.gz', 'uplift_train.csv.gz', 'purchases.csv.gz']]
        required += [ROOT / 'data/splits' / name for name in ['assignments.csv', 'metadata.json']]
    if args.steps[0] >= 2:
        required += [ROOT / 'data/processed' / f'{name}.parquet' for name in ['train', 'validation', 'test']]
    if args.steps[0] >= 3:
        required += [ROOT / 'models' / name for name in ['model_config.json', 'response_model.joblib', 'tlearner_m0.joblib', 'tlearner_m1.joblib']]
    if args.steps[0] == 3:
        required.append(ROOT / 'data/processed/validation_scores.parquet')
    if args.steps[0] == 5:
        required.append(ROOT / 'models/policy_config.json')
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError('Missing required inputs: ' + ', '.join(missing))
    for step in args.steps:
        name = NOTEBOOKS[step]
        started = time.monotonic()
        if args.engine == 'inprocess':
            subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/execute_notebook.py'), name], check=True)
            print(f'PASS {name}: {time.monotonic() - started:.1f}s', flush=True)
            continue
        notebook = nbformat.read(ROOT / name, as_version=4)
        for cell in notebook.cells:
            if cell.cell_type == 'code':
                cell.outputs = []
                cell.execution_count = None
        def progress(cell, cell_index, **kwargs):
            if cell.cell_type == 'code':
                print(f'{name}: cell {cell_index}', flush=True)
        manager = KernelManager(kernel_name='project', kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernel_dir.parent)]))
        client = NotebookClient(notebook, km=manager, timeout=1800, allow_errors=False, on_cell_start=progress)
        try:
            # Explicit cleanup because the manager is supplied by this script.
            with client.setup_kernel(cwd=str(ROOT), cleanup_kc=True):
                client.execute()
        finally:
            nbformat.write(notebook, ROOT / name)
        print(f'PASS {name}: {time.monotonic() - started:.1f}s', flush=True)


if __name__ == '__main__':
    main()
