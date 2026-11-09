# 新增数据字典

所有 CSV 为 UTF-8，标题使用稳定英文字段名便于 SQL／Tableau 连接；中文解释见本文件。空的 Bootstrap 上下限表示该比较没有执行 Bootstrap，不表示 0。

## 表粒度与主键

| 表 | 一行代表什么／主键 | 范围与用途 |
|---|---|---|
| customer_policy_mart.parquet | split × client_id × strategy | 客户策略明细；只保存在本地 reports/portfolio，不打入 Tableau 包 |
| policy_summary.csv | split × strategy | 验证／既有测试，固定 20% 触达的策略价值 |
| paired_comparisons.csv | split × comparison | 策略配对差异；仅原主比较有 Bootstrap |
| selected_profiles.csv | split × strategy | 按选择权重计算的人群画像 |
| policy_overlap.csv | split × strategy_a × strategy_b | 四种确定性策略的选人集合关系 |
| overall_rates.csv | treatment_flg | 三个划分合计的全体有标签客户，描述性购买率 |
| overall_difference.csv | 全表一行 | 全样本触达组减对照组购买率差异，单位百分点 |
| contact_curve.csv | strategy × contact_share | 验证集、0%–100% 触达比例，间隔 5% |
| uplift_calibration.csv | uplift_group | 验证集按预测分数从低到高分为五组 |
| propensity_scenarios.csv | assumed_constant_propensity | 验证集主比较；变动假定常数 e 的情景 |
| cost_scenarios.csv | strategy × contact_share × assumed_margin × assumed_contact_cost | 验证集，九组假设成本毛利组合 |
| experiment_sample_sizes.csv | assumed_baseline_rate × mde_pp | 两组等量、双侧 5%、功效 80% 的近似样本量 |
| test_policy.csv／test_comparisons.csv／validation_profiles.csv | 对应上表的固定 split 子集 | Tableau 展示专用，避免误混合验证和测试数据 |

## 核心指标

| 字段 | 定义与单位 | 聚合规则 |
|---|---|---|
| candidate_count | 评价数据集候选客户数 | 不跨策略相加 |
| contact_count／expected_contacts | 选择权重合计，Random 为期望人数 | 不跨策略相加 |
| selection_weight | 确定性策略 0/1；Random 为 k/n | 每个客户同一策略仅一行 |
| contacts_per_1000 | 1,000 × 平均选择权重 | 每千名候选客户触达数 |
| gain_per_1000 | 1,000 × mean(选择权重 × DR 分数) | 已聚合结果，不能跨比例求和 |
| estimate_per_1000 | 1,000 × mean((Uplift权重−基线权重) × DR 分数) | 配对差异，不是两个独立均值的方差相加 |
| ci_low／ci_high | 策略收益的正态近似 95% 区间 | 与对应点估计相同分母和单位 |
| normal_ci_low／normal_ci_high | 配对差异的正态近似区间 | 固定模型条件下 |
| bootstrap_ci_low／bootstrap_ci_high | 配对差值重采样均值的 2.5%／97.5% 分位数 | 仅主比较计算 |
| se_per_1000 | 客户策略贡献的样本标准差／sqrt(n) × 1,000 | 不跨分组直接平均标准误 |
| ci_width | normal_ci_high − normal_ci_low | Tableau 甘特区间条的长度 |
| contact_share | 请求触达比例，0–1 | 实际比例因人数取整有微小差异 |
| purchase_rate | buyers / customers，0–1 | 若需要合并，重新以人数加权；不能简单求和 |
| *_pp | 概率差 × 100 | 百分点，不是相对百分比 |
| jaccard | 交集人数／并集人数 | 0–1，矩阵对称 |
| share_of_a | 交集人数／策略 A 选中人数 | 0–1，一般不保证对称 |
| net_value_per_1000 | gain_per_1000 × 毛利 − contacts_per_1000 × 触达成本 | 假设货币单位／千名候选客户 |
| net_ci_low／net_ci_high | 固定毛利和成本后的效果区间线性变换 | 不含经济参数不确定性 |
| mde_pp | 规划的最小可检测购买率差异 | 百分点，以所有分组客户为分母 |
| customers_per_arm | 每个随机策略组需要的候选客户数 | 非短信发送数 |

## 客户特征与分数

`recency_days` 是截止点距最近交易的日历天数；`txn_count_history` 和 `spend_history` 为提供历史期间的交易数、消费额，不代表终身值；`txn_count_30d` 和 `spend_30d` 为截止点前 30 天口径。统计截止点沿用 2019-03-19，不声称它是已经核实的营销发送日。

`response_score` 是原全样本购买模型分数；`p0`／`p1` 是两组结果模型预测；`uplift_score=p1-p0`。分数由原训练集模型生成，评价集没有参与模型拟合。`rfm_score` 使用原训练集分位阈值。`*_rank` 在每个 split 内按分数降序、客户 ID 升序确定。

`dr_score` 沿用 e=0.5 假设。条件因果识别、观察窗口和测试集历史等限制见原 `docs/research_design.md` 与新增说明。处理概率、成本和规划基线均不能因字段存在而视为实测事实。

## Tableau 关联规则

各汇总表分别连接，避免 JOIN 导致行数膨胀。同一数据集下策略表、曲线表和画像表粒度不同。禁止通过 client_id 连接汇总表。展示前筛选到一个 split；当前工作簿已通过专用子集固定范围。曲线中 contact_share 必须作为连续维度，以保留每种策略 21 个点。
