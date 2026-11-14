"""RetailHero 营销选人策略 —— 交互看板（业务视角）。

运行（项目根目录）：
    pip install streamlit      # 若未安装
    streamlit run dashboard/app.py

数据来源：
  * reports/tables/test_policy_results.csv      —— 主结果（跑完 01→02→03 生成）
  * reports/tables/test_policy_comparisons.csv  —— 策略对比
  * reports/portfolio/tables/contact_curve.csv  —— 预算曲线（build_portfolio 生成）
  * reports/method_comparison/learner_gains.csv —— meta-learner 对比（run_method_comparison 生成）
  * reports/method_comparison/auuc.csv          —— AUUC

所有文件缺失时对应板块自动跳过，不报错。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="RetailHero 营销选人策略", page_icon="📈", layout="wide")


@st.cache_data
def load_optional(rel_path: str) -> pd.DataFrame | None:
    p = ROOT / rel_path
    return pd.read_csv(p) if p.exists() else None


def gain_bar(df: pd.DataFrame, value_col: str, color: str) -> plt.Figure:
    df = df.sort_values(value_col)
    lower = (df[value_col] - df["ci_low"]).to_numpy()
    upper = (df["ci_high"] - df[value_col]).to_numpy()
    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.45 * len(df))))
    ax.barh(df["strategy"], df[value_col], xerr=np.vstack([lower, upper]), capsize=3, color=color)
    ax.axvline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("per 1000 candidates")
    return fig


st.title("RetailHero 营销选人策略看板")
st.caption("Uplift Modeling 离线评价：有限触达名额下，把营销预算花在能带来「增量」购买的客户上。")

policy_results = load_optional("reports/tables/test_policy_results.csv")
comparisons = load_optional("reports/tables/test_policy_comparisons.csv")
contact_curve = load_optional("reports/portfolio/tables/contact_curve.csv")
method_gains = load_optional("reports/method_comparison/learner_gains.csv")
auuc = load_optional("reports/method_comparison/auuc.csv")

# ---- 1. 核心结论 ----
if comparisons is not None:
    primary = comparisons[comparisons["comparison"] == "Uplift - Response"]
    if not primary.empty:
        row = primary.iloc[0]
        st.header("核心结论（20% 触达，离线 DR 估计）")
        c1, c2, c3 = st.columns(3)
        c1.metric("Uplift − Response 增量", f"{row['extra_gain_per_1000']:.2f} 人/千人")
        c2.metric("近似 95% CI 下界", f"{row['ci_low']:.2f}")
        c3.metric("近似 95% CI 上界", f"{row['ci_high']:.2f}")
        st.caption("⚠️ 历史数据上的离线估计，不是线上实验实际收益；因果解释依赖识别假设（见 README「局限性」）。")

# ---- 2. 策略对比 ----
if policy_results is not None:
    st.header("各策略增量价值（每千人候选客户）")
    st.pyplot(gain_bar(policy_results.copy(), "gain_per_1000", "#4C78A8"))
    st.dataframe(policy_results.round(2))

# ---- 3. 预算曲线 ----
if contact_curve is not None:
    st.header("触达比例 → 增量价值曲线")
    fig, ax = plt.subplots(figsize=(8, 5))
    for strategy, g in contact_curve.groupby("strategy"):
        ax.plot(g["contact_share"] * 100, g["gain_per_1000"], label=strategy, linewidth=2)
    ax.axvline(20, color="gray", linestyle=":", alpha=0.6)
    ax.set_xlabel("contact share (%)")
    ax.set_ylabel("gain per 1000 candidates")
    ax.set_title("Budget curve (validation, DR)")
    ax.legend()
    st.pyplot(fig)

# ---- 4. 净收益计算器 ----
if policy_results is not None:
    st.header("净收益情景（可调参数）")
    st.caption("净收益 = 增量购买 × 假设毛利 − 触达量 × 触达成本（同一货币单位）")
    col1, col2 = st.columns(2)
    margin = col1.slider("每名增量购买客户的贡献毛利", 0.0, 50.0, 10.0, 0.5)
    cost = col2.slider("每次触达成本", 0.0, 2.0, 0.1, 0.05)
    net = policy_results.copy()
    net["net_value_per_1000"] = net["gain_per_1000"] * margin - net["contacts_per_1000"] * cost
    # 净收益的置信区间：触达成本项是常数（仅平移），增益项按 margin 线性缩放
    net["ci_low"] = net["ci_low"] * margin - net["contacts_per_1000"] * cost
    net["ci_high"] = net["ci_high"] * margin - net["contacts_per_1000"] * cost
    st.pyplot(gain_bar(net, "net_value_per_1000", "#59A14F"))
    st.dataframe(net.round(2))

# ---- 5. Meta-learner 对比 ----
if auuc is not None or method_gains is not None:
    st.header("Meta-learner 对比（T / S / X）")
    c1, c2 = st.columns(2)
    if auuc is not None:
        c1.subheader("AUUC（每千人）")
        c1.dataframe(auuc.round(2))
    if method_gains is not None:
        c2.subheader("20% DR 策略价值")
        c2.dataframe(method_gains.round(2))

st.markdown("---")
st.caption("数据与口径详见项目 README；本看板只展示离线分析结果。")
