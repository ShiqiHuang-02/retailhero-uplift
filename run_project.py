"""Run the historical project, or an isolated demo / new-split experiment."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--demo', action='store_true', help='Synthetic data in work/demo; never changes published outputs')
    mode.add_argument('--new-split', action='store_true', help='Real data with a NEW deterministic split in work/new-split')
    parser.add_argument('--output', type=Path, help='New isolated directory; must not exist')
    parser.add_argument('--raw-dir', type=Path, help='Raw CSV directory for --new-split (default: data/raw)')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--n-clients', type=int, default=20000, help='Synthetic sample size for --demo')
    parser.add_argument('--steps', nargs='+', type=int, choices=[1, 2, 3, 5])
    parser.add_argument('--engine', choices=['kernel', 'inprocess'], default='inprocess')
    args = parser.parse_args()
    isolated = args.demo or args.new_split
    steps = args.steps if args.steps is not None else ([1, 2, 3] if isolated else [1, 2, 3, 5])
    if steps != sorted(set(steps)):
        parser.error('Steps must be unique and ascending')
    if isolated and steps[:3] != [1, 2, 3]:
        parser.error('An isolated experiment must include steps 1 2 3')
    if not isolated and (args.output or args.raw_dir or args.seed != 42 or args.n_clients != 20000):
        parser.error('--output/--raw-dir/--seed/--n-clients require --demo or --new-split')
    if args.demo and args.raw_dir:
        parser.error('--raw-dir requires --new-split')
    if args.new_split and args.n_clients != 20000:
        parser.error('--n-clients requires --demo')
    root = ROOT
    if isolated:
        from scripts.prepare_run import prepare_run
        root = prepare_run(ROOT, args.output or ROOT / 'work' / ('demo' if args.demo else 'new-split'),
                           demo=args.demo, raw_dir=args.raw_dir or ROOT / 'data/raw',
                           seed=args.seed, n_clients=args.n_clients)
        print(f'Isolated experiment: {root}', flush=True)
    command = [sys.executable, '-B', str(root / 'scripts/run_pipeline.py'),
               '--engine', args.engine, '--steps', *map(str, steps)]
    result = subprocess.run(command, cwd=root)
    if isolated:
        path = root / 'run_metadata.json'
        metadata = json.loads(path.read_text(encoding='utf-8'))
        metadata.update(status='passed' if result.returncode == 0 else 'failed', steps=steps, engine=args.engine)
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if result.returncode == 0:
            print(f'Results: {root / "reports/tables/test_policy_results.csv"}', flush=True)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
