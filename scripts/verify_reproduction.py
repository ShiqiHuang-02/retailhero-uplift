"""Compare a completed rerun with an existing project without changing the baseline."""
import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--strict', action='store_true', help='Require prediction/report agreement within floating point tolerance')
    parser.add_argument('--report', default='reproduction_check.json', help='Report file name under reports/')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline = args.baseline.resolve()
    if root == baseline:
        raise ValueError('Baseline must be a separate directory')
    if Path(args.report).name != args.report:
        raise ValueError('Report must be a file name')
    result = {'baseline': str(baseline), 'strict': args.strict, 'checks': [], 'table_max_abs_differences': {}}
    for name in ['train', 'validation', 'test']:
        old = duckdb.read_parquet(str(baseline / f'data/processed/{name}.parquet')).df()
        new = duckdb.read_parquet(str(root / f'data/processed/{name}.parquet')).df()
        # Includes exact row order and label equality. Only floating point roundoff is allowed.
        pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-10, atol=1e-10)
        result['checks'].append(f'{name}: membership, order, labels and features/predictions match')
    old_scores = duckdb.read_parquet(str(baseline / 'data/processed/validation_scores.parquet')).df()
    new_scores = duckdb.read_parquet(str(root / 'data/processed/validation_scores.parquet')).df()
    identifiers = ['client_id', 'treatment_flg', 'target']
    pd.testing.assert_frame_equal(old_scores[identifiers], new_scores[identifiers])
    score_columns = ['response_score', 'p0', 'p1', 'uplift_score']
    result['validation_prediction_max_abs_differences'] = {
        column: float((old_scores[column] - new_scores[column]).abs().max()) for column in score_columns
    }
    if args.strict:
        pd.testing.assert_frame_equal(old_scores, new_scores, check_exact=False, rtol=1e-10, atol=1e-10)
    k = round(0.2 * len(new_scores))
    result['validation_top20_replaced_customers'] = {}
    for column in score_columns:
        old_ids = set(old_scores.sort_values([column, 'client_id'], ascending=[False, True]).head(k).client_id)
        new_ids = set(new_scores.sort_values([column, 'client_id'], ascending=[False, True]).head(k).client_id)
        result['validation_top20_replaced_customers'][column] = len(old_ids - new_ids)
    for path in sorted((baseline / 'reports/tables').glob('*.csv')):
        old = pd.read_csv(path)
        new = pd.read_csv(root / 'reports/tables' / path.name)
        columns = old.select_dtypes(include='number').columns
        pd.testing.assert_frame_equal(old.drop(columns=columns), new.drop(columns=columns))
        assert list(old.columns) == list(new.columns)
        if args.strict:
            pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-9, atol=1e-9)
        delta = np.abs(old[columns].to_numpy() - new[columns].to_numpy())
        result['table_max_abs_differences'][path.name] = float(np.nanmax(delta)) if delta.size else 0.0
    executed_cells = 0
    for path in sorted(root.glob('0[123]_*.ipynb')):
        notebook = json.loads(path.read_text())
        old_notebook = json.loads((baseline / path.name).read_text())
        assert len(notebook['cells']) == len(old_notebook['cells'])
        for index, (cell, old_cell) in enumerate(zip(notebook['cells'], old_notebook['cells'])):
            if cell['cell_type'] != 'code':
                continue
            assert cell['execution_count'] is not None, (path.name, index, 'not run')
            assert not any(output.get('output_type') == 'error' for output in cell.get('outputs', []))
            if not (path.name.startswith('01') and index in [41, 53]):
                assert cell['source'] == old_cell['source'], (path.name, index, 'unexpected code change')
            executed_cells += 1
    result['executed_code_cells'] = executed_cells
    results = pd.read_csv(root / 'reports/tables/test_policy_results.csv').set_index('strategy')
    comparisons = pd.read_csv(root / 'reports/tables/test_policy_comparisons.csv').set_index('comparison')
    result['test_uplift_gain_per_1000'] = float(results.loc['Uplift', 'gain_per_1000'])
    result['test_uplift_minus_response_per_1000'] = float(comparisons.loc['Uplift - Response', 'extra_gain_per_1000'])
    result['status'] = 'strict_comparison_passed' if args.strict else 'baseline_comparison_completed_differences_reported'
    out = root / 'reports' / args.report
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
