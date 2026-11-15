"""Preserve an existing customer split; never silently create a new split."""
import hashlib
import json
import random
from pathlib import Path

import pandas as pd

SPLITS = ('train', 'validation', 'test')
FIELDS = ['client_id', 'split', 'position', 'treatment_flg', 'target']


def create_assignments(labels, seed=42):
    """Create a NEW 60/20/20 experiment, invariant to input row order.

    Stratify by treatment and outcome, round within each stratum, and store
    each split in client ID order. This does not recover the historical split.
    """
    labels = labels[['client_id', 'treatment_flg', 'target']].copy()
    if labels.empty or labels.isna().any().any():
        raise ValueError('标签表为空或含缺失值')
    labels['client_id'] = labels.client_id.astype(str)
    if not labels.client_id.is_unique:
        raise ValueError('标签表存在重复客户')
    if not labels[['treatment_flg', 'target']].isin([0, 1]).all().all():
        raise ValueError('处理与结果标签必须为 0/1')
    labels = labels.sort_values('client_id').reset_index(drop=True)
    rng = random.Random(seed)
    parts = []
    for _, group in labels.groupby(['treatment_flg', 'target'], sort=True):
        indices = group.index.tolist()
        if len(indices) < 5:
            raise ValueError('每个处理×结果层至少需要 5 名客户')
        rng.shuffle(indices)
        n_train, n_valid = round(len(indices) * .6), round(len(indices) * .2)
        chunks = [indices[:n_train], indices[n_train:n_train+n_valid], indices[n_train+n_valid:]]
        for name, chunk in zip(SPLITS, chunks):
            parts.append(labels.loc[chunk].assign(split=name))
    combined = pd.concat(parts, ignore_index=True)
    ordered = []
    for name in SPLITS:
        frame = combined.loc[combined.split.eq(name)].sort_values('client_id').copy()
        frame['position'] = range(len(frame))
        ordered.append(frame[FIELDS])
    assignments = pd.concat(ordered, ignore_index=True)
    validate_assignments(assignments)
    return assignments


def write_new_manifest(labels_path, output, seed=42):
    """Write a manifest only to an unused location; preserve existing experiments."""
    output = Path(output)
    if any((output / name).exists() for name in ['assignments.csv', 'metadata.json']):
        raise FileExistsError('划分文件已存在；请使用新的输出目录，不覆盖历史实验。')
    labels = pd.read_csv(labels_path, dtype={'client_id': str})
    assignments = create_assignments(labels, seed)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / 'assignments.csv'
    assignments.to_csv(csv_path, index=False, lineterminator='\n')
    metadata = {
        'schema_version': 1,
        'origin': 'New reproducible split; NOT the historical published experiment.',
        'algorithm': 'sorted_client_id_stratified_treatment_target_python_random_v1',
        'seed': seed,
        'fractions': {'train': .6, 'validation': .2, 'test': .2},
        'counts': {name: int(assignments.split.eq(name).sum()) for name in SPLITS},
        'stratum_counts': {
            name: {f'{int(t)}_{int(y)}': int(len(g)) for (t, y), g in
                   assignments.loc[assignments.split.eq(name)].groupby(['treatment_flg', 'target'])}
            for name in SPLITS
        },
        'assignments_sha256': sha256(csv_path),
        'source_labels_sha256': sha256(labels_path),
    }
    (output / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return metadata


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_assignments(assignments):
    if list(assignments.columns) != FIELDS:
        raise ValueError('划分清单字段不符合规范')
    if assignments.empty or assignments.isna().any().any():
        raise ValueError('划分清单为空或含缺失值')
    if not assignments.client_id.is_unique:
        raise ValueError('划分清单存在重复客户或跨集交叉')
    if set(assignments['split']) != set(SPLITS):
        raise ValueError('必须包含 train、validation、test 三个集合')
    for column in ['treatment_flg', 'target']:
        if not assignments[column].isin([0, 1]).all():
            raise ValueError(f'{column} 必须为 0/1')
    for name in SPLITS:
        positions = assignments.loc[assignments['split'].eq(name), 'position']
        if sorted(positions.tolist()) != list(range(len(positions))):
            raise ValueError(f'{name} 内部顺序必须是从 0 开始的连续整数')


def restore_splits(feature_table, manifest_dir='data/splits'):
    """Restore original membership AND row order after recomputing features."""
    manifest_dir = Path(manifest_dir)
    csv_path = manifest_dir / 'assignments.csv'
    metadata_path = manifest_dir / 'metadata.json'
    if not csv_path.exists() or not metadata_path.exists():
        raise FileNotFoundError('缺少 data/splits 划分清单及校验信息。历史复现请恢复备份；新实验请运行 python run_project.py --new-split，在独立目录生成新划分。')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    if metadata.get('schema_version') != 1:
        raise ValueError('不支持的划分清单版本')
    if sha256(csv_path) != metadata['assignments_sha256']:
        raise ValueError('划分清单校验失败，文件可能被修改')
    assignments = pd.read_csv(csv_path, dtype={'client_id': str})
    validate_assignments(assignments)
    counts = assignments['split'].value_counts().to_dict()
    if counts != metadata['counts']:
        raise ValueError('划分人数与元数据不一致')
    if feature_table.client_id.isna().any() or not feature_table.client_id.is_unique:
        raise ValueError('特征表存在空客户 ID 或重复客户')
    if set(feature_table.client_id) != set(assignments.client_id):
        raise ValueError('特征表与固定清单客户集合不一致')
    indexed = feature_table.set_index('client_id', drop=False)
    restored = {}
    for name in SPLITS:
        saved = assignments.loc[assignments['split'].eq(name)].sort_values('position')
        frame = indexed.loc[saved.client_id.tolist()].reset_index(drop=True)
        for column in ['treatment_flg', 'target']:
            if not frame[column].eq(saved[column].reset_index(drop=True)).all():
                raise ValueError(f'{name} 的 {column} 与固定清单不一致')
        restored[name] = frame
    return restored
