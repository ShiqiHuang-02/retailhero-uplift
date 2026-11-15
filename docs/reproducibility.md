# 运行与复现

项目提供三条运行路径。所有结果均为离线分析，重复运行不产生新的独立因果证据。

| 路径 | 所需输入 | 默认输出 | 能否复现 README 历史数字 |
|---|---|---|---|
| 合成演示 `--demo` | 安装依赖 | `work/demo/` | 不能，仅验证流程 |
| 真实数据新划分 `--new-split` | 三份原始 CSV | `work/new-split/` | 不保证；生成新实验 |
| 历史固定划分，无模式参数 | 原始 CSV、原划分 CSV 及元数据 | 当前项目，更新既有输出 | 同环境下可核对；不承诺跨平台逐位一致 |

## 环境与依赖

已验证的本地解释器为 Python 3.14.7。`requirements.txt` 固定主分析的直接依赖；完整历史环境（含可选 Jupyter 组件）另存于 `requirements-lock.txt`。不要直接复制 `.venv` 到其他机器。

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

2026-11-15 尝试在新虚拟环境安装时，当前软件源未提供 `duckdb==1.5.6` 可安装版本，安装未完成。因此目前验证范围是**已有依赖环境中的完整运行**，不宣称新电脑或跨操作系统安装通过。详见[本轮验证记录](public_repository_validation.md)。

默认使用独立 IPython 子进程执行每份 Notebook，无需 Jupyter 端口；也可加 `--engine kernel` 使用独立内核。两种方式都使用启动脚本的同一 Python。脚本默认限制部分数值计算线程数为 4；环境变量可覆盖此设定。

## 合成演示

```bash
python run_project.py --demo
```

生成 20,000 名合成客户，执行 01 → 02 → 03。代码与 Notebook 复制到独立目录；不带入历史模型、处理后数据或报告。合成数据的潜在活跃度影响历史交易与购买倾向，处理以 0.5 概率随机分配，处理效果随活跃度变化。设定见 `scripts/make_demo_data.py`，不把人为设定的优势当作真实数据结论。

可指定规模、种子与新目录：

```bash
python run_project.py --demo --n-clients 20000 --seed 42 --output work/demo-2
```

目录已存在时拒绝覆盖。演示数据与真实数据共享字段结构，但不承诺共享日期分布、业务样本范围或效果幅度。

## 从真实原始数据开始

从 [ODS 数据页面](https://ods.ai/competitions/x5-retailhero-uplift-modeling/data)自行获取以下文件，遵循提供方的数据使用条款。项目不会自动下载或公开再分发原始数据。

```text
data/raw/clients.csv.gz
data/raw/uplift_train.csv.gz
data/raw/purchases.csv.gz
```

```bash
python run_project.py --new-split
```

可指定其他数据目录和独立输出位置：

```bash
python run_project.py --new-split --raw-dir /path/to/raw --output work/experiment-2 --seed 42
```

程序复制三份原始文件（需要额外磁盘空间），然后生成清单并运行 01 → 02 → 03。开始时目录中没有 processed、模型和报告。若需要补充稳健性分析，可加 `--steps 1 2 3 5`。

划分算法 `sorted_client_id_stratified_treatment_target_python_random_v1`：

1. 以字符串读取客户 ID，拒绝空值、重复客户与非二元标签。
2. 先按客户 ID 稳定排序，再按“处理 × 结果”分层；使用 Python `random.Random(seed)` 打乱每层索引。
3. 每层训练人数取 `round(0.6*n)`、验证人数取 `round(0.2*n)`，余下为测试；每层至少需要 5 名客户。由于分层取整，总人数不必与历史划分相同。
4. 各集合内部按客户 ID 排序，保存连续行号与标签，执行覆盖与不交叉校验。

清单元数据包含算法名、种子、人数、各层分布、标签输入哈希与清单哈希。`run_metadata.json` 另记录原始文件哈希、执行前代码哈希、软件版本、执行步骤和状态。输入顺序改变不会改变划分；数据、种子或算法改变则属于不同实验。

只生成清单（不运行模型）时使用：

```bash
python scripts/create_split_manifest.py --labels data/raw/uplift_train.csv.gz --output work/split-only --seed 42
```

**新清单不是历史名单的恢复。** README 的 10.86、8.29 等来自保留的历史实验；新实验请读取自己的 `reports/tables/`，不要引用历史报告作为本次输出。

## 恢复历史固定划分

除原始数据外，还需要原 `data/splits/assignments.csv` 及其匹配的 `metadata.json`。公开仓库只包含元数据，哈希不能反推出客户名单。

```bash
python run_project.py
```

该路径原地执行 01 → 02 → 03 → 05，会重建处理后数据、模型、报告和 Notebook 输出。需保留历史结果时，请在独立副本中运行。只跑主分析可用 `--steps 1 2 3`；只跑补充分析可用 `--steps 5`，但相应模型与中间数据须已存在。

`restore_splits` 校验文件哈希、客户唯一性、跨集交叉、连续行序号、客户覆盖与标签一致性；缺失或不匹配时立即报错，不自动抽样。原清单来自已有 processed 文件的一次性导出，未重建最初随机划分算法。

如从另一个完整项目迁移名单，可以导出到尚不存在的目录：

```bash
python scripts/export_split_manifest.py --source data/processed --labels data/raw/uplift_train.csv.gz --output work/exported-historical-split
```

## 补充分析与展示

以下命令从**目标实验的根目录**运行。若分析新实验，请先 `cd work/new-split`，并使用已经激活的项目 Python 环境。

```bash
python run_project.py --steps 5
python scripts/run_method_comparison.py
python scripts/build_portfolio.py --audit-raw
python scripts/run_budget_optimization.py --margin 10 --cost 0.5
```

模型比较只在验证集上比较 T/S/X-learner。展示脚本生成客户画像、配对 Bootstrap、预算曲线、HTML 和 Tableau 草稿；预算情景依赖此前生成的展示表。HTML 主要数字从汇总表读取；Tableau 仍需原生验证。

可选看板：`python -m pip install streamlit`，然后 `python -m streamlit run dashboard/app.py`。看板读取其所在实验目录的结果，不自动切换到另一个实验。

## 数字同步与发布

主结果由 03 自动输出到 `reports/tables/`，主要图表由 03 与 `build_portfolio.py` 生成。历史仓库的 README 结果块可由同一组 CSV 自动更新与检查：

```bash
python scripts/summarize_results.py --check
python scripts/summarize_results.py --write
```

更新前确认这是要公开的那一次实验，再同步业务简报、HTML、图表和验证记录。该检查只核对 README 标记区间与两张主表，不等同于全仓库数字校验。

公开 Notebook 保留汇总统计与图表，移除客户明细样例和本机路径。重新执行可能产生机器路径或长警告，提交前需检查输出差异。原始数据、处理后数据、固定客户名单、模型和 `work/` 均由 `.gitignore` 排除。

## 验证与数值稳定性

```bash
python -m unittest discover -s tests -v
python scripts/verify_reproduction.py --baseline /path/to/historical-backup
```

第二条用于具有匹配历史名单的独立重跑核对，**不要用来要求新划分匹配历史结果**。`--strict` 进一步要求预测和结果表符合严格浮点容差；基准不能指向当前项目自身。

金额特征按每位客户的交易 ID 固定求和顺序，减少并行浮点累加差异。客户、标签、特征、模型超参数与评价公式均可单独核对。历史验证见 [reproducibility_validation.md](reproducibility_validation.md)、[repeatability_check.json](../reports/repeatability_check.json)；这些是当时版本与环境的记录，不覆盖后续所有改动。
