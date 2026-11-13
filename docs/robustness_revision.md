# 2026-11-13 本地修订与真实数据验证

本次在原项目目录完成合并。修改前的 notebook、代码、文档、模型、报告和处理后数据备份在 `work/backups/before_robustness_20261113/`。原始数据和划分清单未改写，原 `src/splits.py` 的校验恢复逻辑保留。

## 修改范围

| 文件 | 修改 |
|---|---|
| 01_data_exploration.ipynb | ID、标签、交易键、金额冲突、缺失、负值、交易时间与特征关联检查失败时停止 |
| 02_modeling.ipynb | 校准改为“校准诊断”；增加跨集检查和分数解释边界 |
| 03_policy_evaluation.ipynb | 共用经测试的 DR/IPW 与策略选择实现；保持原公式、预算和主比较 |
| 04_portfolio_analysis.ipynb | 保留原文件及展示内容 |
| 05_robustness_and_business.ipynb | 处理概率敏感性、S-learner、客户画像、重选前 20% 的 bootstrap、五次划分稳定性、成本情景 |
| src/audit_core.py / src/causal_robustness.py | 统计计算、模型与增量分析模块 |
| run_project.py / scripts/run_pipeline.py | 统一运行入口，可指定步骤与执行方式 |
| scripts/execute_notebook.py | 无需 Jupyter 端口的独立 IPython 进程执行，保留表格及图像输出 |
| scripts/verify_robustness_revision.py | 修改前后数值与执行完整性核对 |

新增结果位于 `reports/audit/`；辅助模型位于 `models/audit/`。这些辅助模型不替换原主模型。原第四个 notebook 的客户画像与固定名单 bootstrap 保留，新分析使用原验证集，bootstrap 每次重新排序选人。

## 已完成的验证

- 使用本机既有 Python 3.14.7 虚拟环境及完整原始数据执行 01 → 02 → 03 → 05。
- 22 项测试通过：12 项数学计算测试、3 项模拟数据集成测试、7 项客户划分校验测试。
- 63 个代码单元格执行成功：01 为 31 个、02 为 10 个、03 为 14 个、05 为 8 个；无错误单元，图表已嵌入 notebook。
- 原训练／验证／测试客户、行序、标签、特征及验证预测在 1e-10 容差内一致；三个原模型的超参数一致。
- 原九张结果表最大绝对差异约 1.1e-14，仅浮点舍入差异。
- 04 原文件逐字节一致；新增分析输入、代码、结果表哈希及五个划分和 500 次 bootstrap 的完整性通过校验。

当前验证包含真实数据重建与训练；没有重新安装整个 Python 环境，也没有新增 Tableau 原生软件验证。

## 结果解读

验证集处理概率敏感性分析中，Uplift − Response 的 DR 点估计为 7.96–8.01 人／千人。逻辑回归处理概率 AUC 约 0.4996，无概率截断；这些结果不能证明随机化或排除未观测混杂。

五次开发集划分中，该 DR 点估计均为正，范围为 5.54–13.36 人／千人。各次划分共享客户，仅报告描述性统计，不把五次估计当成独立实验作显著性检验。

验证集主比较的重选人 bootstrap 近似 95% 区间为 [2.98, 12.30] 人／千人。固定模型、固定处理概率与 RFM 阈值，保留重复抽样副本；不包括重新训练和模型选择的不确定性。

S-learner 的点估计高于原 T-learner 排序策略。T − S 的 DR 差异为 −1.98，近似区间 [−5.60, 1.63]；IPW 差异为 −6.00，区间 [−11.63, −0.37]。两种结果都应保留，不能据此宣布 T-learner 最优，也不依据这一探索结果回头选择原主模型。

Uplift 和 Response 在验证集各选 8,002 人，只有 80 人重合，重合率约 1%。Uplift 选择的客户近期购买次数、消费金额中位数更低，最近一次购买距截止点更久；这是名单描述，不是特征造成营销效果差异的证据。

全部新增模型拟合和策略评价都限于训练／验证数据，原测试集只用于完整性检查。已有测试结果仍属于此前已查看的评价；新增分析不会恢复独立确认性证据。没有真实成本及贡献毛利数据，成本表仅为假设情景。

## 运行

```bash
# 核心、集成及划分测试
OMP_NUM_THREADS=4 .venv/bin/python -B -m unittest discover -s tests -v

# 本轮使用的完整运行方式
.venv/bin/python -B run_project.py --engine inprocess

# 已有主分析输出时，只运行新增部分
.venv/bin/python -B run_project.py --steps 5 --engine inprocess

# 与本次修改前备份比较
.venv/bin/python -B scripts/verify_robustness_revision.py \
  --baseline work/backups/before_robustness_20261113
```

省略 `--engine inprocess` 使用 Jupyter 内核；两种方式均使用调用脚本的 Python 解释器。重跑会覆盖相应模型、结果表和 notebook 输出。查看完整自动生成摘要请打开 `reports/audit/summary.md`。
