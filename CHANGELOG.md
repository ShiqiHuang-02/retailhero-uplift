# 版本记录

## 2026-11-14 — 方法对比与求职演示

- 新增手写 X-learner（`src/xlearner.py`）与 Qini/AUUC 指标（`src/uplift_metrics.py`），未引入外部因果推断库。
- 新增 `scripts/run_method_comparison.py`：在验证集上对比 T/S/X-learner 的 Qini/AUUC 与 20% DR 策略价值，不触碰测试集。
- 新增合成数据 demo 一键入口（`run_project.py --demo` 与 `scripts/make_demo_data.py`），供招聘方在无真实数据时复现主流程。
- 新增 Streamlit 交互看板（`dashboard/app.py`）与一页业务简报（`docs/business_brief.md`）。
- 新增预算优化脚本（`scripts/run_budget_optimization.py`）：在验证集预算曲线上按毛利/成本寻优触达比例。
- README 增补 TL;DR 与「1 分钟体验」说明。

## 2026-11-13 — 稳健性与本地真实数据验证

- 为 01–03 加入关键审计阻断与共用评价模块，保持原模型参数和主要比较。
- 保留原 04，新增 05：处理概率敏感性、S-learner、客户画像、重选人 bootstrap、五次开发划分。
- 增加统一执行入口及无需 Jupyter 端口的运行方式。
- 22 项测试和 63 个代码单元通过；原九张结果表仅有浮点末位变化。
- 完整报告 S-learner 对照，避免将原 T-learner 解释为最优模型；详见 docs/robustness_revision.md。


## v0.1.0 — 第一版快照（2026-11-10）

本节记录首个 Git 版本包含的现有成果，提交与版本标签以 Git 历史为准。

- 数据探索、T-learner、策略评价三个 notebook。
- 第四份求职展示分析 notebook、SQL 模块、配对 Bootstrap 与成本情景。
- 固定客户划分恢复逻辑、运行入口及划分检查。
- 汇总结果表、图表、离线 HTML 报告及 Tableau 草稿。
- 研究假设、复现边界与拟议线上实验说明。

当前结果为公开数据上的离线分析。测试集此前已查看；新增分析具有探索性质。Tableau 文件为尚未完成原生软件验证的草稿。

原始数据、固定客户清单、处理后数据、训练模型、虚拟环境和本地备份不进入此代码仓库；GitHub 副本不是整个本地项目的完整数据备份。
