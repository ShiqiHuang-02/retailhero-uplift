"""Budget optimization: choose the profit-maximizing contact share.

Reads the validation contact curve (already produced by scripts/build_portfolio.py)
and, for given margin/cost assumptions, finds the contact share that maximizes
net value per 1000 candidates:

    net_value = gain_per_1000 * margin - contacts_per_1000 * cost

Reports the optimum per strategy with an honest caveat about post-selection:
the share is chosen ON the validation set, so its held-out value will regress
toward the mean (selection bias). The optimum is a discrete approximation over
21 contact-share grid points (0%, 5%, ..., 100%), not a continuous optimizer.

Run from the project root:
    .venv/bin/python -B scripts/run_budget_optimization.py --margin 10 --cost 0.5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def net_value_frame(curve: pd.DataFrame, margin: float, cost: float) -> pd.DataFrame:
    z = curve.copy()
    z["net_value_per_1000"] = z.gain_per_1000 * margin - z.contacts_per_1000 * cost
    z["net_ci_low"] = z.ci_low * margin - z.contacts_per_1000 * cost
    z["net_ci_high"] = z.ci_high * margin - z.contacts_per_1000 * cost
    return z


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--margin", type=float, default=10.0, help="Contribution margin per incremental buyer (default 10)")
    parser.add_argument("--cost", type=float, default=0.5, help="Contact cost per message (default 0.5)")
    parser.add_argument("--curve", type=Path, default=ROOT / "reports/portfolio/tables/contact_curve.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/budget")
    args = parser.parse_args(argv)

    if not args.curve.exists():
        raise FileNotFoundError(
            f"预算曲线不存在：{args.curve}。请先运行 scripts/build_portfolio.py 生成。"
        )

    curve = pd.read_csv(args.curve)
    z = net_value_frame(curve, args.margin, args.cost)

    rows = []
    for strategy, g in z.groupby("strategy"):
        best = g.loc[g.net_value_per_1000.idxmax()]
        rows.append({
            "strategy": strategy,
            "optimal_contact_share": round(float(best.contact_share), 4),
            "optimal_net_per_1000": round(float(best.net_value_per_1000), 4),
            "net_ci_low": round(float(best.net_ci_low), 4),
            "net_ci_high": round(float(best.net_ci_high), 4),
            "gain_at_opt": round(float(best.gain_per_1000), 4),
        })
    optimal = pd.DataFrame(rows)

    args.output.mkdir(parents=True, exist_ok=True)
    optimal.to_csv(args.output / "optimal_budget.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    for strategy, g in z.groupby("strategy"):
        (line,) = ax.plot(g.contact_share * 100, g.net_value_per_1000, label=strategy)
        best = g.loc[g.net_value_per_1000.idxmax()]
        ax.plot(best.contact_share * 100, best.net_value_per_1000, "o", color=line.get_color(), markersize=7)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("contact share (%)")
    ax.set_ylabel("net value per 1000 candidates")
    ax.set_title(f"Net value vs contact share (margin={args.margin}, cost={args.cost})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.output / "net_value_curves.png", dpi=110)
    plt.close(fig)

    print(f"最优触达比例（margin={args.margin}, cost={args.cost}，验证集离线估计）：")
    print(optimal.to_string(index=False))
    print("\n⚠️ 选后保证：以上最优在验证集上选出，测试集/线上表现会回归（selection bias）。")
    print("   正式做法：验证集选 k*，再用独立测试集或线上实验确认；不要直接拿验证集最优值当预期收益。")
    print(f"\n输出目录：{args.output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
