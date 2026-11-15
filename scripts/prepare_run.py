"""Prepare a standalone analysis directory without historical results or models."""
import importlib.metadata
import json
import platform
import shutil
from pathlib import Path

from src.splits import sha256, write_new_manifest

RAW_FILES = ['clients.csv.gz', 'uplift_train.csv.gz', 'purchases.csv.gz']


def prepare_run(source, output, *, demo=False, raw_dir=None, seed=42, n_clients=20000):
    source, output = Path(source).resolve(), Path(output).resolve()
    raw_dir = Path(raw_dir or source / 'data/raw').resolve()
    if output.exists():
        raise FileExistsError(f'输出目录已存在：{output}。请用 --output 指定新的目录。')
    for folder in ['src', 'scripts', 'sql', 'docs', 'dashboard', 'data', 'models', 'reports', 'tableau']:
        if output.is_relative_to(source / folder):
            raise ValueError('请将独立实验放在 work/ 或项目以外的目录')
    if not demo:
        missing = [name for name in RAW_FILES if not (raw_dir / name).is_file()]
        if missing:
            raise FileNotFoundError('缺少原始数据：' + ', '.join(missing))
    elif n_clients < 100:
        raise ValueError('演示至少需要 100 名客户')
    output.mkdir(parents=True)
    for folder in ['src', 'scripts', 'sql', 'docs', 'dashboard']:
        shutil.copytree(source / folder, output / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ['run_project.py', 'requirements.txt']:
        shutil.copy2(source / name, output / name)
    label = '合成数据演示' if demo else '真实数据的新划分实验'
    notice = f'# {label}\n\n本目录独立保存本次运行。历史仓库的结论不适用于本次数据；以本次生成的表格为准。\n'
    (output / 'README.md').write_text(notice, encoding='utf-8')
    for path in source.glob('*.ipynb'):
        notebook = json.loads(path.read_text(encoding='utf-8'))
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                cell['outputs'], cell['execution_count'] = [], None
        notebook['cells'].insert(0, {'cell_type': 'markdown', 'id': 'experiment-context', 'metadata': {}, 'source': notice})
        (output / path.name).write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if demo:
        from scripts.make_demo_data import write_all
        write_all(output, n_clients=n_clients, seed=seed)
    else:
        (output / 'data/raw').mkdir(parents=True)
        for name in RAW_FILES:
            shutil.copy2(raw_dir / name, output / 'data/raw' / name)
        write_new_manifest(output / 'data/raw/uplift_train.csv.gz', output / 'data/splits', seed)
    metadata = {
        'mode': 'synthetic_demo' if demo else 'new_real_data_split',
        'status': 'prepared', 'seed': seed, 'python': platform.python_version(),
        'packages': {name: importlib.metadata.version(name) for name in
                     ['numpy', 'pandas', 'scikit-learn', 'duckdb', 'joblib']},
        'raw_sha256': {name: sha256(output / 'data/raw' / name) for name in RAW_FILES},
        'code_sha256': {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*'))
                        if p.suffix in ['.py', '.ipynb', '.sql']},
    }
    (output / 'run_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output
