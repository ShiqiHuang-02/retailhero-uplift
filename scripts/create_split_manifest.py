"""Create a reproducible NEW split from raw labels; never overwrite history."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.splits import write_new_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, default=Path('data/raw/uplift_train.csv.gz'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(write_new_manifest(args.labels, args.output, args.seed), indent=2))


if __name__ == '__main__':
    main()
