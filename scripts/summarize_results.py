"""Generate or check the README result block from the canonical test tables."""
import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = '<!-- RESULTS:START -->', '<!-- RESULTS:END -->'


def result_block(root):
    with (root / 'reports/tables/test_policy_results.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    with (root / 'reports/tables/test_policy_comparisons.csv').open() as stream:
        primary = next(r for r in csv.DictReader(stream) if r['comparison'] == 'Uplift - Response')
    lines = ['| 策略 | 预计新增购买人数／千名候选客户 | 近似 95% CI |', '|---|---:|---:|']
    for row in rows:
        lines.append(f"| {row['strategy']} | {float(row['gain_per_1000']):.2f} | [{float(row['ci_low']):.2f}, {float(row['ci_high']):.2f}] |")
    lines += ['', f"Uplift 相对 Response 的离线估计差异为 **{float(primary['extra_gain_per_1000']):.2f} 人／千名候选客户**，配对差异的近似 95% CI 为 **[{float(primary['ci_low']):.2f}, {float(primary['ci_high']):.2f}]**。"]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    args = parser.parse_args()
    block = result_block(ROOT)
    if not (args.check or args.write):
        print(block)
        return
    path = ROOT / 'README.md'
    text = path.read_text(encoding='utf-8')
    before, rest = text.split(START)
    current, after = rest.split(END)
    expected = '\n' + block + '\n'
    if args.check:
        if current != expected:
            raise SystemExit('README differs from result tables. Run scripts/summarize_results.py --write after reviewing the new experiment.')
        print('PASS: README result block matches canonical test tables.')
    else:
        path.write_text(before + START + expected + END + after, encoding='utf-8')


if __name__ == '__main__':
    main()
