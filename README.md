# RetailHero Uplift Modeling：营销增量效果与触达策略评估

基于 X5 RetailHero 公开数据，研究在**只能触达 20% 候选客户**时，如何通过客户选择增加购买人数。项目由因果推断课程作业扩展，涵盖交易特征构建、Uplift 建模、营销策略离线评价及不确定性分析。

购买概率高，不一定意味着营销能带来额外购买。本项目对比按预测增量、购买概率、RFM 和随机分配名额的策略。20% 是预设容量约束，不是已确认的最优预算。

## 主要结果

下表为**历史固定划分的内部测试集、20% 触达比例、DR 估计**。指标表示相对完全不触达时，每千名候选客户的预计新增购买人数；分母包含未被选中的客户。

<!-- RESULTS:START -->
| 策略 | 预计新增购买人数／千名候选客户 | 近似 95% CI |
|---|---:|---:|
| Random | 5.20 | [3.52, 6.89] |
| RFM | 1.55 | [-1.00, 4.10] |
| Response | 2.57 | [0.27, 4.88] |
| Response_p1 | 3.04 | [0.73, 5.35] |
| Uplift | 10.86 | [6.70, 15.02] |

Uplift 相对 Response 的离线估计差异为 **8.29 人／千名候选客户**，配对差异的近似 95% CI 为 **[3.55, 13.02]**。
<!-- RESULTS:END -->

![测试集策略价值与配对差异区间](reports/portfolio/figures/01_policy_uncertainty.png)

数据出处：[策略结果表](reports/tables/test_policy_results.csv)、[配对差异表](reports/tables/test_policy_comparisons.csv)。图右侧另展示固定模型、固定选人结果的配对 Bootstrap 区间，与验证集上重新选人的 Bootstrap 分析不同。

这些是**离线估计，不能表述为实际新增客户或已实现利润**。测试集此前已被查看；本轮整理不构成新的独立测试验证。新划分和合成演示会产生不同结果。

## 方法与数据

原始数据来自 [X5 RetailHero Uplift Modeling](https://ods.ai/competitions/x5-retailhero-uplift-modeling)，包含客户资料、历史交易及营销沟通标签。历史分析使用 200,039 名有标签客户，训练／验证／内部测试样本量分别为 120,023／40,008／40,008。

1. **特征构建**：使用 DuckDB SQL 将商品明细汇总到交易，再汇总到客户；检查交易信息冲突，避免金额重复累计。处理异常年龄，剔除无法确认在特征截止点之前可用的日期字段。
2. **建模与排序**：以 HistGradientBoosting 为基学习器训练 T-learner；对照策略包括 RFM、全训练样本响应模型 Response、触达组响应模型 Response_p1。S/X-learner 和 Qini/AUUC 提供补充诊断。
3. **策略评价**：使用 DR 与 IPW 估计相对不触达的增量价值，并按同一批客户计算策略差异。Random 采用固定名额随机选人的期望权重，不是一次随机抽样的偶然结果。
4. **稳健性分析**：检查处理概率设定、客户 Bootstrap、开发集重复划分和不同模型；在假设成本与毛利下进行验证集预算情景分析。

训练集用于模型拟合与 RFM 阈值确定，验证集用于诊断与方案比较；内部测试集用于报告既有固定策略。详情见[研究设计](docs/research_design.md)、[稳健性摘要](reports/audit/summary.md)和[业务简报](docs/business_brief.md)。

## 快速开始

### 安装依赖

在项目根目录执行。已验证的本地解释器为 Python 3.14.7；依赖安装与跨平台验证状态见[验证记录](docs/public_repository_validation.md)。

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` 列出主分析直接依赖；`requirements-lock.txt` 保留历史本地环境的完整版本快照。Windows 激活命令为 `.venv\Scripts\activate`。

### 无原始数据：合成演示

```bash
python run_project.py --demo
```

默认生成 20,000 名合成客户，在 `work/demo/` 独立执行 01 → 02 → 03。结果位于 `work/demo/reports/tables/`，不会覆盖正式数据、报表或 Notebook 输出。合成数据包含人为设定的异质性效果，只用于说明流程，不作为真实业务效果证据；运行时间依机器与环境而定。

再次运行时请指定新目录，例如 `python run_project.py --demo --output work/demo-2`；程序拒绝覆盖已有实验。

### 有原始数据：新划分完整运行

从[数据来源页面](https://ods.ai/competitions/x5-retailhero-uplift-modeling/data)自行获取数据，将 `clients.csv.gz`、`uplift_train.csv.gz`、`purchases.csv.gz` 放到 `data/raw/`，然后运行：

```bash
python run_project.py --new-split
```

命令将原始文件复制到 `work/new-split/`，按客户 ID 排序后，以固定种子 42 在“处理 × 结果”层内生成约 60%／20%／20% 划分，再执行 01 → 02 → 03。记录输入哈希、划分算法、种子、样本量及软件版本。其他数据位置可通过 `--raw-dir` 指定。

**新划分用于复现分析方法，不保证复现上表数字。** 精确恢复历史实验仍需原 `assignments.csv`；仓库保留其哈希元数据，但不公开客户名单。已有该清单的用户可运行 `python run_project.py`，原地执行 01 → 02 → 03 → 05 并更新结果。完整用法见[复现说明](docs/reproducibility.md)。

### 检查与展示

```bash
python -m unittest discover -s tests -v
python scripts/summarize_results.py --check
```

已有汇总结果可直接阅读[HTML 分析报告](reports/portfolio/项目展示报告.html)（下载后在浏览器打开）。可选交互看板：

```bash
python -m pip install streamlit
python -m streamlit run dashboard/app.py
```

## 项目结构

| 入口 | 内容 |
|---|---|
| [01_data_exploration.ipynb](01_data_exploration.ipynb) | 数据审计、交易聚合、客户特征与固定划分恢复 |
| [02_modeling.ipynb](02_modeling.ipynb) | 响应模型、T-learner 与验证集诊断 |
| [03_policy_evaluation.ipynb](03_policy_evaluation.ipynb) | DR/IPW 策略评价、配对差异与预算曲线 |
| [04_portfolio_analysis.ipynb](04_portfolio_analysis.ipynb) | 画像、名单重合、成本情景与展示分析 |
| [05_robustness_and_business.ipynb](05_robustness_and_business.ipynb) | 处理概率、S-learner、Bootstrap 与划分稳定性 |
| [src/](src/) / [scripts/](scripts/) | 共用统计方法、划分校验、运行与报告生成 |
| [reports/](reports/) / [docs/](docs/) | 汇总表、图表、研究设计、复现及验证记录 |

可选分析包括[模型比较](scripts/run_method_comparison.py)、[预算情景](scripts/run_budget_optimization.py)和[线上实验方案](docs/online_experiment_plan.md)，运行命令见复现说明。Tableau 仅保留为[未完成原生验证的草稿](tableau/使用说明.md)，不作为已完成的展示成果。

## 解释边界

- **因果识别**：真实随机分配机制、营销触达定义和结果观察窗口尚未核实；`e=0.5` 是分析假设。特征截止点 `2019-03-19 00:00:00` 由项目设定，不代表已确认的触达时间。
- **统计不确定性**：主要区间条件于已训练模型，未完整包含模型重训、策略选择和多重比较的不确定性。部分 IPW 结果支持较弱，S-learner 在部分口径下优于 T-learner，不能据此认定 T-learner 最优。
- **业务外推**：样本主要覆盖近期活跃客户，缺少真实触达成本、贡献毛利和线上实验。预算寻优属于验证集探索，其最大值不能直接视为未来收益。

## 来源与项目说明

数据与字段来源见[研究设计的来源清单](docs/research_design.md#来源)。本仓库整理了客户特征工程、meta-learner 建模、策略离线评价、稳健性检查与展示流程；项目指标不同于官方竞赛排名指标。

原始数据、客户级中间结果、训练模型和本地运行目录不随代码发布。数据获取与使用应遵循原提供方条款；代码公开不代表附带原始数据再分发授权。版本记录见 [CHANGELOG.md](CHANGELOG.md)。
