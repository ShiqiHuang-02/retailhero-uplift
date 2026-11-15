"""Ensure demo preparation cannot mutate published results or reuse raw data."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_run import prepare_run


class RunIsolationTests(unittest.TestCase):
    def test_demo_isolated_from_existing_real_data_and_results(self):
        source = Path(__file__).resolve().parents[1]
        protected = [source / p for p in ['data/splits/metadata.json',
                     'reports/tables/test_policy_results.csv', '03_policy_evaluation.ipynb']]
        before = {p: p.read_bytes() for p in protected}
        with tempfile.TemporaryDirectory() as folder:
            out = prepare_run(source, Path(folder) / 'demo', demo=True, n_clients=100)
            self.assertFalse((out / 'reports/tables/test_policy_results.csv').exists())
            self.assertFalse((out / 'models/tlearner_m0.joblib').exists())
            meta = json.loads((out / 'run_metadata.json').read_text())
            self.assertEqual(meta['mode'], 'synthetic_demo')
            with self.assertRaises(FileExistsError):
                prepare_run(source, out, demo=True)
        self.assertEqual(before, {p: p.read_bytes() for p in protected})

    def test_missing_raw_data_fails_before_creating_output(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'run'
            with self.assertRaises(FileNotFoundError):
                prepare_run(source, out, raw_dir=Path(folder) / 'missing')
            self.assertFalse(out.exists())
