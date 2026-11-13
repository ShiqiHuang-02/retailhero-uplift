"""Verify a completed robustness revision against its local pre-edit backup."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import joblib
import nbformat
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    if baseline == ROOT:
        raise ValueError('Baseline must be a separate backup')
    result = {'baseline': str(baseline), 'checks': [], 'table_max_abs_differences': {}}
    for name in ['train', 'validation', 'test', 'validation_scores']:
        relative = f'data/processed/{name}.parquet'
        old = duckdb.read_parquet(str(baseline / relative)).df()
        new = duckdb.read_parquet(str(ROOT / relative)).df()
        pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-10, atol=1e-10)
        result['checks'].append(f'{name}: membership, row order, labels and values unchanged within 1e-10')
    for old_path in sorted((baseline / 'reports/tables').glob('*.csv')):
        old = pd.read_csv(old_path)
        new = pd.read_csv(ROOT / 'reports/tables' / old_path.name)
        pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-9, atol=1e-9)
        cols = old.select_dtypes(include='number').columns
        result['table_max_abs_differences'][old_path.name] = float(np.nanmax(np.abs(old[cols].to_numpy() - new[cols].to_numpy())))
    for name in ['response_model.joblib', 'tlearner_m0.joblib', 'tlearner_m1.joblib']:
        old = joblib.load(baseline / 'models' / name)
        new = joblib.load(ROOT / 'models' / name)
        assert old.named_steps['classifier'].get_params() == new.named_steps['classifier'].get_params()
    result['checks'].append('All three original classifiers retain their hyperparameters')
    assert sha256(baseline / '04_portfolio_analysis.ipynb') == sha256(ROOT / '04_portfolio_analysis.ipynb')
    result['checks'].append('Existing portfolio notebook preserved byte-for-byte')
    counts = {}
    for path in sorted(ROOT.glob('0[1235]_*.ipynb')):
        nb = nbformat.read(path, as_version=4)
        nbformat.validate(nb)
        code = [c for c in nb.cells if c.cell_type == 'code']
        assert all(c.execution_count is not None for c in code), path.name
        assert not any(o.output_type == 'error' for c in code for o in c.outputs), path.name
        counts[path.name] = len(code)
    result['executed_code_cells'] = counts
    audit = ROOT / 'reports/audit'
    metadata = json.loads((audit / 'run_metadata.json').read_text())
    assert metadata['status'] == 'completed'
    for relative, digest in {**metadata['input_sha256'], **metadata['output_sha256']}.items():
        assert sha256(ROOT / relative) == digest, relative
    for relative, digest in metadata['source_sha256'].items():
        path = ROOT / relative
        if path.suffix == '.ipynb':
            nb = nbformat.read(path, as_version=4)
            source = [(c.cell_type, c.source) for c in nb.cells]
            actual = hashlib.sha256(json.dumps(source, ensure_ascii=False).encode('utf-8')).hexdigest()
        else:
            actual = sha256(path)
        assert actual == digest, relative
    detail = pd.read_csv(audit / 'repeated_split_details.csv')
    assert set(detail.split_seed) == {101, 202, 303, 404, 505}
    assert len(detail) == 5 * 2 * 4
    bootstrap = pd.read_csv(audit / 'customer_bootstrap_results.csv')
    assert len(bootstrap) == 9 and bootstrap.repeats.eq(500).all()
    assert bootstrap.ci_low.le(bootstrap.ci_high).all()
    sensitivity = pd.read_csv(audit / 'propensity_sensitivity_gains.csv')
    assert len(sensitivity) == 3 * 2 * 5
    for name in ['customer_gender_profiles.csv', 'customer_numeric_profiles.csv',
                 'strategy_overlap.csv', 'slearner_strategy_gains.csv', 'propensity_diagnostics.csv']:
        assert not pd.read_csv(audit / name).empty
    result['checks'].append('Completed audit: input/source/output hashes, all five splits, 500 bootstrap draws and result tables verified')
    result['status'] = 'passed'
    destination = ROOT / 'reports/robustness_revision_check.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
