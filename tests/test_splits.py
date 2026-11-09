import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.splits import FIELDS, sha256, restore_splits, validate_assignments


class SplitSafetyTests(unittest.TestCase):
    def setUp(self):
        self.assignments = pd.DataFrame([
            ['b', 'train', 0, 1, 0], ['a', 'train', 1, 0, 1],
            ['c', 'validation', 0, 1, 1], ['d', 'test', 0, 0, 0],
        ], columns=FIELDS)
        self.features = self.assignments[['client_id', 'treatment_flg', 'target']].sort_values('client_id').copy()
        self.features['new_feature'] = [10, 20, 30, 40]

    def manifest(self, folder):
        path = Path(folder)
        self.assignments.to_csv(path / 'assignments.csv', index=False)
        (path / 'metadata.json').write_text(json.dumps({
            'schema_version': 1, 'assignments_sha256': sha256(path / 'assignments.csv'),
            'counts': {'train': 2, 'validation': 1, 'test': 1},
        }))
        return path

    def test_restores_order_and_recomputed_features_without_processed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            restored = restore_splits(self.features, self.manifest(folder))
            self.assertEqual(restored['train'].client_id.tolist(), ['b', 'a'])
            self.assertEqual(restored['train'].new_feature.tolist(), [20, 10])

    def test_duplicate_customer_rejected(self):
        self.assignments.loc[3, 'client_id'] = 'a'
        with self.assertRaisesRegex(ValueError, '重复'):
            validate_assignments(self.assignments)

    def test_changed_label_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.manifest(folder)
            self.features.loc[self.features.client_id.eq('a'), 'target'] = 0
            with self.assertRaisesRegex(ValueError, 'target'):
                restore_splits(self.features, path)

    def test_changed_membership_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.manifest(folder)
            with self.assertRaisesRegex(ValueError, '客户集合'):
                restore_splits(self.features.iloc[:-1], path)

    def test_tampered_file_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.manifest(folder)
            with (path / 'assignments.csv').open('a') as f:
                f.write('\n')
            with self.assertRaisesRegex(ValueError, '校验失败'):
                restore_splits(self.features, path)

    def test_invalid_order_rejected(self):
        self.assignments.loc[1, 'position'] = 0
        with self.assertRaisesRegex(ValueError, '连续整数'):
            validate_assignments(self.assignments)

    def test_missing_manifest_never_randomly_resplits(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                restore_splits(self.features, folder)


if __name__ == '__main__':
    unittest.main()
