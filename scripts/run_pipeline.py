"""Run all notebooks using this interpreter, with a fresh kernel for each."""
import json
import os
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[1]


def main():
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
    required = [ROOT / 'data/raw' / name for name in ['clients.csv.gz', 'uplift_train.csv.gz', 'purchases.csv.gz']]
    required += [ROOT / 'data/splits' / name for name in ['assignments.csv', 'metadata.json']]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError('Missing required inputs: ' + ', '.join(missing))
    for name in ['01_data_exploration.ipynb', '02_modeling.ipynb', '03_policy_evaluation.ipynb']:
        started = time.monotonic()
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
