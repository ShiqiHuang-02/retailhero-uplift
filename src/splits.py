"""Preserve an existing customer split; never silently create a new split."""
import hashlib
import json
from pathlib import Path

import pandas as pd

SPLITS = ('train', 'validation', 'test')
FIELDS = ['client_id', 'split', 'position', 'treatment_flg', 'target']


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
        raise FileNotFoundError('缺少 data/splits 划分清单及校验信息，请从备份恢复；不要重新随机划分。')
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
