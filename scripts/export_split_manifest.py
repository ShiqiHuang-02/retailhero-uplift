"""One-time export from existing processed data, not a random split generator."""
import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.splits import SPLITS, FIELDS, sha256, validate_assignments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('data/processed'))
    parser.add_argument('--labels', type=Path, default=Path('data/raw/uplift_train.csv.gz'))
    parser.add_argument('--output', type=Path, default=Path('data/splits'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('输出目录已存在；为保护原名单，不覆盖或重建划分清单。')
    rows = []
    for name in SPLITS:
        frame = duckdb.read_parquet(str(args.source / f'{name}.parquet')).df()
        record = frame[['client_id', 'treatment_flg', 'target']].copy()
        record['split'] = name
        record['position'] = range(len(record))
        rows.append(record[FIELDS])
    assignments = pd.concat(rows, ignore_index=True)
    validate_assignments(assignments)
    labels = pd.read_csv(args.labels, dtype={'client_id': str}).set_index('client_id')
    if not labels.index.is_unique or set(labels.index) != set(assignments.client_id):
        raise ValueError('原始标签与划分清单客户集合不一致')
    aligned = labels.loc[assignments.client_id].reset_index()
    for column in ['treatment_flg', 'target']:
        if not aligned[column].eq(assignments[column]).all():
            raise ValueError(f'原始标签与清单 {column} 不一致')
    args.output.mkdir(parents=True)
    csv_path = args.output / 'assignments.csv'
    assignments.to_csv(csv_path, index=False, lineterminator='\n')
    metadata = {
        'schema_version': 1,
        'origin': 'Existing processed datasets; exact membership and row order preserved. Original splitting algorithm is not reconstructed.',
        'counts': {name: int(assignments['split'].eq(name).sum()) for name in SPLITS},
        'assignments_sha256': sha256(csv_path),
        'source_parquet_sha256': {name: sha256(args.source / f'{name}.parquet') for name in SPLITS},
        'source_labels_sha256': sha256(args.labels),
    }
    (args.output / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
