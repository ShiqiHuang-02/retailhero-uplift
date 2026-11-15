import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.splits import FIELDS, sha256, restore_splits, validate_assignments, create_assignments, write_new_manifest


class NewSplitTests(unittest.TestCase):
    def setUp(self):
        self.labels = pd.DataFrame({
            'client_id': [f'{i:05}' for i in range(100)],
            'treatment_flg': [i % 2 for i in range(100)],
            'target': [(i // 2) % 2 for i in range(100)],
        })

    def test_row_order_invariance_and_complete_disjoint_coverage(self):
        first = create_assignments(self.labels)
        shuffled = create_assignments(self.labels.sample(frac=1, random_state=17))
        pd.testing.assert_frame_equal(first, shuffled)
        self.assertEqual(set(first.client_id), set(self.labels.client_id))
        self.assertEqual(first.split.value_counts().to_dict(), {'train': 60, 'validation': 20, 'test': 20})
        self.assertTrue(first.client_id.is_unique)
        self.assertFalse(first.equals(create_assignments(self.labels, seed=43)))

    def test_roundtrip_keeps_leading_zero_ids_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            labels = root / 'labels.csv'
            self.labels.to_csv(labels, index=False)
            output = root / 'split'
            write_new_manifest(labels, output)
            restored = restore_splits(self.labels, output)
            self.assertEqual(sum(map(len, restored.values())), 100)
            original = (output / 'metadata.json').read_bytes()
            with self.assertRaises(FileExistsError):
                write_new_manifest(labels, output, seed=43)
            self.assertEqual(original, (output / 'metadata.json').read_bytes())

    def test_rejects_duplicate_labels_and_tiny_strata(self):
        with self.assertRaisesRegex(ValueError, '重复'):
            create_assignments(pd.concat([self.labels, self.labels.iloc[:1]]))
        with self.assertRaisesRegex(ValueError, '至少'):
            create_assignments(self.labels.iloc[:4])


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
