# 运行与划分恢复说明

## 必需输入

项目根目录须保留以下文件：

```text
data/raw/clients.csv.gz
data/raw/uplift_train.csv.gz
data/raw/purchases.csv.gz
data/splits/assignments.csv
data/splits/metadata.json
```

原始数据在当前本地项目中已具备。迁移到另一台电脑时，需要自行准备上述输入，并保留三个 notebook、`src/`、`scripts/` 和 `requirements.txt`。不要将本机 `.venv` 直接复制为另一台机器的环境。

`assignments.csv` 保存原有 200,039 名客户的集合归属、内部顺序和两项标签，不包含重新计算的行为特征。`metadata.json` 保存人数与 SHA-256 校验值。清单来自既有 processed 文件的一次性导出，没有重新抽样，也没有声称重建最初划分算法。

**从原始数据复现仍需要固定划分清单。**变化在于，不再需要旧特征、旧模型或旧报告。清单应与项目一起备份；如果丢失，请恢复原清单，不能用新的随机划分冒充同一实验。

## 使用已有环境

在项目根目录运行：

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B scripts/run_pipeline.py
```

第一条运行名单恢复与异常输入检查。第二条依次执行 01 → 02 → 03，每份 notebook 使用独立内核，且采用启动脚本的同一 Python 环境，避免误用其他 Jupyter 环境。

完整运行会重建 `data/processed/`、`models/` 和 `reports/` 下的当前输出，并更新三个 notebook 的运行结果。已有重要结果请先备份，或在独立项目副本中运行。本次验证是在没有 processed、模型或报告文件的独立目录中开始的。

如果选择手动使用 Jupyter，打开项目根目录，确认内核属于该项目 `.venv`，按 01 → 02 → 03 从头执行。

## 新环境准备

本机现有环境为 Python 3.14.7；`requirements.txt` 固定了已记录的依赖版本。另一环境可按如下方式建立：

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B scripts/run_pipeline.py
```

本次验证使用本机已有环境，没有重新安装全部依赖，也没有验证跨操作系统的可安装性或数值一致性。脚本默认将部分数值计算线程数限制为 4，减少线程争抢；这不改变模型超参数。

## 固定名单的恢复与迁移

01 调用 `src/splits.py` 中的 `restore_splits`。读取清单后检查：文件哈希、客户唯一性、跨集交叉、连续行序号、与当前客户集合相符、处理与结果标签一致。校验失败立即报错，绝不自动生成新划分。

`scripts/export_split_manifest.py` 是首次迁移工具，当前项目的清单已经生成，正常运行不需要再执行。只有在从另一个已有完整项目迁移时，才使用：

```bash
.venv/bin/python -B scripts/export_split_manifest.py \
  --source data/processed \
  --labels data/raw/uplift_train.csv.gz \
  --output data/splits
```

输出目录已经存在时工具拒绝覆盖。哈希用于发现意外改动，不是防止恶意篡改的数字签名；比较基准应保留在独立备份中。

## 如何核对独立重跑

在完成运行的项目副本中执行：

```bash
.venv/bin/python -B scripts/verify_reproduction.py --baseline /绝对路径/原项目备份
```

如副本中没有 `.venv`，使用原环境 Python 的绝对路径。验证脚本比较数据集客户顺序、标签、特征、验证预测及全部既有结果表，同时检查 55 个代码单元格均成功执行。数值比较规则如下；比较报告保存为 `reports/reproduction_check.json`。默认模式严格核对名单、标签及特征，完整报告预测和结果表的差异，不将重训后不同的数字强行判为相等。添加 `--strict` 时，预测和结果表也必须在严格浮点容差内一致；可用 `--report 文件名.json` 保留多次比较。基准不能指向副本自身。

完整重跑验证的是既有分析可复现，不增加新的独立样本，也不解决随机分配机制、真实处理时间和观察窗口仍待核实的问题。

## 数值稳定性处理

01 的客户金额汇总原来使用无指定顺序的浮点求和。并行执行的累加顺序会造成末位差异，树模型及排名边界可能放大这种差异。当前将历史金额、平均交易金额及近 30 天金额的聚合顺序固定为每位客户的 transaction_id，保留原金额精度，不做额外舍入。客户范围、交易范围、模型超参数和评价公式保持原样。

与旧版本的细微数值差异见 `reports/reproduction_check.json`；相同新版流程重复运行的严格核对见 `reports/repeatability_check.json`。这是本机同一环境的重复运行验证，不承诺跨版本、跨硬件逐位一致。
